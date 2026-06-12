# Sidecar Lifecycle

## Startup Contract

The main process spawns the Python sidecar with:

```text
python -m xreadagent.api --port 0
```

The sidecar prints `SIDECAR_BOOT` early and `SIDECAR_READY port=<N>` when uvicorn is listening. `SidecarManager` then polls `/healthz` before the renderer is loaded.

Reference files: `electron/src/sidecar.ts`, `backend/src/xreadagent/api/__main__.py`, `electron/src/main.ts`.

## Timeouts

Use the tiered timeout model:

- `SIDECAR_BOOT_TIMEOUT_MS`: first sign of life. Silence beyond this budget indicates a hung process.
- `SIDECAR_READY_TIMEOUT_MS`: full import/startup budget after any output appears. This is deliberately generous for first launch and antivirus scanning.
- `HEALTHZ_TIMEOUT_MS`: final local HTTP readiness check.

Do not collapse these into one short timeout; recent release work raised the ready budget because packaged cold starts can be slow.

## Renderer Loading

`electron/src/startup.ts` is the pure decision boundary:

- `resolveRendererUrl(...)` returns `null` until `sidecarPort > 0`.
- In dev mode, the renderer URL is the Vite dev server, but loading still waits for sidecar readiness.
- In packaged mode, the sidecar serves the SPA from `XREAD_FRONTEND_DIR`, so the renderer URL is `http://127.0.0.1:{port}/`.

`main.ts` shows an inline loading/error screen until the sidecar is ready.

## Production Environment

`buildSidecarEnv()` owns packaged Python environment construction.

Required order:

1. Bundled backend source path.
2. Bundled venv `site-packages`.
3. Inherited `PYTHONPATH`.

`VIRTUAL_ENV` and venv `Scripts`/`bin` are also set, but the base interpreter does not discover venv packages from `VIRTUAL_ENV` alone. Tests in `electron/tests/sidecar.test.ts` guard the `pydantic` import regression.

## Restart And Logs

Unexpected sidecar exits trigger up to three auto-restart attempts with exponential backoff. Recent stdout/stderr lines are stored in a circular buffer for the settings UI.

Renderer-facing status and restart info flows through IPC:

- `sidecar:status`
- `sidecar:logs`
- `sidecar:restart`
- `sidecar:restart-info`
- `sidecar:restarting`

Reference files: `electron/src/sidecar.ts`, `frontend/src/components/settings/sidecar-tab.tsx`.

## Anti-Patterns

- Do not block `createMainWindow()` on Python startup.
- Do not assume the sidecar always runs on port `8765`; packaged and Electron flows use random ports.
- Do not remove health polling after the ready marker.
- Do not add production Python paths in an order that lets stale installed package code override bundled source.
- Do not make cold-start timeouts shorter without reproducing packaged first-launch behavior.
