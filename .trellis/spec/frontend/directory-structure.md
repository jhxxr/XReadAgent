# Directory Structure

> How the renderer is laid out on disk.

---

## Layout

```
frontend/
├── eslint.config.js          # flat config, typed rules (see Quality Guidelines)
├── .prettierrc.json          # 100-col, double-quote, trailingComma all
├── tsconfig.json             # project references → app + node
├── tsconfig.app.json         # strict + path alias (@/* → ./src/*)
├── tsconfig.node.json        # vite.config.ts / vitest.config.ts only
├── vite.config.ts            # /api + /ws proxy to localhost:8765
├── vitest.config.ts          # jsdom env, tests/**/*.test.{ts,tsx}
├── src/
│   ├── main.tsx              # createRoot — only entrypoint
│   ├── app.tsx               # <App /> + <AppProviders /> (all providers)
│   ├── router.tsx            # TanStack Router tree + module augmentation
│   ├── components/
│   │   ├── ui/               # shadcn-style local primitives (Button, Card, …)
│   │   ├── shell/            # app-wide chrome (AppShell, AppSidebar, …)
│   │   └── <feature>/        # feature-scoped components (e.g. workspace/)
│   ├── lib/                  # framework-shaped utilities (api.ts, theme.tsx, utils.ts)
│   ├── routes/               # one file per route, exports a `<Route>Route` component
│   ├── styles/
│   │   └── globals.css       # Tailwind 4 entry + design tokens (oklch)
│   └── types/
│       └── api.ts            # TS mirrors of Pydantic schemas on the sidecar
└── tests/
    ├── setup.ts              # vitest setup; matchMedia/scrollTo polyfills
    ├── lib/<name>.test.{ts,tsx}
    └── routes/<name>.test.tsx
```

`dist/`, `node_modules/`, `coverage/`, `.vite/` are ignored everywhere (gitignore + `eslint.config.js` `ignores`).

---

## Module Organization

**Three kinds of components**, in this order of preference:

1. **`components/ui/`** — primitive, app-agnostic. Wraps a Radix primitive or pure DOM. No business logic, no data fetching. New files here only when adding a new design-system primitive (e.g. a new `<Drawer />`). Examples: `button.tsx`, `card.tsx`, `dialog.tsx`.
2. **`components/shell/`** — app chrome that lives outside any route. Knows about the global app (router, theme, sidecar health). Example: `app-shell.tsx`, `health-banner.tsx`.
3. **`components/<feature>/`** — components tied to one feature area, used by one or two routes. Example: `components/workspace/workspace-empty-state.tsx`. Create a new feature folder only when a route grows >1 substantive component; otherwise keep the JSX inside the route file.

**Routes** (`src/routes/<name>.tsx`) export a single named component (`<PaperRoute />`, `<QueriesRoute />`) and are registered in `src/router.tsx` via `createRoute({ component: ... })`. Route files own page layout and call into `components/<feature>/...` for non-trivial subtrees.

**`lib/`** — code that talks to the runtime (browser, sidecar, react). One file per concern: `api.ts` (HTTP client), `theme.tsx` (theme context + provider + hook), `utils.ts` (`cn()` only). Add new files freely; resist barrel `index.ts` re-exports.

**`types/api.ts`** mirrors the Pydantic schemas exposed by the Python sidecar (`HealthzResponse`, `PaperSummary`, …). Every new sidecar endpoint adds a TS interface here before anything calls it.

---

## Naming Conventions

| Thing | Convention | Example |
|-------|------------|---------|
| File name | kebab-case | `app-shell.tsx`, `workspace-empty-state.tsx` |
| Component name | PascalCase | `AppShell`, `WorkspaceEmptyState` |
| Hook name | `useFoo` camelCase | `useTheme` |
| Route component | `<Name>Route` | `PaperRoute`, `QueriesRoute` (in `routes/paper.tsx`, `routes/queries.tsx`) |
| Test file | mirror the source path under `tests/` with `.test.{ts,tsx}` | `src/lib/api.ts` → `tests/lib/api.test.ts` |
| `cva` variant table | `<noun>Variants` | `buttonVariants`, `badgeVariants` |
| CSS token | `--<role>` in `globals.css` | `--primary`, `--sidebar-accent` |
| Storage key | `xreadagent.<key>` | `xreadagent.theme` (`lib/theme.tsx`) |

---

## Path Alias

The only alias is `@/*` → `./src/*`, declared in three places that must stay in sync:

- `tsconfig.app.json` → `compilerOptions.paths`
- `vite.config.ts` → `resolve.alias`
- `vitest.config.ts` → `resolve.alias`

Always import via `@/...` from inside `src/` or `tests/`. Avoid relative `../` walks beyond a single level.

---

## When to add a new top-level folder under `src/`

Default: **don't**. The current set (`components/`, `lib/`, `routes/`, `styles/`, `types/`) covers everything in Phase 0–1. Phase 2 may add `agents/` (streaming client logic) or `wiki/` (markdown rendering); discuss in the task's `prd.md` before adding.
