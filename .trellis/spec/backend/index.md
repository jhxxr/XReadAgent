# Backend Development Guidelines

Applies to Python code under `backend/src/xreadagent` and tests under `backend/tests`.

XReadAgent's backend is a Python 3.11+ package that serves as a local FastAPI sidecar, CLI, MCP server, LLM agent layer, document conversion pipeline, translation worker, and markdown-native workspace store. It is not a generic web backend with a database; most state lives in a workspace directory as Markdown, JSON, JSONL, PDFs, and derived extracts.

## Pre-Development Checklist

- Read [Directory Structure](./directory-structure.md) before adding or moving backend modules.
- Read [Error Handling](./error-handling.md) before changing API handlers, job services, workers, or CLI exits.
- Read [Workspace Storage](./workspace-storage.md) before touching workspace layout, manifests, wiki pages, raw files, extracts, translations, or logs.
- Read [Logging Guidelines](./logging-guidelines.md) before adding audit trails or side-effect records.
- Read [Quality Guidelines](./quality-guidelines.md) before finishing any backend change.
- For API contracts consumed by the renderer or Electron shell, also read `../cross-layer/index.md`.

## Quality Check

- Run targeted tests first, then the broad checks that match the touched area.
- Backend CI commands are:
  - `uv run ruff check backend/src backend/tests`
  - `uv run mypy backend/src`
  - `uv run pytest -xvs backend/tests`
- Heavy integration tests are marker-gated. Do not run `babeldoc` or `mineru` tests unless the task explicitly needs them.

## Local Rules At A Glance

- Pydantic wire models use strict validation: `ConfigDict(strict=True, extra="forbid")`.
- HTTP JSON fields use camelCase. WebSocket event `type` tokens and event fields use snake_case.
- Keep sidecar startup light. Do not import LangChain, DeepAgents, BabelDOC, or other heavy dependencies on the FastAPI app import path unless existing tests prove it is acceptable.
- Workspace writes that replace JSON/Markdown state should use `atomic_write_bytes` / `atomic_write_text`; append-only logs should use `append_text_locked`.
- Background job APIs should return `{jobId}` immediately and stream progress over `/ws/jobs/{job_id}`.
- Translation and query flows intentionally avoid mutating synthesized wiki pages except in their owning orchestrators.
