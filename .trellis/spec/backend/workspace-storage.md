# Workspace Storage

## Storage Model

XReadAgent stores user knowledge in a workspace directory, not a relational database. Treat the workspace layout as a public product contract because the renderer, CLI, MCP tools, and future users all rely on it.

Workspaces are **app-managed**: the desktop app creates them under the Electron `userData` directory (`<userData>/workspaces/<slug>/`) and tracks them in a registry (`<userData>/workspaces.json`). Electron owns *where* a workspace lives (slug allocation, collision handling, directory lifecycle, registry); the backend `Workspace` stays the owner of the *layout inside* a root. There is no "open an arbitrary folder" path — wiki/translation artifacts must never land in Downloads or another unmanaged location.

Workspace creation is seeded by the backend via `POST /api/workspaces/create` (`api/main.py`, `_create_workspace`), which runs `Workspace.init_empty` and mirrors the `xreadagent init` CLI semantics (idempotent; refuses a non-empty, non-workspace directory). It is the ONLY HTTP endpoint allowed to materialize a workspace.

Canonical layout ownership:

- `wiki/workspace.py`: `Workspace` object and path accessors.
- `wiki/paths.py`: layout constants, source slugs, and path helpers.
- `wiki/sources.py`: `state/sources.json` manifest.
- `translation/manifest.py`: `translations/manifest.json`.
- `wiki/pages.py` and `wiki/frontmatter_utils.py`: Markdown page writes/reads.

Reference files: `backend/src/xreadagent/wiki/workspace.py`, `backend/src/xreadagent/wiki/paths.py`, `backend/src/xreadagent/wiki/sources.py`, `backend/src/xreadagent/translation/manifest.py`.

## Write Safety

Use atomic replacement for JSON/Markdown state that should never be partially written:

- `atomic_write_bytes`
- `atomic_write_text`

Use `append_text_locked` for append-only logs that may be written by concurrent jobs in one sidecar process.

Reference file: `backend/src/xreadagent/wiki/atomic.py`.

## Operation Isolation

Different workflows intentionally touch different workspace areas:

- Conversion writes `extracts/`, archives raw input under `raw/_processed/`, updates `state/sources.json`, and appends a `convert` row to `wiki/log.md`.
- **Register (decoupled import)** runs convert-only: it does the conversion + source-manifest write but NO LLM/wiki synthesis. See `agents/orchestrator.py::register_source` and the `mode="register"` branch of `api/ingest_jobs.py::_default_runner`. Triggered by `POST /api/sources/register` (no model required).
- Ingest (build wiki) writes synthesized wiki pages and state through the agent apply/write path. Triggered by `POST /api/ingest` or, for an already-registered source by slug, `POST /api/sources/{slug}/build` (resolves the archived file from `state/sources.json` so the renderer never constructs a path). The convert step short-circuits on the cached content hash.
- Query writes only `wiki/queries/{topic}/...` and `state/conversation-log.jsonl`; it must not mutate papers, concepts, index, or `wiki/log.md`.
- Translation writes `translations/manifest.json`, translation PDFs, and conversation-log entries; it must not mutate wiki papers/concepts or sources.

`GET /api/sources` lists registered documents from `state/sources.json` (NOT `wiki/papers/`) with derived per-document status: `wikiBuilt` (a `wiki/papers/{slug}.md` exists) and `translated` (a translation entry shares the source `contentHash`). Registered-but-unbuilt documents MUST appear here.

Reference files: `backend/src/xreadagent/pipeline/router.py`, `backend/src/xreadagent/agents/orchestrator.py`, `backend/src/xreadagent/api/ingest_jobs.py`, `backend/src/xreadagent/api/wiki_router.py`, `backend/src/xreadagent/translation/service.py`, `backend/tests/test_translation_service.py`.

## Idempotency

Content hash and stable slug logic prevent unnecessary rework:

- `convert_source` short-circuits when `state/sources.json` already knows the content hash and the canonical extract exists.
- `ingest_source` short-circuits when the paper page already exists for the known source.
- `TranslationService.start_translation` returns a synthetic cache-hit job when a manifest entry and its PDFs still exist.

When adding a new workspace mutation, decide the idempotency key up front and test the repeat-run behavior.

## Path Rules

- Convert persisted workspace paths to POSIX strings when storing them in manifests or API responses.
- Store paths relative to `workspace.root` when possible.
- Resolve and containment-check user-provided paths before serving files or writing outputs.
- Do not auto-create workspaces from read-only API endpoints; `_open_workspace` intentionally requires the directory to exist.

## Anti-Patterns

- Do not write JSON with `Path.write_text` when a torn write could corrupt state.
- Do not let a translation or query path update `wiki/index.md`, `wiki/papers`, or `wiki/concepts`.
- Do not expose `state/` or synthesized `wiki/` files through generic file-serving endpoints.
- Do not duplicate the workspace directory layout in frontend or Electron code.
