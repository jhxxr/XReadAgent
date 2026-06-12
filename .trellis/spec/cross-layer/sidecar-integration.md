# Sidecar Integration

## Startup Flow

Electron main process starts the Python sidecar before loading the renderer:

1. Create the main window with loading UI.
2. Spawn the sidecar.
3. Wait for `SIDECAR_READY port=<N>`.
4. Poll `/healthz`.
5. Load the renderer.
6. Inject/expose the sidecar port through the preload bridge.

Reference files: `electron/src/main.ts`, `electron/src/sidecar.ts`, `electron/src/startup.ts`, `frontend/src/lib/platform.ts`.

## Dev Versus Packaged URLs

Browser dev mode:

- Vite serves the renderer.
- `/api` is proxied and stripped before hitting the sidecar.
- `/ws` upgrades are proxied to the sidecar.

Electron mode:

- Renderer API base is `http://127.0.0.1:{port}/api`.
- Renderer WS base is `ws://127.0.0.1:{port}`.
- Packaged renderer is served by the sidecar from `XREAD_FRONTEND_DIR`.

Do not hardcode `localhost:8765` in frontend feature code; only Vite dev proxy config should know that default.

## Health And Settings UI

`/healthz` is a sidecar root route, not under `/api`; frontend `getHealthz()` uses `getSidecarBaseUrl()`.

Sidecar status/log/restart controls are Electron IPC, not backend HTTP. The settings sidecar tab gates itself with `isElectron()` and shows a browser-mode notice otherwise.

Reference files: `frontend/src/lib/api.ts`, `frontend/src/components/settings/sidecar-tab.tsx`.

## SPA Fallback

When `XREAD_FRONTEND_DIR` points to a built frontend, backend `api/main.py` serves:

- `/assets/*` as static assets.
- `/` and client-side routes as `index.html`.
- Reserved prefixes (`/api`, `/ws`, `/mcp`, `/healthz`) as backend control-plane routes, not SPA HTML.

Keep this split when changing route prefixes.

## Anti-Patterns

- Do not load the renderer before sidecar readiness in Electron.
- Do not make browser-mode frontend depend on Electron preload APIs.
- Do not let SPA fallback swallow API, WebSocket, MCP, or health routes.
- Do not add a frontend API helper that bypasses `getApiBaseUrl()` / `getWsBaseUrl()`.
