# Cross-Layer Contracts

Applies when a task touches more than one of backend, frontend, and Electron.

Read this before changing API schemas, WebSocket events, workspace file paths, settings/provider config, sidecar startup, or import/translation/query flows.

## Pre-Development Checklist

- Read [API And Events](./api-and-events.md) before changing HTTP models, frontend API types, job events, or WebSocket clients.
- Read [Workspace And Files](./workspace-and-files.md) before changing workspace paths, served files, import/translation outputs, or drag-and-drop/native file flows.
- Read [Sidecar Integration](./sidecar-integration.md) before changing Python sidecar startup, renderer URL resolution, Vite proxying, or Electron preload APIs.
- Also read the owning layer specs: `../backend/index.md`, `../frontend/index.md`, and/or `../electron/index.md`.

## Quality Check

For cross-layer changes, run the relevant checks on every touched layer. Typical full matrix:

```bash
uv run ruff check backend/src backend/tests
uv run mypy backend/src
uv run pytest -xvs backend/tests
cd frontend && pnpm lint && pnpm typecheck && pnpm test
cd electron && pnpm typecheck && pnpm test
```

Use targeted tests first, but do not finish with only one layer checked when the contract crosses layers.

## Local Rules At A Glance

- Backend Pydantic models and frontend TypeScript interfaces must move together.
- HTTP JSON uses camelCase; WebSocket job event fields use snake_case.
- Long-running jobs return `{jobId}` from HTTP and stream terminal `finish` or `error` over `/ws/jobs/{jobId}`.
- Workspace-relative file paths are POSIX strings in manifests and API payloads.
- Electron is the only owner of native filesystem dialogs and dropped-file path resolution.
