# Electron Development Guidelines

Applies to `electron/src`, `electron/scripts`, `electron/build`, and `electron/tests`.

The Electron app owns the desktop shell, native dialogs, tray/menu/deep links, secure preload bridge, and Python sidecar lifecycle. It must keep the renderer sandboxed and route all native capabilities through explicit IPC.

## Pre-Development Checklist

- Read [Sidecar Lifecycle](./sidecar-lifecycle.md) before changing startup, restart, Python paths, packaged resources, or health checks.
- Read [IPC And Security](./ipc-and-security.md) before changing preload, IPC handlers, dialogs, external links, or renderer integration.
- Read [Quality Guidelines](./quality-guidelines.md) before finishing Electron work.
- For renderer or backend contract changes, also read `../cross-layer/index.md`.

## Quality Check

Run from `electron/`:

```bash
pnpm typecheck
pnpm test
pnpm build
```

For sidecar lifecycle changes, also consider the e2e sidecar test called out in CI:

```bash
pnpm test -- --run tests/e2e/sidecar-lifecycle.test.ts
```

## Local Rules At A Glance

- Create the main window immediately and start the Python sidecar in parallel.
- Load the React renderer only after the sidecar is healthy and has a real port.
- Keep `contextIsolation: true` and `nodeIntegration: false`.
- Expose native functions only through `preload.ts` and typed `window.electronAPI`.
- Do not send deep links to the loading screen; queue them until the renderer loads.
- Preserve production `PYTHONPATH` ordering: backend source first, venv site-packages second, inherited path last.
