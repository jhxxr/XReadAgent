# Backend Development Guidelines

> Best practices for XReadAgent's Python backend.

---

## Overview

XReadAgent's Python backend is the **single sidecar process** that:

- Maintains the LLM-Wiki on disk (workspace under user control).
- Routes documents through markitdown / MinerU converters.
- Drives the deepagents-based ingest, query, and crystallize agents on top of LangChain 1.x.
- (Phase 2) Wraps BabelDOC for layout-preserving PDF translation in an isolated subprocess.
- (Phase 3) Wraps as an Electron desktop app. The Electron main process spawns the sidecar with `--port 0`, reads `SIDECAR_READY port=<N>` from stdout, and polls `/healthz` until 200. The renderer communicates with the sidecar over HTTP/WS on `127.0.0.1:<port>`, using `platform.ts` for dual-environment URL resolution.

It runs as a FastAPI server on `127.0.0.1:<random>` and emits the `SIDECAR_READY port=<N>` contract on stdout so the Electron loader (or a dev-mode browser tab) can find it.

All persisted state is plain markdown + JSON. **No database in v1.** See `database-guidelines.md`.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Subpackage layout, workspace on-disk contract, accessor discipline, page section skeletons | Filled (Phase 0+1) |
| [Quality Guidelines](./quality-guidelines.md) | AGPL SPDX, Pydantic strict, casing rules, atomic writes, planner Protocol, forbidden patterns | Filled (Phase 0+1) |
| [Error Handling](./error-handling.md) | Domain error types per subsystem, validate-at-boundary, graceful degradation in apply functions | Filled (Phase 0+1) |
| [Logging Guidelines](./logging-guidelines.md) | Two-stream model: `wiki/log.md` (humans, synthesis-only) + `conversation-log.jsonl` (machines, all events) | Filled (Phase 0+1) |
| [Database Guidelines](./database-guidelines.md) | File-based state model; no DB in v1; atomic writes; single-writer-per-file; idempotent contentHash | Filled (Phase 0+1) |

Cross-references:
- [`guides/cross-layer-thinking-guide.md`](../guides/cross-layer-thinking-guide.md) — for FastAPI ↔ React contracts (Phase 2+)
- [`guides/code-reuse-thinking-guide.md`](../guides/code-reuse-thinking-guide.md) — when refactoring across agents

---

## Quick Reference — Hard Rules

These are the rules a sub-agent must follow without re-litigating:

1. **AGPL-3.0-or-later SPDX header on every `.py`** (including empty `__init__.py`).
2. **`_Strict` base on every Pydantic `BaseModel`** (`strict=True`, `extra="forbid"`).
3. **camelCase for state JSON schemas** (Source/Entity/Claim/Relation/Task/DistillationPayload); **snake_case for agent plans + frontmatter**.
4. **All state writes through `wiki/atomic.py`** — never `path.write_text` directly on `state/` or `wiki/`.
5. **No LangChain imports outside `xreadagent.agents.*`** — wiki + pipeline stay framework-agnostic.
6. **No vector/embedding tier — memory is a pure LLM-Wiki.** No `embed`/`embedding`/`vector`/`sqlite-vec`/`optimum`/`transformers`/`torch`/`faiss`/`chroma` in `backend/src/` **or** in `pyproject.toml` deps. Retrieval = the agent reading `index.md` + pages + `search_wiki` (grep, via `wiki/keyword_search.py`). A sqlite-vec semantic-search tier was added in Phase 4A (`b17110c`) and **removed in v0.0.3** as a design correction: the memory model is the Karpathy LLM-Wiki (markdown pages + index, LLM-driven retrieval), **not** embeddings — and the embedding stack (torch/optimum/transformers) also bloated the desktop bundle and broke the Release build. Do not reintroduce it. The MCP `semantic_search` tool name is kept for interface stability but is now grep-backed.
7. **No auto-promote from `queries/`** — `/crystallize` is the only path. Verified by `test_query_isolation`.
8. **All agent classes take an injectable `Planner` Protocol** for tests.
9. **Idempotent `contentHash` short-circuit** at the router; cache-hit short-circuit at the orchestrator.
10. **UTC ISO 8601 with `Z` suffix** for every persisted timestamp.

---

## Phase Status

| Phase | Status | Commits |
|---|---|---|
| Phase 0 (skeleton) | Complete | `b6a0792` |
| Phase 1A (pipeline + ingest agent) | Complete | `c8a8a8c` |
| Phase 1B-1 (query agent + crystallize) | Complete | `0c59055` |
| Phase 1B-2 (React/Vite/shadcn frontend skeleton) | Complete |  |
| Phase 2A (BabelDOC translation backend + API + CLI) | Complete | (this dispatch) |
| Phase 2B (PDF.js reader + Translate dialog) | Next |  |
| Phase 3 (Electron wrapper + native integrations + packaging) | Complete | `165947c..676fd84` |
| Phase 4A (sqlite-vec semantic search) | Reverted in v0.0.3 — replaced by grep-based LLM-Wiki retrieval (see Hard Rule 6) | `b17110c` (added) |
| Phase 4B (MCP protocol integration) | Complete | `2fb0196` |
| Phase 4C (macOS Electron packaging) | Complete | `09f2334` |

See `.trellis/tasks/05-22-build-sciresearch-agent-literature-reading-knowledge-base/plan.md` for the full roadmap.
