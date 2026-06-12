# Directory Structure

## Package Shape

Backend source lives under `backend/src/xreadagent`. Tests mirror behavior under `backend/tests`. The package uses explicit modules rather than hidden framework magic; new code should land near the owning runtime boundary.

Key areas:

- `api/`: FastAPI sidecar routes and job facades. `api/main.py` builds the app, wires shared state, and owns root routes such as `/healthz`, `/api/translate`, `/ws/jobs/{job_id}`, static workspace file serving, and SPA fallback. `api/wiki_router.py` owns wiki read APIs plus ingest/query endpoints.
- `agents/`: LLM-backed ingest, query, crystallize, planner schemas, prompts, and deterministic write-out helpers.
- `pipeline/`: source conversion and routing. `pipeline/router.py` is the single ingest conversion entry point and delegates to MinerU or MarkItDown converters.
- `translation/`: BabelDOC adapter, worker, manifest, service, and translation events. `translation/service.py` is the API/CLI-facing orchestration layer.
- `wiki/`: workspace layout, atomic writes, Markdown page read/write, frontmatter parsing, sources index, and logs.
- `schemas/`: Pydantic schemas for persisted/wiki-facing structures.
- `cli/`: Typer/argparse-style command boundary for local smoke flows.
- `mcp/`: MCP server tools/resources that expose backend capabilities to external AI tools.

Reference files: `backend/src/xreadagent/api/main.py`, `backend/src/xreadagent/api/wiki_router.py`, `backend/src/xreadagent/pipeline/router.py`, `backend/src/xreadagent/wiki/workspace.py`.

## Where New Logic Belongs

- Put HTTP request/response shapes and status-code mapping in `api/`.
- Put durable workspace path knowledge in `wiki/workspace.py` or `wiki/paths.py`, not in route handlers.
- Put deterministic file mutations in `wiki/`, `pipeline/`, `agents/apply_*`, or the owning service, not in UI-facing API models.
- Put LLM orchestration in `agents/`; keep route handlers thin after validation/model resolution.
- Put long-running work behind service/worker classes with injectable collaborators so tests can stub expensive dependencies.

## Import Boundaries

The sidecar startup path must stay light. `backend/src/xreadagent/api/ingest_jobs.py` imports `IngestAgent` and `ingest_source` inside `_default_runner`, not at module import time, because `backend/tests/test_lazy_imports.py` guards that LangChain is not loaded during sidecar startup.

Follow the same pattern for heavy optional dependencies:

- Import agent/LLM libraries inside the function that actually runs a job.
- Import BabelDOC only in translation adapter/worker code, not in `api/main.py`.
- Keep tests able to instantiate `create_app()` without real LLM providers, BabelDOC assets, or MinerU installed.

## Naming And API Model Placement

- Request/response Pydantic models used only by one router can live in that router (`TranslateRequest`, `IngestRequest`, `QueryRequest`).
- Persisted state schemas that are shared across modules should live in `schemas/`, `translation/manifest.py`, or the owning wiki module.
- Prefer explicit names that include the protocol boundary: `IngestJobRequest`, `IngestJobResponse`, `TranslationRequest`, `TranslationsManifest`.

## Anti-Patterns

- Do not add route handlers that directly perform LLM calls or document conversion synchronously.
- Do not duplicate workspace path arithmetic in API/frontend-facing code; use `Workspace` accessors.
- Do not move shared sidecar state into module globals when tests need to inject services via `create_app(...)`.
- Do not add broad package-level imports that make `python -m xreadagent.api --port 0` load expensive optional subsystems.
