# Quality Guidelines

> Code quality standards enforced across XReadAgent's Python backend.

---

## Overview

Three commands must stay green at all times:

```
uv run ruff check .
uv run mypy backend/src
uv run pytest -xvs
```

CI will gate PRs on these. Local pre-commit is not enforced but is recommended.

Beyond automation, this doc encodes the **mandatory patterns** and **forbidden patterns** that emerged from Phases 0, 1A, and 1B-1. Future sub-agents and contributors should follow them without re-litigating.

---

## Required Patterns

### Pattern: AGPL SPDX header on every .py file

**What**: Every Python source file (including empty `__init__.py`) starts with:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
```

**Why**: XReadAgent is AGPL-3.0 by license decision D1 (see `task plan.md §11`). SPDX headers make per-file licensing auditable for downstream packagers. Missing headers fail audit and can leak into derivative work as ambiguous-license code.

**Enforcement**: `trellis-check` greps for the header on every changed `.py` file.

---

### Pattern: Pydantic 2 `_Strict` base

**What**: Every `BaseModel` uses strict mode + extra forbidden:

```python
from pydantic import BaseModel, ConfigDict

class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

class Source(_Strict):
    sourceId: str
    title: str
    contentHash: str
    ...
```

**Why**: Strict mode prevents Pydantic from silently coercing `"42"` to `42`; `extra="forbid"` catches typos at parse time instead of letting them disappear into `model_extra`. This is critical when the source of the JSON is an LLM — silent coercion masks model errors.

**Test contract**: every new schema gets a `test_X_rejects_extra_fields` assertion and a `test_X_required_fields_enforced` assertion (see `tests/test_schemas.py` for the template).

---

### Pattern: camelCase for state JSON, snake_case for agent plans / frontmatter

**What**:

| Schema family | Casing | Reason |
|---|---|---|
| `Source`, `Entity`, `Claim`, `Relation`, `Task`, `DistillationPayload` | **camelCase** | Wire-compatible with OpenSciReader's Go JSON tags. Files under `state/by-source/*.json` can be exchanged between the two products. |
| `IngestPaperPage`, `IngestConceptTouch`, `IngestPlan`, `QueryAnswer`, `CrystallizePlan`, `CitedEvidence` | **snake_case** | Idiomatic Python; consumed only by our agent code. Never written to a state JSON sidecar verbatim. |
| `PaperFrontmatter`, `ConceptFrontmatter`, `QueryFrontmatter` | **snake_case** | YAML frontmatter in markdown files. Matches `obsidian-paper-curator` template convention. |

**Why**: Mixing the two is a documented compatibility decision, not an oversight. If you find yourself adding a new schema, decide first which world it belongs to:
- "Does this get written to a `state/*.json` or `state/by-source/*.json` file?" → camelCase
- "Does this only flow between LLM and Python code?" → snake_case

---

### Pattern: Atomic write triad

**What**: All state files use the three-step write pattern in `wiki/atomic.py`:

```python
def atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.fsync(tmp.open("rb").fileno())     # actually a bit more careful — see source
    os.replace(tmp, path)                  # atomic on POSIX + Windows
```

**Why**: A crash mid-write must never leave a half-written file that future loads will silently corrupt. `os.replace` is atomic on every supported platform.

**Append variant**: `append_text_locked(path, content)` for `wiki/log.md` and `state/conversation-log.jsonl`. Uses a module-level `threading.Lock` (the Phase-1 single-sidecar assumption holds; multi-process locking is out of scope until/unless we add it).

**Forbidden alternative**: `path.write_text(...)` directly on any file under `state/` or `wiki/`. Only `extracts/` (which is regenerable cache) may use direct writes.

---

### Pattern: Planner Protocol injection

**What**: Every agent class (`IngestAgent`, `QueryAgent`, `CrystallizeAgent`) takes a `planner: Protocol | None` constructor arg. The default planner builds a real LangChain `init_chat_model(...).with_structured_output(Schema)`. Tests inject a stub planner that returns a canned schema instance — no LLM call.

```python
class IngestPlanner(Protocol):
    async def __call__(self, *, system_prompt: str, user_prompt: str) -> IngestPlan: ...

class IngestAgent:
    def __init__(self, workspace, *, model: str, planner: IngestPlanner | None = None):
        self._planner = planner or _default_planner(model)
```

**Why**: Without the Protocol seam, every test of agent behavior would need a real LLM API call. With it, ingest/query/crystallize each have ~10 fast deterministic tests covering all branches.

**Anti-pattern**: hard-coding `chat_model.invoke(...)` inside `IngestAgent.ingest`. Forces every test to mock at the wrong level.

---

### Pattern: Idempotent contentHash

**What**: `compute_content_hash(path: Path) -> str` returns sha256 of file bytes. Stored on `Source.contentHash`. The router short-circuits when:

```python
existing = sources_index.find_by_hash(hash)
if existing and extract_path.exists():
    return cached_result    # no converter call, no LLM call downstream
```

**Why**: Users will re-drop the same paper. Without this short-circuit, every re-drop costs 30s+ of MinerU and a full ingest LLM call. The orchestrator's cache-hit guard is the second layer: if the paper page already exists in `wiki/papers/`, no LLM planner is invoked even if extracts were re-computed.

**Test contract**: `test_orchestrator_cache_hit::test_planner_called_once_across_two_ingests` proves the planner is called at most once when the same file is ingested twice.

---

### Pattern: Pure `apply_*` functions

**What**: `apply_plan(workspace, plan, source) -> list[str]` (ingest) and `apply_crystallize(workspace, plan) -> CrystallizeResult` (crystallize) are **pure file-system writers**. No LLM calls. No network. No subprocess. Just: schema → files. Take inputs, produce side effects on disk, return summary.

**Why**: Pure apply functions are testable without any mocking — pass a hand-built plan, run, assert file state. The agent's planner stage is the only LLM dependency; apply is plain Python.

**Anti-pattern**: smuggling a `regenerate_summary_via_llm(...)` call into `apply_plan`. If a step needs an LLM, it belongs in the planner output (`IngestPlan` already carries final markdown), not in apply.

---

### Pattern: Lazy import of heavy deps

**What**: When a dependency has a slow import (markitdown's `magika` ONNX preload is ~30s; mineru CLI may not be installed at all), import it inside the function that needs it:

```python
def _load_markitdown():
    from markitdown import MarkItDown   # ~30s on cold cache
    return MarkItDown()

def convert_with_markitdown(...) -> ConvertResult:
    md = _load_markitdown()
    return md.convert(...)
```

**Why**: Module-level `from markitdown import MarkItDown` makes every unrelated test (and every cold sidecar start) eat the 30s. Lazy loading keeps `import xreadagent` near-instant.

**Audit**: any third-party import with > 100ms cost belongs inside the function, not at module top.

---

### Pattern: SIDECAR_READY contract (cross-layer)

**What**: When `python -m xreadagent.api --port N` starts, the FastAPI lifespan opens **before** uvicorn logs "Uvicorn running on..." and emits one line to stdout, flushed:

```
SIDECAR_READY port=59979
```

**Why**: The future Electron loader spawns the Python sidecar as a child process and polls stdout for this line to know when `/healthz` is reachable. Race-free, no time-based wait.

**Test contract**: `test_api::test_sidecar_subprocess_emits_ready_line` spawns the real `python -m xreadagent.api --port 0` subprocess, reads stdout, extracts the port, calls `/healthz`, asserts 200.

---

## Forbidden Patterns

### Don't: Auto-promote query content into the synthesis zone

```python
# WRONG — violates D4
def answer_query(...):
    answer = agent.answer(question)
    write_paper_page(workspace, answer.derived_slug, ...)   # NEVER
```

**Why**: Query archives are isolated to `wiki/queries/{topic}/...` by design. Promoting query content automatically creates a hallucination feedback loop (paper-curator's documented anti-pattern). Promotion only happens via the explicit `/crystallize` user-confirmed flow.

**Hard test**: `test_query_isolation::test_query_does_not_modify_synthesis_zone` byte-digests the synthesis zone before and after `answer_query`; asserts equality.

---

### Don't: Add an embedding / vector tier in v1

```python
# WRONG — violates D8
import sqlite_vec
import chromadb
```

**Why**: Pure-agentic navigation (read `index.md`, drill) is documented to work to ~300 papers. Adding a vector tier in v1 doubles the dependency surface and the failure modes without solving any concrete user complaint. Tier 2 (`sqlite-vec` + FTS5) is planned for Phase 4 and only after a user reports navigation limits.

**Audit**: grep for `embed|vector|sqlite-vec|faiss|chroma|lancedb|qdrant` in `backend/src/` must return zero matches in v1.

---

### Don't: Leak LangChain types out of `xreadagent.agents`

```python
# WRONG — violates the layering rule
# In xreadagent/wiki/sources.py:
from langchain_core.messages import HumanMessage   # NO
```

**Why**: The wiki layer must be usable from any agent harness, not just LangChain. If LangChain churns again, we keep the engine. Confining LC types to `agents/` makes the boundary auditable.

---

### Don't: Write to wiki files outside `wiki/atomic.py`

```python
# WRONG
(workspace.papers_dir / "x.md").write_text(content)
```

**Why**: Bypasses the atomic-write guarantee. A crash mid-write leaves half a paper page.

**Correct**: every state writer routes through `atomic_write_text` / `atomic_write_bytes` / `append_text_locked`.

---

### Don't: Write noisy comments narrating the code

```python
# WRONG — adds no information
# Loop through the sources
for source in sources:
    # Get the hash
    h = source.contentHash
    # Check if it exists
    if find_by_hash(h):
        ...
```

**Why**: well-named identifiers already convey intent. Comments should explain **why** something non-obvious is the way it is (a hidden constraint, a workaround, a subtle invariant), not narrate **what**.

---

## Testing Requirements

- **One test file per source module**: `test_<source_module>.py`. Don't combine unrelated tests.
- **Strict-mode assertions**: every schema gets `test_*_rejects_extra_fields` and `test_*_required_fields_enforced`.
- **Idempotency proofs**: cache-hit, re-ingest, deterministic regeneration each get a dedicated test.
- **Isolation contracts**: byte-digest tests for queries (Phase 1B) and the same pattern for future read-only agents (Lint, Phase 3).
- **Mock at the right level**: agent tests inject stub planners; converter tests mock the subprocess. Tools that talk to the filesystem use real `tmp_path` fixtures — don't mock the FS.
- **Heavy deps are opt-in**: tests requiring a real MinerU install live behind `@pytest.mark.mineru`. Real-LLM smoke tests will live behind `@pytest.mark.integration` (not yet introduced).

---

## Code Review Checklist

When reviewing a PR:

- [ ] Every new `.py` has the AGPL SPDX header
- [ ] Every new `BaseModel` extends `_Strict` (or has a documented reason not to)
- [ ] camelCase vs snake_case matches the schema family (state JSON vs agent plan vs frontmatter)
- [ ] No imports from `langchain*` outside `xreadagent.agents.*`
- [ ] All state writes route through `wiki/atomic.py` helpers
- [ ] New agent has a `Planner` Protocol seam + a stub-planner test
- [ ] No `embed|vector|sqlite-vec|faiss|chroma` strings appear (D8 audit)
- [ ] Comments explain WHY, not WHAT
- [ ] `uv run ruff check .` + `uv run mypy backend/src` + `uv run pytest -xvs` all green
- [ ] New runtime dep added → `NOTICE` updated with license attribution
