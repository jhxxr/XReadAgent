# Directory Structure

> How XReadAgent's Python backend is organized.

---

## Overview

XReadAgent uses **src-layout** with one root package, `xreadagent`, split into six framework-segregated subpackages. The hard rule: **LangChain / deepagents types never leak out of `xreadagent.agents`**. If a function in `xreadagent.wiki` or `xreadagent.pipeline` imports from `langchain*`, that's a layering violation.

---

## Directory Layout

```
backend/
├── src/xreadagent/
│   ├── __init__.py          Top-level re-exports (Workspace, IngestAgent, QueryAgent, ...)
│   ├── api/                 FastAPI sidecar + SIDECAR_READY contract for Electron loader
│   │   ├── main.py          /healthz, /ws/events, CORS
│   │   └── __main__.py      python -m xreadagent.api --port N entry point
│   ├── llm/                 Provider-agnostic LLMGateway (NOT used by agents — see below)
│   │   ├── gateway.py       Routes provider:model strings to BaseProvider
│   │   ├── config.py        LLMGatewayConfig
│   │   └── providers/       openai_compat (working), anthropic / gemini / ollama (stubs)
│   ├── schemas/             Pydantic 2 strict types — the wire contracts
│   │   ├── entities.py      Entity / Claim / Relation / Task (camelCase, Go-tag compat)
│   │   ├── sources.py       Source / SourcesManifest (camelCase)
│   │   └── wiki_pages.py    PaperFrontmatter / ConceptFrontmatter / QueryFrontmatter (snake_case)
│   ├── wiki/                Framework-agnostic wiki primitives. Pure Python + Pydantic.
│   │   ├── paths.py         WORKSPACE_LAYOUT, validate_wiki_path, stable_source_slug, concept_slug
│   │   ├── workspace.py     Workspace frozen dataclass + named accessors
│   │   ├── atomic.py        atomic_write_text / atomic_write_bytes / append_text_locked
│   │   ├── sources.py       SourcesIndex + compute_content_hash
│   │   ├── log.py           WikiLog (markdown) + WikiConversationLog (JSONL)
│   │   ├── pages.py         write_paper_page / write_concept_page / write_query_page
│   │   ├── index_regen.py   Deterministic index.md regeneration
│   │   └── distillation.py  DistillationPayload + save/load
│   ├── pipeline/            Document → markdown converters. Subprocess isolation for heavy deps.
│   │   ├── types.py         ConvertResult + routing constants + domain errors
│   │   ├── markitdown_converter.py   .docx/.pptx/.xlsx/.html/.epub only (PDFs raise)
│   │   ├── mineru_converter.py       .pdf via MinerU CLI subprocess
│   │   └── router.py        convert_source(workspace, raw_path) top-level entry
│   └── agents/              LangChain + deepagents land. ONLY place LC types are allowed.
│       ├── _merge.py        Shared concept-merge helper used by ingest + crystallize
│       ├── ingest_schema.py / ingest.py / orchestrator.py / tools.py
│       ├── query_schema.py / query.py / query_orchestrator.py / query_tools.py
│       ├── crystallize_schema.py / crystallize.py
│       └── prompts/         System prompts as .md files (loaded via importlib.resources)
└── tests/                   Flat. One test file per source module. No deep nesting.
    └── test_*.py
```

---

## Workspace On-Disk Layout

`Workspace` (`wiki/workspace.py`) owns nine directories. The keys are `WORKSPACE_LAYOUT` (`wiki/paths.py`):

```
{workspace}/
├── raw/                       Immutable. Original PDFs / DOCX / HTML.
│   └── _processed/            Archived sources post-ingest. Presence = "ingested".
├── extracts/                  Converter output. One .md per source + optional images/ + blocks.json.
├── state/                     Machine-readable state. Recomputable from raw + LLM.
│   ├── sources.json           SourcesIndex manifest (contentHash for idempotency).
│   ├── by-source/{slug}.json  Per-source DistillationPayload (entities/claims/relations/tasks).
│   ├── compile-summary.json   "wiki dirty?" bookkeeping.
│   └── conversation-log.jsonl JSONL of every event (ingest / query / crystallize / lint).
└── wiki/                      Human-readable. LLM-owned. The compounding artifact.
    ├── index.md               Auto-regenerated catalog (deterministic).
    ├── log.md                 Synthesis-op append-only log (ingest / crystallize / lint).
    ├── overview.md            Workspace-level summary.
    ├── open-questions.md      Aggregated from state/by-source/*.tasks.
    ├── papers/{slug}.md       Per-source paper page (7 fixed sections).
    ├── concepts/{slug}.md     Per-entity concept page (4 fixed sections).
    └── queries/{topic}/...    Archived Q&A. ISOLATED — see §queries-isolation.
```

### Workspace Accessor Discipline

Always use named accessors, never `workspace.paths["wiki_papers"]`:

```python
# Correct
ws.papers_dir / f"{slug}.md"
ws.index_md_path
ws.state_dir / "by-source" / f"{slug}.json"

# Wrong — bypasses the accessor invariants
ws.paths["wiki_papers"] / f"{slug}.md"
```

The accessor list lives in `wiki/workspace.py:125-159`. Add a new accessor there if you find yourself wanting another path; do not reach into `paths[]`.

---

## Page Section Skeletons (fixed)

Page writers in `wiki/pages.py` enforce these section sets — extra sections in input are dropped, missing sections get `_(not yet filled)_`:

| Page | Sections (in order) |
|---|---|
| Paper | Background / Challenges / Solution / Positioning / Key Concepts / Experiments / Open Questions |
| Concept | Summary / Related Papers / Related Claims / Open Questions |
| Query | Question / Answer / Sources |

Adding a section means: update the page writer, the corresponding schema (`agents/*_schema.py`), and the system prompt. All three must move together.

---

## Naming Conventions

- **Files**: kebab-case, ASCII-only.
- **Slugs (papers)**: `stable_source_slug(title, source_key)` → `kebab(title) + '-' + sha256_12(source_key)`. The 12-char suffix prevents title collisions.
- **Slugs (concepts)**: `concept_slug(canonical_name, existing)` → `kebab(canonical_name)` with `-2`, `-3`, ... on collision.
- **Test files**: `test_<source_module>.py`. One-to-one. Don't combine.
- **System prompts**: `agents/prompts/{agent}_system.md`. Loaded via `importlib.resources` — must be packaged in the wheel (see `pyproject.toml` `force-include` rule).

---

## Subpackage Layering Rule

```
api/ ──► agents/ ──► wiki/ ◄── pipeline/
              │         ▲
              └─► schemas/ (used by everyone)

           llm/ (used by api/ for plain chat; NOT used by agents/)
```

- `wiki/` and `pipeline/` must NEVER import from `agents/`, `api/`, or `langchain*`.
- `agents/` may import from `wiki/`, `pipeline/`, `schemas/`, `langchain*`, `deepagents`.
- `api/` may import from anywhere.
- `llm/` is for **plain-chat** domain code (future metadata extractor, glossary builder). The agent layer uses LangChain's `init_chat_model` directly — NOT LLMGateway. Don't bridge them.

---

## Examples

- Good module to study: `wiki/sources.py` — single responsibility, ~80 LOC, atomic + idempotent, no framework dependencies, fully unit-testable.
- Good multi-layer example: `agents/orchestrator.py` — composes `pipeline.router.convert_source` + `agents.ingest.IngestAgent.ingest` + `wiki.log.WikiConversationLog`. Reads top-to-bottom; no surprises.
