# XReadAgent — Scientific Research Agent with LLM-Wiki Memory

## Goal

Build a beautiful, powerful agent application for scientific researchers that combines:
1. **Literature reading & translation** — PDF reading with layout-preserving translation, similar in spirit to OpenSciReader but rebuilt from scratch with higher ambition
2. **LLM-Wiki memory framework** (Karpathy pattern) — persistent, compounding markdown wiki that the LLM maintains autonomously, rather than ephemeral RAG
3. **Agent layer (LangChain / LangGraph era)** — Q&A, summarization, cross-paper analysis, research planning, all grounded in the wiki

The product is for individual researchers (and eventually research teams) who want their reading to **compound** into a navigable second brain, instead of being lost in a folder of PDFs.

## What I already know

### From user
- This is a **full rewrite** — OpenSciReader is a feature reference only, NOT a starting codebase. The user explicitly said "OpenSciReader 远没有达到我的预期，因此我想重新设计项目，重写一个".
- The "LLM Wiki" concept refers specifically to **Karpathy's pattern** (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), not a generic RAG knowledge base.
- Modern agent framework preferred — "LangChain 这种" — implies Python ecosystem is acceptable / preferred.
- Aesthetic matters: "美观，功能强大".
- **Python-heavy stack confirmed** ("综上所述会更多的使用到python").
- **markitdown** (https://github.com/microsoft/markitdown) is the chosen document → markdown converter (handles PDF, Word, etc., LLM-friendly output).
- **Layout-preserving translation must be a feature** — same capability OpenSciReader provided via pdf2zh / pdf2zh-next pipeline.

### From Karpathy's LLM Wiki gist
- **Three layers**: Raw Sources (immutable) / Wiki (LLM-owned markdown) / Schema (CLAUDE.md-style conventions defining how LLM maintains the wiki)
- **Three operations**: Ingest (one source touches 10-15 wiki pages), Query (synthesis from wiki, with valuable answers filed back), Lint (find contradictions, orphans, stale claims)
- **Navigation layer**: `index.md` (content catalog) + `log.md` (append-only ledger of ingests/queries/maintenance)
- Core insight: synthesis happens **once** and compounds — RAG re-derives synthesis every query and never compounds.

### From OpenSciReader (reference points worth borrowing)
- PDF layout-preserving translation pipeline (Go orchestration + Python `pdf2zh` worker) — feature pattern, not architecture
- Workspace knowledge layer with `raw/` `wiki/` `schema/` structure — already matches Karpathy's framing, validates the approach
- Memory distillation: entities / claims / tasks / relations as first-class types
- Multi-provider LLM integration (OpenAI-compat, DeepL, Gemini, Azure, GLM-4V for OCR)
- Zotero integration for reference management
- Copilot sidebar with Ask / Answer / Evidence / Promote workflow
- **Failure modes per user**: not beautiful enough, not powerful enough — the new product must significantly raise the bar on both UX and intelligence

### Current repo state
- `G:/0JHX-code/Project/XReadAgent/` is essentially empty (only Trellis scaffolding + AGENTS.md)
- This is a greenfield project — no legacy code to maintain compatibility with

## Assumptions (temporary — to validate)

- A1. Target user: primarily individual researchers initially, possibly small teams later. NOT enterprise / institution-scale yet.
- A2. Primary platform: Windows desktop first (user is on Windows 11), with cross-platform desirable but not blocking MVP.
- A3. Python is acceptable as the agent backend language (LangChain/LangGraph are Python-first).
- A4. The user is open to a web-frontend + Python-backend architecture if it gives the best UI quality.
- A5. The user values "agent intelligence" (good wiki, smart reasoning) more than "translation pipeline polish" — OpenSciReader nailed translation but not knowledge.
- A6. Local-first preferred: papers and wiki should live on the user's disk; cloud sync optional later.

## Open Questions

All major architectural decisions resolved in 2026-05-22 brainstorm — see `plan.md` §11 Decision Log (D1–D10). Remaining questions surface during implementation.

## Requirements

### MVP requirements (Phase 1–3)

**R-INGEST** — Ingest a paper (PDF / DOCX / PPTX / HTML) into the workspace:
- PDFs route through MinerU 3.x pipeline backend → produce `extracts/{slug}.md` + image dump + per-block JSON.
- DOCX/PPTX/XLSX/HTML route through markitdown → produce `extracts/{slug}.md`.
- LLM ingest sub-agent (deepagents) reads the extract, generates 10–15 wiki page touches (papers/, concepts/, index.md, log.md) in a single structured-output pass.
- Source archived under `raw/_processed/` after success; `state/sources.json` records contentHash for idempotent re-runs.

**R-QUERY** — Ask a natural-language question grounded in the wiki:
- Agent reads `index.md` → drills into ≤5 wiki pages → answers with `[[wiki-link]]` citations.
- Answer archived to `wiki/queries/{topic}/{date}-{slug}.md`.
- Strict isolation: query results **never** auto-modify `papers/`, `concepts/`, `index.md`, `log.md`.

**R-CRYSTALLIZE** — User-invoked promotion of a query into the wiki:
- `/crystallize <query-id>` command reads the query archive and proposes diffs to relevant `papers/` or `concepts/` pages.
- User confirms each diff before write.

**R-LINT** — User- or schedule-triggered wiki health check:
- Detect orphan pages (no inbound links).
- Detect contradictions (LLM diff over claim pairs sharing a topic).
- Detect stale claims (timestamps + LLM judgment).
- Report only; no auto-edits.

**R-TRANSLATE** — Layout-preserving PDF translation:
- BabelDOC 0.6.2 in `ProcessPoolExecutor` subprocess.
- WS stream stages: `progress_start` / `progress_update` / `progress_end` / `finish` / `error`.
- Output: mono + dual PDF (BabelDOC built-in).
- First-run download UX for ~50 MB ONNX layout model + CJK fonts.

**R-LLM-PROVIDER** — Provider-agnostic LLM access via LLMGateway:
- Settings UI configures OpenAI-compat (incl. self-hosted), Anthropic, Gemini, Ollama.
- One env var or settings toggle enables LangSmith / Pydantic Logfire tracing (off by default).

**R-UI** — Polished local-first UI:
- Phase 1–2 (weeks 1–6): React/Vite/shadcn + PDF.js served via Vite dev server in browser tab.
- Phase 3 (weeks 7+): same React app wrapped in Electron + Python sidecar.
- Three primary surfaces: PDF reader (dual-column with translated chunks), wiki browser (papers/concepts/queries), copilot sidebar (ask + answer + evidence).

**R-LOCAL-FIRST** — All sources, extracts, state, and wiki live on user's disk:
- LLM API calls are the only network dependency.
- Wiki is plain markdown — readable in any markdown viewer, Obsidian-compatible.

## Acceptance Criteria

- [ ] User can import a PDF; within 5 minutes (typical 10-page paper, GPT-4-tier LLM) the wiki contains a new `papers/{slug}.md` and updated `index.md` + `log.md`.
- [ ] `papers/{slug}.md` has the seven sections from paper-curator template (Background / Challenges / Solution / Positioning / Key Concepts / Experiments / Open Questions) with `[[wiki-link]]` to relevant concept pages.
- [ ] User can ask a natural-language question; agent returns an answer with at least one wiki-page citation; the query is archived under `wiki/queries/{topic}/`.
- [ ] Query archives never trigger writes to `papers/`, `concepts/`, `index.md`, or `log.md`.
- [ ] User invokes `/crystallize <query-id>` and the agent proposes diffs that require user confirmation before applying.
- [ ] User translates a PDF; output includes both `<name>.mono.pdf` and `<name>.dual.pdf` with preserved layout (figures in original positions, equations untranslated).
- [ ] Translation worker streams progress events to the UI via WebSocket.
- [ ] LLMGateway successfully calls each of: an OpenAI-compatible endpoint, Anthropic Claude, Google Gemini, and a local Ollama model — switching is a settings toggle.
- [ ] Smoke test: 10-paper ingest, 5 queries, 2 `/crystallize`, 1 lint run — wiki ends in a consistent state (no orphan or path-traversal violations).
- [ ] App runs offline for everything except LLM API calls; no telemetry sent without user opt-in.

## Definition of Done

- Tests: unit tests for wiki tools (read/write/index regen), integration tests for ingest pipeline (single-paper happy path + duplicate detection + LLM failure recovery), smoke test for translation worker.
- Lint / typecheck (ruff + mypy for Python, eslint + tsc for TS) green.
- License files in place: project `LICENSE` (AGPL-3.0), `NOTICE` listing third-party licenses (MinerU OSS License, markitdown MIT, BabelDOC AGPL-3.0, deepagents MIT, etc.).
- Wiki state is portable: `cd` into the workspace dir, open `index.md` in any markdown viewer or Obsidian — everything readable and linked.
- All decisions in `plan.md` §11 verifiable in code (license headers, no auto-promote, no vector tier files, MCP server not wired in Phase 1–3).

## Out of Scope (locked v1)

- Multi-user collaboration / real-time editing
- Cloud sync (workspace stays local-first; sync can be layered by user via syncthing/Dropbox)
- Mobile apps
- Plugin marketplace
- Web-search auto-ingest (paper-curator has it; we defer)
- macOS / Apple Silicon (deferred to v1.5 after `hyperscan` verification)
- Linux (deferred to v2; WebKitGTK and BabelDOC ARM concerns)
- Vector / embedding tier (`sqlite-vec` + FTS5) — deferred to Phase 4
- Automatic candidate-memory promotion (replaced by manual `/crystallize` per D4)
- Closed-source SaaS distribution (precluded by AGPL-3.0 license decision D1)

## Technical Notes

### Reference projects inspected
- `G:/0JHX-code/Project/OpenSciReader/` — Wails (Go + React) + Python worker for pdf2zh. Knowledge layer in `internal/desktop/workspace_knowledge_*.go` and `workspace_wiki_service.go`. Validated as feature reference, not architecture baseline.
- Karpathy gist: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f — defines the LLM-Wiki contract we'll implement.

### Constraints
- Windows-first development (user OS)
- Python ecosystem preferred (LangChain / LangGraph)
- Local-first storage for sources and wiki
- LLM-provider-agnostic (OpenAI-compatible API as the lingua franca, plus first-class support for Anthropic, possibly Google / local Ollama)

## Research References

(to be populated by `trellis-research` sub-agents in subsequent steps)

- [ ] `research/agent-framework.md` — LangChain vs LangGraph vs LlamaIndex vs custom (for our wiki-maintenance use case)
- [ ] `research/pdf-pipeline.md` — PDF text/layout/OCR extraction options for Python (pdf2zh-next, MinerU, Unstructured, marker, pymupdf)
- [ ] `research/desktop-shell.md` — Electron vs Tauri vs PyWebView vs Wails+Python-sidecar vs pure-web
- [ ] `research/llm-wiki-implementations.md` — existing implementations or close cousins of Karpathy's pattern (Logseq AI, Obsidian Smart Connections, mem.ai, Notion AI, etc.)
- [ ] `research/translation-strategies.md` — layout-preserving vs text-only PDF translation approaches

## Decision Log (ADR-lite)

(none yet)
