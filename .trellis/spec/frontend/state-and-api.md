# State And API

## API Client Boundary

All sidecar HTTP and WebSocket URL construction belongs in `frontend/src/lib/api.ts` and `frontend/src/lib/platform.ts`.

Local patterns:

- `getApiBase()` resolves `/api` in browser mode and `http://127.0.0.1:{port}/api` in Electron mode.
- `getHealthz()` uses the sidecar root base, because `/healthz` is not under `/api`.
- `buildJobEventsWsUrl(jobId)` appends `/ws/jobs/{jobId}` to the platform-specific WebSocket base.
- `ApiError` includes HTTP status and parsed backend `detail` messages.

Reference files: `frontend/src/lib/api.ts`, `frontend/src/lib/platform.ts`.

## Server State

Use TanStack Query for sidecar-backed state. `AppProviders` configures a single `QueryClient` with `staleTime: 30_000` and `refetchOnWindowFocus: false`.

For mutations:

- Use stable mutation keys when multiple component instances can launch the same workflow.
- Invalidate the specific query keys affected by the mutation.
- Keep long-running mutations pending until the background job has finished, not merely until the initial POST returns.

Reference file: `frontend/src/lib/use-workspace-actions.ts`.

## Background Jobs

Long-running backend work follows a two-step contract:

1. POST returns `{jobId}`.
2. The renderer subscribes to `/ws/jobs/{jobId}` until a terminal `finish` or `error` event.

`runIngestJob()` is the reference client. It resolves only on `finish`, rejects on `error`, socket failure, or premature close, and accepts an injectable WebSocket factory for tests.

Reference file: `frontend/src/lib/ingest-job.ts`.

## Type Contracts

`frontend/src/types/api.ts` mirrors backend Pydantic models. Keep these conventions:

- HTTP JSON request/response fields are camelCase.
- WebSocket event payloads use snake_case fields because backend event models serialize directly.
- Event unions are discriminated by `type`.
- Translation and ingest error events share the same `ErrorEvent` shape.

When backend schemas change, update `types/api.ts`, `lib/api.ts`, route/component consumers, and tests together.

## Settings And Provider Config

Settings are fetched with `getSettings()` and saved with `putSettings()`. The UI currently has general/language/sidecar tabs; provider-model WIP may add fields to backend settings. When expanding settings:

- Preserve partial-update semantics for `UpdateSettingsRequest`.
- Keep language changes flowing through `LanguageProvider`.
- Sync saved `workspacePath` back through `writeWorkspacePath()`.

Reference files: `frontend/src/routes/settings.tsx`, `frontend/src/lib/i18n.tsx`, `backend/src/xreadagent/api/settings.py`.

## Anti-Patterns

- Do not use component-local `fetch` calls for sidecar APIs.
- Do not treat a job as done after the POST returns.
- Do not parse backend errors in each component; use `ApiError` and shared helpers.
- Do not duplicate supported document suffixes without checking Electron file dialog filters.
