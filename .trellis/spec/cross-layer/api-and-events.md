# API And Events

## HTTP Naming

HTTP JSON payloads use camelCase across backend and frontend.

Examples:

- Backend `TranslateRequest.workspacePath`, `sourcePath`, `targetLang`, `maxTokens` in `backend/src/xreadagent/api/main.py`.
- Frontend `TranslateRequest` in `frontend/src/types/api.ts`.
- Backend `IngestJobResponse.jobId` and frontend `IngestJobResponse.jobId`.

When adding an HTTP field, update backend Pydantic model, frontend type, API helper, and tests together.

## WebSocket Naming

WebSocket events use snake_case event fields and stable snake_case `type` tokens.

Examples:

- Translation `FinishEvent` fields: `mono_path`, `dual_path`, `duration_s`, `cached`.
- Ingest `IngestFinishEvent` fields: `cache_hit`, `files_touched`, `duration_s`.
- Stage tokens: `stage_start`, `stage_progress`, `stage_end`.

This is intentional because event models serialize directly from backend Pydantic/in-process schemas.

## Job Contract

Long-running operations use the shared job flow:

1. HTTP POST starts work and returns `{jobId}` immediately.
2. Frontend opens `/ws/jobs/{jobId}`.
3. Backend streams progress events.
4. Backend sends exactly one terminal `finish` or `error` event, then the stream closes.

Current implementations:

- Translation: `POST /api/translate` in `api/main.py`, `TranslationService.event_stream`.
- Ingest: `POST /api/ingest` in `api/wiki_router.py`, `IngestJobService.event_stream`.
- Frontend ingest client: `frontend/src/lib/ingest-job.ts`.

## Error Contract

Backend HTTP errors should include FastAPI `detail` so `frontend/src/lib/api.ts` can surface a useful `ApiError`. Frontend should not duplicate per-endpoint error parsing.

Job errors share the `ErrorEvent` shape. Keep it compatible between translation and ingest so UI code can handle one terminal failure path.

## Schema Drift Checklist

Before finishing any API/event contract change:

- Backend Pydantic model updated.
- Frontend `types/api.ts` updated.
- `lib/api.ts` or job client updated if URL/body semantics changed.
- Route/component consumers updated.
- Backend route/service tests updated.
- Frontend API/job tests updated.

## Anti-Patterns

- Do not introduce snake_case HTTP JSON fields unless the endpoint is explicitly not a renderer-facing API.
- Do not add a second WebSocket path for a job type when `/ws/jobs/{jobId}` can carry it.
- Do not let frontend code infer job completion from socket close without a terminal event.
