# State Management

> Where each kind of state lives.

---

## State categories

The renderer has **four** kinds of state. Pick the right one — they do not substitute for each other.

| Category | Lives in | Examples |
|----------|----------|----------|
| **Server state** | TanStack Query cache | `/healthz`, future `/papers`, `/queries`, `/concepts` |
| **App-wide UI state** | React Context + Provider | theme (`lib/theme.tsx`) |
| **URL state** | TanStack Router | active route, route params (`/paper/$slug`), redirects |
| **Local ephemeral state** | `useState` in the component | dialog open/close, hover, input draft, tab selection |

There is **no Redux, Zustand, Jotai, MobX, Recoil, or Pinia**. Don't introduce one. If the choice gets tight, post in the task's `prd.md` and discuss before adding a dependency.

---

## Server state — TanStack Query

All sidecar data is server state, even though "server" is `localhost:8765`. Rationale: it's persisted on disk, can change out-of-band (CLI, another window), and benefits from caching + refetch semantics.

Defaults (set in `frontend/src/app.tsx`):

- `staleTime: 30_000` — read calls that succeed are considered fresh for 30s.
- `refetchOnWindowFocus: false` — Electron windows lose focus constantly; we don't want a refetch storm.

Per-query overrides:

- **Polling queries** (sidecar liveness): explicit `refetchInterval` (`HealthBanner` polls `/healthz` every 5s) and `retry: false` so a real connection failure surfaces immediately.
- **One-shot queries** (paper read, concept read): no special overrides — the 30s `staleTime` is the right default.

**Mutation cache invalidation** lands in Phase 2. The rule will be: each mutation's `onSuccess` invalidates the smallest set of query keys that could have changed. Example: ingesting a paper invalidates `["papers"]` (the index) and `["concepts"]` (concept counts), but not `["healthz"]`.

---

## App-wide UI state — Context

Use Context **only** when:

1. The state is meaningfully app-wide (every route observes it), **and**
2. Prop-drilling would cross 3+ layers, **and**
3. The state changes rarely (theme: a few times per session).

Current Contexts:

- `ThemeContext` (`lib/theme.tsx`) — `{ theme, resolvedTheme, setTheme }`, persisted to `localStorage` under `xreadagent.theme`, with `matchMedia` subscription for `system` mode.

When to add another: a new "app-wide concern" that genuinely matches the three criteria above — e.g. the future workspace switcher (when there are multiple workspaces) or sidecar connection identity. Don't add Context for "things that happen to be needed in two places."

**Pattern**: see `lib/theme.tsx`. Co-locate Provider + hook + non-null check; memoize the value object; SSR-guard browser globals; pair with a test under `tests/lib/`.

---

## URL state — TanStack Router

Route, route params, and `?` search params live in the URL — not in React state and not in Context. Reasons:

- Back/forward navigation works without bespoke history wiring.
- A deep link to `/paper/<slug>` reloads correctly.
- The router exposes `useRouterState`, `useParams`, and (Phase 2) `useSearch` with full type inference via the `Register` augmentation in `router.tsx`.

Don't mirror route state into `useState` "for convenience." That introduces drift between the URL and the UI.

---

## Local ephemeral state — `useState`

Anything that's neither server state nor app-wide nor URL-derived: `useState`, scoped to the component or its parent. Examples:

- `WorkspaceEmptyState` owns `explainerOpen: boolean` for the "What is an LLM Wiki?" dialog (`frontend/src/components/workspace/workspace-empty-state.tsx`).
- `CopilotSidebar` owns `open: boolean` for the Radix dialog.

Default rule: state lives **as low in the tree as possible**. Lift only when a sibling needs it.

---

## Persistence

- `localStorage` — used only for `xreadagent.theme` so far. Key convention: `xreadagent.<scope>.<name>`. SSR/test-safe read/write (see `theme.tsx` `readStored` / `setTheme`).
- `sessionStorage` — not used. Don't add it without a reason.
- Cookies — none. The sidecar doesn't use auth in v1.

---

## Common mistakes

- **Putting server data in `useState`**. Use TanStack Query — the cache is your single source of truth, and `useQuery` already exposes `data`, `isPending`, `isError`, `error`.
- **Mirroring URL state in Context**. The router is the source of truth; reading it twice creates lag.
- **Mirroring derived state**. `resolvedTheme` is computed inline from `theme + system`, not stored. Apply the same pattern: if it's a function of other state, derive it during render.
- **Adding a global store "just in case"**. The local-first, route-anchored layout means almost nothing genuinely needs to be global. Force yourself to articulate which two distant components share the state and why prop drilling fails before reaching for Context.
- **Polling without `retry: false`**. With retries on, a 5s poll against a dead sidecar can fan out into a stuttering UI; the `HealthBanner` rule is "fail fast, render the error tone, recover on the next interval."
