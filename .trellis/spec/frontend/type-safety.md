# Type Safety

> TypeScript conventions in the renderer.

---

## Compiler settings (source of truth: `frontend/tsconfig.app.json`)

Strict mode is on, plus the following are not optional:

- `strict: true`
- `noUnusedLocals: true`, `noUnusedParameters: true`
- `noFallthroughCasesInSwitch: true`
- `noUncheckedSideEffectImports: true`
- **`noUncheckedIndexedAccess: true`** — every `arr[0]` / `obj[key]` returns `T | undefined`. You must narrow.
- `noImplicitOverride: true`
- `verbatimModuleSyntax: true` — `import type` for types, `import` for values; not interchangeable.
- `exactOptionalPropertyTypes: false` — intentional, so libraries that distinguish "absent" vs "explicit undefined" don't churn. Don't flip this without a discussion in `prd.md`.
- `target: ES2022`, `module: ESNext`, `moduleResolution: bundler`, `jsx: react-jsx`.

Type check command (must pass before commit): `npm run typecheck` (`tsc -b --noEmit`).

---

## `import type` is mandatory

Because `verbatimModuleSyntax: true`, type-only imports must use `import type` (or inline `import { type Foo }`). The ESLint rule `@typescript-eslint/consistent-type-imports: "error"` enforces this. Mixing them is a build break, not a warning.

```ts
// ✓ types
import type { HealthzResponse } from "@/types/api";
import { type ClassValue, clsx } from "clsx";   // inline form is also fine
import type { LucideIcon } from "lucide-react";

// ✗ this breaks the build under verbatimModuleSyntax
import { HealthzResponse } from "@/types/api";
```

---

## Type organization

| Where the type lives | What goes there |
|----------------------|-----------------|
| `frontend/src/types/api.ts` | TS mirrors of Pydantic schemas exposed by the Python sidecar (`HealthzResponse`, `PaperSummary`, `ConceptSummary`, `QuerySummary`). One interface per response shape. |
| Co-located with the component / hook | Props interfaces (`ButtonProps`, `ThemeProviderProps`), internal helper types (`BannerState` in `health-banner.tsx`, `NavItem` in `app-sidebar.tsx`). |
| `frontend/src/lib/theme.tsx` | Re-exportable types that the rest of the app needs (`Theme`, `ResolvedTheme`). |

Do not invent a `types/index.ts` barrel — `types/api.ts` is the only file currently in `types/`, and that's the convention: one file per external schema source.

---

## API schemas: types/api.ts mirrors Pydantic

`types/api.ts` is **the renderer's view of the sidecar contract**. Rules:

- Field names follow the JSON wire format (`ingestedAt`, `archivedAt`), not the Python source (`ingested_at`). The Pydantic models use camelCase aliases on the wire — if a new field arrives in snake_case, fix the Pydantic side, don't translate in the client.
- Arrays of immutable values use `readonly T[]` (`authors: readonly string[]`).
- ISO timestamps are typed as `string` with a doc comment (`/** ISO 8601 UTC timestamp. */`). Do not parse them into `Date` at the boundary; let consumers parse if needed.
- Nullable fields: `T | null` (matches JSON), not `T | undefined`.

When you add an endpoint to the Python sidecar, add the matching TS interface here **first**, then write the `lib/api.ts` function that returns `Promise<Foo>`. The api client is the only file that exits the type-safe world via `(await response.json()) as T` — keep it that way.

---

## Runtime validation

**None for v1.** The sidecar is local, the contract is fixed by Pydantic on the server, and we control both sides. `lib/api.ts` does one `as T` cast in `request<T>` (`(await response.json()) as T`). That's the only sanctioned assertion.

If a Phase 2 endpoint requires defensive parsing (e.g. user-uploaded JSON), introduce `zod` and add a discussion to `prd.md`. Don't sprinkle `zod` schemas across the renderer "just to be safe" — they double the maintenance cost of every type.

---

## Discriminated errors

`ApiError` (`frontend/src/lib/api.ts`) is the only thrown type from the api layer. It has:

- `name = "ApiError"` (override-readonly, so structural narrowing works).
- `status: number` (`0` = network error, otherwise HTTP status).

Consumers narrow with `instanceof ApiError` (see `health-banner.tsx#selectState`). Never throw plain `Error` from `lib/api.ts`. Tests pin both `instanceof ApiError` and the `status` shape (see `tests/lib/api.test.ts`).

---

## Common patterns

- **`as const` for static config tables**: `NAV_ITEMS: readonly NavItem[] = [...] as const` (`app-sidebar.tsx`).
- **`Record<K, V>` lookup tables**: `NEXT: Record<Theme, Theme>`, `LABEL: Record<Theme, string>` in `theme-toggle.tsx`. Exhaustiveness comes from `K` being a closed union.
- **`React.ComponentRef<typeof Primitive>` / `React.ComponentPropsWithoutRef<typeof Primitive>`** for Radix wrappers (`dialog.tsx`).
- **`VariantProps<typeof fooVariants>`** to pull CVA variants into props (`ButtonProps`, `BadgeProps`).
- **`unknown` for caught errors**, narrowed with `instanceof`: `error instanceof ApiError ? ... : error instanceof Error ? ... : "Unknown error"` (`health-banner.tsx`).
- **`{ slug }` typed via `useParams({ from: "/paper/$slug" })`** — the router's `Register` augmentation gives full inference.

---

## Forbidden patterns

- **`any`**. There is none in the codebase. If you reach for it, you have not finished thinking about the type. Use `unknown` + narrowing.
- **`as Foo` casts** — only `lib/api.ts` `request<T>()` may do it (for the JSON boundary). Any other `as` is a smell that demands a comment justifying it (e.g. `import.meta.env.VITE_API_BASE as string | undefined`, which we already do once).
- **`@ts-ignore` / `@ts-expect-error`**. Use targeted ESLint disables when really needed (`// eslint-disable-next-line @typescript-eslint/only-throw-error` for TanStack Router's redirect throws); never disable the TS checker itself.
- **Non-null assertions (`x!`)** outside test files. In tests they're acceptable for narrowing tuple/array access (see `tests/lib/api.test.ts`'s `call!`).
- **Type aliases for primitives** (`type UserId = string`) that don't add real safety. Either use a branded type (`type UserId = string & { __brand: "UserId" }`) or just use `string` and document the meaning at the call site.

---

## Common mistakes

- **`arr[0]` without a `?`** — under `noUncheckedIndexedAccess` the result is `T | undefined`. Either narrow (`const first = arr[0]; if (!first) ...`) or use `at(0)` and handle the undefined case.
- **`import { type X }` mixed with value imports across multiple lines** — the ESLint rule wants one consistent style per import statement. Prefer top-level `import type { X }` unless mixing values and types from the same module.
- **Forgetting `Register` augmentation** when adding a new route — without `declare module "@tanstack/react-router" { interface Register { router: typeof router } }` (`router.tsx`), `useParams` / `Link to=...` lose their inference.
- **Annotating a `useState` setter parameter** as `React.SetStateAction<T>` — let TS infer it from the initial value (`useState<Theme>(...)`).
