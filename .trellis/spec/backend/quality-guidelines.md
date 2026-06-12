# Quality Guidelines

## Required Checks

Backend CI runs:

```bash
uv run ruff check backend/src backend/tests
uv run mypy backend/src
uv run pytest -xvs backend/tests
```

Use targeted tests while iterating, then run the relevant broad command before finishing. `pyproject.toml` sets strict mypy for `backend/src`, Python 3.11 target, and pytest defaults that exclude heavy `babeldoc` and `mineru` markers.

## Test Style

Prefer tests that exercise real local boundaries with injected heavy collaborators:

- FastAPI routes use `TestClient(create_app(...))`.
- Workspace tests create a real temporary `Workspace`.
- Heavy LLM/BabelDOC/MinerU paths use stubs or marker-gated integration tests.
- Job services expose injectable runners/workers so tests can avoid real subprocesses and network calls.

Reference files: `backend/tests/test_wiki_api.py`, `backend/tests/test_ingest_jobs_api.py`, `backend/tests/test_translation_service.py`, `backend/tests/README.md`.

## Lazy Import Regression

When changing startup, API routers, settings, providers, or job service imports, run or update `backend/tests/test_lazy_imports.py`. Sidecar startup must not import heavy LLM/agent stacks until a job actually needs them.

## Schema And Wire Compatibility

- Keep backend Pydantic models aligned with `frontend/src/types/api.ts`.
- Keep API JSON response fields camelCase.
- Keep WebSocket event unions stable and discriminated by `type`.
- For new fields, update backend model, frontend type, API client behavior, and tests in the same change.

## Dependency Risk

`babeldoc==0.6.2` is pinned because its APIs are internal and version bumps are breaking-change events. Any BabelDOC bump needs a smoke PDF round-trip test. Similar caution applies to provider SDK and LangChain/DeepAgents imports because they affect startup and packaged sidecar behavior.

## Anti-Patterns

- Do not add untyped backend code that breaks strict mypy.
- Do not make tests depend on a real LLM key by default.
- Do not broaden default pytest to include expensive marker-gated tests.
- Do not duplicate frontend API TypeScript shapes without updating backend Pydantic models.
