# Quality Guidelines

> Quality gates for the renderer. Before-commit checks, lint rules, test patterns.

---

## Required commands (must pass before commit)

From `frontend/`:

```bash
npm run lint        # eslint . (flat config; ignores dist, coverage, node_modules, .vite)
npm run typecheck   # tsc -b --noEmit (app + node project references)
npm run test        # vitest run
```

CI runs the same trio. None of them are advisory.

`npm run format` runs Prettier across `src/**/*.{ts,tsx,css,json}` and `tests/**/*.{ts,tsx}`. Settings (`.prettierrc.json`):

- `printWidth: 100`
- `tabWidth: 2`, `useTabs: false`
- `singleQuote: false` — **double quotes everywhere**, including `"@/foo"` imports
- `trailingComma: "all"`
- `arrowParens: "always"`
- `endOfLine: "lf"`

Prettier is the only formatter; the ESLint config is intentionally formatting-blind (`eslint-config-prettier` is the last layer).

---

## ESLint rules in force (source of truth: `frontend/eslint.config.js`)

- `@eslint/js` recommended
- `typescript-eslint` **`recommendedTypeChecked`** + **`stylisticTypeChecked`** — these are the type-aware rule sets; they require `parserOptions.project` (already wired).
- `eslint-plugin-react-hooks` recommended
- `eslint-plugin-react-refresh` with `allowConstantExport: true` (so `cva` variant exports don't break fast refresh — see `button.tsx`, `badge.tsx`)
- `@typescript-eslint/consistent-type-imports: "error"`
- `@typescript-eslint/no-unused-vars: ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }]`

When you need to suppress a rule, do it on the **specific line** with `// eslint-disable-next-line <rule>`, and (when non-obvious) add a one-line comment above it explaining why. Never disable a rule file-wide or project-wide. Current legitimate suppressions:

- `@typescript-eslint/only-throw-error` in `router.tsx` (TanStack Router uses `throw redirect()` as control flow).
- `react-refresh/only-export-components` next to `useTheme`, `buttonVariants`, `badgeVariants` exports (the file legitimately exports both a component and a non-component value).

---

## Required patterns

- **SPDX header on every TS/TSX/CSS source file** — `// SPDX-License-Identifier: AGPL-3.0-or-later` (CSS uses block comment, see `globals.css`). No exceptions; CI greps for it.
- **Named exports only.** No `export default` anywhere in `src/` — the only `default export` in the tree is in `vite.config.ts` / `vitest.config.ts` / `eslint.config.js` where the tooling requires it.
- **All imports go through `@/`** for anything inside `src/` (or `tests/`). Relative imports are reserved for siblings (`./foo`) and avoided for `../`.
- **All API calls go through `lib/api.ts`** — components never call `fetch` directly.
- **All variant tables use CVA** (see Component Guidelines). Don't ship one-off ternary class strings; if there are ≥3 visual states, define `cva()`.
- **All styling goes through `cn()`** when `className` is a prop, even for one base class.
- **Tests live under `tests/`**, never co-located with source.

---

## Forbidden patterns

- **`console.log` in shipped code.** Acceptable temporarily during local dev — strip before committing. (No project-wide rule yet; team norm.)
- **CSS-in-JS** or `styled-components`. Tailwind + CSS custom properties only.
- **Arbitrary Tailwind values** for colors (`bg-[#aabbcc]`, `text-[oklch(...)]`). Add the token to `globals.css` instead.
- **Default exports** (see above).
- **`any` / `@ts-ignore` / project-wide ESLint disables** — see Type Safety.
- **Direct `localStorage` / `matchMedia` calls outside `lib/`** — they need the SSR-safe `typeof window === "undefined"` guard.
- **`fetch` outside `lib/api.ts`.**
- **New runtime dependencies** without a `prd.md` discussion and an update to the Stack Pinning table in `index.md`.

---

## Testing

**Runner**: Vitest in `jsdom` environment. Setup file `tests/setup.ts` polyfills `window.matchMedia` (jsdom doesn't ship it) and `window.scrollTo` (TanStack Router's scroll-restoration calls it), clears `localStorage` and the `.dark` class before each test, and runs `cleanup()` after each.

**Test layout**: mirror the source path under `tests/`. Filename ends with `.test.ts` (logic) or `.test.tsx` (renders DOM).

**What to test**:

| Layer | Coverage expectation |
|-------|----------------------|
| `lib/` (api, theme, utils) | Cover happy path + every named error branch. `tests/lib/api.test.ts` is the template — assert both the parsed payload shape and the headers + `instanceof ApiError` + `status: 0` network-error case. |
| `components/ui/` | Don't test Radix wrappers in isolation — Radix is already tested upstream. Trust the type system and let route-level tests cover them in context. |
| `components/<feature>/` | Render through the route that uses them when the test exists (see `tests/routes/workspace-empty.test.tsx`). Use Testing Library `findByRole` / `findByText`; only fall back to `data-testid` when role/text queries would be ambiguous. |
| `routes/` | One render-and-assert test per route, exercising the empty state and any user interaction (dialog open, button click). Build a fresh `QueryClient` + `createMemoryHistory({ initialEntries: [...] })` router per test — never share singletons between tests. |
| `hooks` | Wrap in a probe component (`ThemeProbe` in `tests/lib/theme.test.tsx`) and assert observable behavior (class on `<html>`, persisted value, exposed `theme` state). |

**Async event helpers**: use `@testing-library/user-event` (`userEvent.setup()`), wrap state-mutating clicks in `act(async () => { await user.click(...) })` when chasing the React 19 act warnings.

Phase 0+1 ended with 5 frontend tests passing (`api` x 3, `theme` x 1, `workspace-empty` x 1). Phase 2 will grow this — keep each route at ≥1 render test, and add a test for every new `lib/` helper.

---

## Code review checklist

Before opening a PR / asking for review, walk this list:

- [ ] `npm run lint && npm run typecheck && npm run test` all clean.
- [ ] SPDX header on every new file.
- [ ] No `default` exports; no `any`; no `as` outside `lib/api.ts`.
- [ ] All new dependencies appear in both `package.json` and the Stack Pinning table in `spec/frontend/index.md`.
- [ ] New routes registered in `router.tsx` with a matching `routes/<name>.tsx` and at least one test.
- [ ] New API endpoints have a TS interface in `types/api.ts`, a function in `lib/api.ts`, and a test covering happy path + `ApiError`.
- [ ] New tokens (colors, radii) live in `globals.css` as CSS variables, not hardcoded in components.
- [ ] No `console.log` left behind.
- [ ] Components that take `className` accept it via spread + `cn()`.
- [ ] Interactive icon-only controls have an `aria-label`.
- [ ] Changes that touched a Pydantic schema on the sidecar also updated the matching TS interface in `types/api.ts`.

---

## Common mistakes the checks catch

- `import { Foo } from "@/types/api"` where `Foo` is type-only — `verbatimModuleSyntax` breaks the build; the ESLint rule will flag it as `consistent-type-imports`.
- Forgetting `await` on a `userEvent.click` — flaky test that "sometimes passes."
- Sharing a `QueryClient` across tests — cache state bleeds between tests and assertions race.
- Adding a `fetch` in a component — typecheck passes, but `ApiError` handling regresses.
- Editing `vite.config.ts` proxy paths without updating `apiBase` default in `lib/api.ts`.
