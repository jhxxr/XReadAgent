# Error Handling

## HTTP Boundaries

FastAPI handlers should translate local exceptions into deliberate status codes at the route boundary.

Local patterns:

- Missing or invalid `workspacePath` becomes HTTP 400 in `_open_workspace` (`api/main.py`, `api/wiki_router.py`).
- Missing wiki pages become HTTP 404 in wiki read handlers.
- Invalid user inputs for jobs, such as missing source files or invalid translation sources, become HTTP 422 (`POST /api/translate`, `POST /api/ingest`).
- Service not configured is HTTP 503, not an AttributeError (`_resolve_translation_service`, `post_ingest`).

Reference files: `backend/src/xreadagent/api/main.py`, `backend/src/xreadagent/api/wiki_router.py`, `backend/tests/test_wiki_api.py`, `backend/tests/test_translate_api.py`, `backend/tests/test_ingest_jobs_api.py`.

## Strict Pydantic Models

Use strict Pydantic models at API and event boundaries:

```python
class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
```

This pattern appears in API models and job events. It catches misspelled fields and accidental coercions before data crosses process boundaries.

## Job Error Events

Long-running jobs report terminal failures through WebSocket error events rather than only raising in the background thread/subprocess.

- Translation uses `translation.events.ErrorEvent`.
- Ingest reuses the translation `ErrorEvent` shape so frontend consumers handle one job failure contract.
- Job services should emit a terminal `error` event, then finish the stream.
- Include a concise message and bounded traceback excerpt where useful; `IngestJobService` truncates tracebacks to 2000 characters.

Reference files: `backend/src/xreadagent/api/ingest_jobs.py`, `backend/src/xreadagent/translation/events.py`, `backend/src/xreadagent/translation/worker.py`.

## Path And File Errors

For workspace file serving, distinguish:

- 400 for empty, absolute, or escaping paths.
- 403 for workspace roots that are not allowlisted.
- 404 for missing files.

`_resolve_workspace_file` in `api/main.py` is the reference implementation. Keep the allowlist narrow: `translations`, `raw`, and `extracts` are currently safe; `state` and `wiki` are intentionally not served.

## Recovery And Defaults

Use safe defaults only where the product contract calls for it. `settings.load_settings()` returns default settings for missing or corrupted settings files because this is a single-user desktop app and a corrupt settings file should not prevent startup.

Do not hide failures that should drive user action. A missing translations manifest returns 404 from the backend, and the frontend intentionally maps that to an empty manifest.

## Anti-Patterns

- Do not catch broad exceptions in route handlers and return HTTP 200 with error-shaped JSON.
- Do not let background job exceptions vanish in daemon threads.
- Do not leak full secrets, API keys, or unbounded tracebacks into WebSocket events or logs.
- Do not convert transient sidecar startup failures into silent fallback behavior.
