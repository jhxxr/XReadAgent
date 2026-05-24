# XReadAgent Frontend

React + Vite + Tailwind CSS v4 + shadcn-style UI primitives. Talks to the
Python sidecar (`xreadagent.api`) over HTTP and WebSocket.

This is the **dev-mode** shell. Phase 3 wraps the same React app in Electron
with a sidecar that reports its random port via `SIDECAR_READY port=<N>`.

## Dev quickstart

Two terminals, dev-mode only (fixed sidecar port `8765`):

```sh
# Terminal 1 — Python sidecar on fixed dev port
cd backend  # (or repo root if you prefer)
uv run python -m xreadagent.api --port 8765

# Terminal 2 — Vite dev server
cd frontend
pnpm install
pnpm dev
# open http://localhost:5173
```

The Vite dev server proxies `/api/*` → `http://localhost:8765/*` and
`/ws/*` → `ws://localhost:8765/*` so the renderer can stay agnostic about
which scheme/host the sidecar runs on. In Electron the proxy goes away
and the renderer reads the random port the sidecar reports on stdout.

### Verifying the health banner

With both terminals running, the top of every page should show a green
"Sidecar ready · xreadagent v<n>" banner. If you kill the Python sidecar
the banner flips red within five seconds (TanStack Query polls
`/healthz` on a 5 s interval).

## Scripts

| Script | What it does |
|---|---|
| `pnpm dev` | Vite dev server on `http://localhost:5173` |
| `pnpm build` | `tsc -b` + `vite build` → `dist/` |
| `pnpm preview` | Serve the production build locally |
| `pnpm typecheck` | `tsc -b --noEmit` |
| `pnpm lint` | ESLint over `src/` and `tests/` |
| `pnpm test` | Vitest run (jsdom) |
| `pnpm test:watch` | Vitest watch mode |
| `pnpm format` | Prettier write |

## Stack

| Layer | Library |
|---|---|
| Build | Vite 6 + TypeScript 5.7 (strict) |
| UI | React 19 |
| Styling | Tailwind CSS v4 (`@tailwindcss/vite`) + `tw-animate-css` |
| Components | Radix Primitives + shadcn-style wrappers in `src/components/ui/` |
| Routing | TanStack Router 1.x (code-based, single file in `src/router.tsx`) |
| Data | TanStack Query 5.x |
| Toasts | Sonner |
| Icons | lucide-react |
| Tests | Vitest 3 + React Testing Library + jsdom |
| Lint | ESLint 9 (flat config, type-checked) + Prettier |

## Layout

```
frontend/
├── index.html
├── src/
│   ├── main.tsx                 React entry
│   ├── app.tsx                  Providers + RouterProvider
│   ├── router.tsx               TanStack Router definition
│   ├── components/
│   │   ├── shell/               App-shell pieces (sidebar, header, copilot)
│   │   ├── ui/                  shadcn-style primitives
│   │   └── workspace/           Workspace surfaces
│   ├── lib/
│   │   ├── api.ts               Sidecar client (`getHealthz`, ...)
│   │   ├── theme.tsx            Theme provider (light/dark/system)
│   │   └── utils.ts             `cn()` helper
│   ├── routes/                  Per-route screen components
│   ├── styles/globals.css       Tailwind v4 entry, design tokens, dark mode
│   └── types/api.ts             Hand-rolled shapes; OpenAPI gen in Phase 2
└── tests/
    ├── setup.ts                 jsdom shims (matchMedia, scrollTo) + jest-dom
    ├── lib/                     api + theme unit tests
    └── routes/                  Route render tests
```

## Conventions

- **Strict TypeScript**: `strict`, `noUncheckedIndexedAccess`,
  `noImplicitOverride`. No `any`, no `as unknown as Foo` escape hatches.
- **AGPL-3.0-or-later** SPDX header on every `.ts` / `.tsx` / `.css`.
- **No emoji** in code or UI text.
- **shadcn components** live under `src/components/ui/` and re-export
  Radix primitives so they stay swappable.
- **Theme**: `next-themes`-style provider; persisted to `localStorage`
  under `xreadagent.theme`. Defaults to system preference.

## Sidecar contract

The dev server expects the Python sidecar on `127.0.0.1:8765` with at
minimum:

- `GET /healthz` → `{ status: "ok", version: "0.0.1" }`
- `WebSocket /ws/events` → ping/pong (placeholder; streaming agent events
  land in Phase 2).

In production (Electron), the sidecar picks a free port and emits
`SIDECAR_READY port=<N>` on stdout; the main process reads it and passes
the URL to the renderer via `window.__XREAD_API__`.

## Out of scope (deferred)

- Electron wrapper, code signing, auto-update — **Phase 3**
- Real PDF rendering (PDF.js) — **Phase 2**
- Streaming copilot UI + WebSocket protocol — **Phase 2**
- Settings UI — **Phase 2**
- OpenAPI type generation — **Phase 2**
- BabelDOC translation UI — **Phase 2**
- Multiple workspaces — **Phase 3+**

See [`plan.md`](../.trellis/tasks/05-22-build-sciresearch-agent-literature-reading-knowledge-base/plan.md)
for the full roadmap.

## License

AGPL-3.0-or-later. See repo root [`LICENSE`](../LICENSE) and
[`NOTICE`](../NOTICE).
