# Frontend Architecture

## Runtime Modes

The renderer runs in two modes:

- Browser dev mode: Vite serves React at `http://localhost:5173`; `/api` and `/ws` are proxied to the sidecar at `localhost:8765`.
- Electron mode: the main process injects the live sidecar port, and the renderer talks directly to `http://127.0.0.1:{port}` / `ws://127.0.0.1:{port}`.

Reference files: `frontend/vite.config.ts`, `frontend/src/lib/platform.ts`, `electron/src/main.ts`.

## Routing

TanStack Router is defined in `frontend/src/router.tsx`.

- `/` redirects to `/workspace`.
- The workspace route is eager because it is the first screen.
- Paper reader, markdown-heavy wiki pages, queries, and settings routes are lazy-loaded so `pdfjs-dist` and `react-markdown` stay out of the initial bundle.

When adding a route, decide whether it belongs in the initial workspace path or should use `lazyRouteComponent`.

## Providers

`frontend/src/app.tsx` owns shared providers:

- `ThemeProvider`
- `QueryClientProvider`
- `LanguageProvider`
- `TooltipProvider`
- `Toaster`
- `RouterProvider`

Avoid creating additional app-wide singletons inside route components. If a new provider must wrap the app, add it in `AppProviders` and test the affected route.

## Platform Boundary

Components should not directly inspect Electron internals. Use:

- `isElectron()`
- `getElectronAPI()`
- `getApiBaseUrl()`
- `getWsBaseUrl()`
- listener helpers such as `onDeepLink`, `onOpenWorkspace`, and `onSidecarRestarting`

Reference file: `frontend/src/lib/platform.ts`.

## Workspace Path Boundary

Temporary workspace selection lives in `frontend/src/lib/workspace.ts` and uses `localStorage` plus a custom event. Until a fuller workspace switcher exists, do not add alternate workspace-path storage.

`useWorkspacePath()` is the hook for React consumers. `writeWorkspacePath()` is the imperative bridge used by settings, Electron menu/deep-link handlers, and workspace selection.

## Anti-Patterns

- Do not call `window.electronAPI` directly from random components when a `lib/platform.ts` helper can own the boundary.
- Do not hardcode `localhost:8765` or a sidecar port in feature code.
- Do not import PDF/rendering/markdown-heavy dependencies into the root route unless the first screen requires them.
- Do not create route-local QueryClient instances.
