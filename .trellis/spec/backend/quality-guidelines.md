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

**Startup-path contract (since the 06-10 optimization task)**: the sidecar import path — `import xreadagent`, `xreadagent.api.main`, `xreadagent.cli.main` — must stay **langchain-free**. The package roots (`xreadagent/__init__.py`, `agents/__init__.py`) re-export agent names via PEP 562 `__getattr__` + `TYPE_CHECKING` blocks instead of eager imports (eager imports cost ~0.4s warm / ~78s cold-first-run and threatened the 30s Electron sidecar timeout). Agent imports in `api/` and `cli/` live inside route handlers / job runners / subcommand `run()` bodies.

```python
# WRONG — defeats the whole lazy-export setup (in any api/ module)
from xreadagent.agents.ingest import IngestAgent

# Correct — import where it runs
def _default_runner(...):
    from xreadagent.agents.ingest import IngestAgent
    ...
```

**Enforcement**: `backend/tests/test_lazy_imports.py` subprocess-imports the three entry modules and fails if any `langchain*/langgraph*/deepagents*/langsmith*` module lands in `sys.modules`. New api/cli modules reachable from those entry points are automatically covered.

---

### Pattern: Background job + `/ws/jobs/{job_id}` progress contract

**What**: Long-running operations (anything that can take more than a couple of seconds: LLM agent runs, BabelDOC translation) must NOT block their POST handler. The established pattern — implemented twice now (`translation/service.py` + `api/ingest_jobs.py`) — is:

1. `POST /api/<op>` validates, starts the job, returns `{"jobId": "<uuid4hex>"}` immediately (camelCase REST body).
2. Events stream over the shared `WS /ws/jobs/{job_id}` channel, resolved in `api/main.py::_resolve_job_event_source` (per-op job map, exact-id lookup).
3. Event payloads are **snake_case** (matching `translation/events.py`): `stage_start` / `stage_end` / `finish` / `error`; `error` reuses the translation `ErrorEvent` shape (`stage`, `message`, `traceback_excerpt`).
4. Events are buffered per job and **replayed to late subscribers** (a fast-finishing job must not strand the UI).
5. Failures append a `<op>_error` record to `state/conversation-log.jsonl`.

**Why**: One job/WS convention means the frontend has a single subscription helper shape (`lib/ingest-job.ts` mirrors `translate-dialog.tsx`) and the contract stays auditable. A second convention would double the failure modes at the hardest boundary we have.

**Tests required** (see `test_ingest_job_service.py` / `test_ingest_jobs_api.py` for the template): event ordering, error event + conversation-log record, late-subscriber replay, WS resolution precedence, and — if the runner imports agents — the lazy-import guard staying green.

**Anti-pattern**: a new long-running endpoint returning its result synchronously "because it's usually fast", or inventing a bespoke polling endpoint instead of the shared WS channel.

---

### Pattern: SIDECAR_READY contract (cross-layer)

**What**: `python -m xreadagent.api --port N` first prints `SIDECAR_BOOT` (flushed, stdlib-only — before the heavy uvicorn/FastAPI imports) as a liveness marker; then the FastAPI lifespan opens **before** uvicorn logs "Uvicorn running on..." and emits the ready line, flushed:

```
SIDECAR_BOOT
SIDECAR_READY port=59979
```

**Why**: The Electron loader spawns the Python sidecar as a child process and polls stdout for these lines. `SIDECAR_BOOT` lets it tell a slow import chain (first launch under antivirus scanning — minutes) apart from a hung process; `SIDECAR_READY` says `/healthz` is reachable. Race-free, no time-based wait. This requires `xreadagent/api/__init__.py` to stay a **lazy (PEP 562) re-export** of `create_app` — `python -m` imports the package before `__main__` runs, so an eager re-export would delay the boot marker by the whole FastAPI/pydantic chain.

**Test contract**: `test_api::test_sidecar_subprocess_emits_ready_line` spawns the real `python -m xreadagent.api --port 0` subprocess, asserts `SIDECAR_BOOT` is the first stdout line, extracts the port from the ready line, calls `/healthz`, asserts 200. `test_lazy_imports::test_import_api_package_root_stays_light` pins the lazy package root.

---

### Pattern: Auto-inject infrastructure metadata in `apply_plan`

**What**: After the planner returns its `IngestPlan` and before `save_distillation`, `apply_plan` populates the infrastructure metadata fields on every Entity / Claim / Relation / Task that the LLM left blank: `workspaceId` (defaults to the workspace root's directory name), `createdAt` / `updatedAt` (UTC ISO 8601 with `Z`), `origin` (`ingest:{source.id}`), `status` (`active`). The LLM is asked for *content* (title, summary, entityIds, sourceRefs), never for *infra* facts it cannot know correctly.

Same pattern applies to `ConceptFrontmatter.type` — defaulted to `"concept"` in `apply_plan` when the LLM leaves it empty, because the field exists for future "type of concept page" extensibility, not as a meaningful prompt for v1 models.

**Why**: Asking the LLM for `workspaceId` produces either `""` (because it sees no workspace context in the prompt) or hallucinations. Asking for `createdAt` produces inconsistent date formats. The right separation is: planner emits the bits the LLM is good at (judgments about entities and claims), `apply_plan` fills the bits the runtime knows authoritatively.

**Test contract**: `test_apply_plan::test_apply_plan_auto_injects_infrastructure_metadata` asserts every collection item has populated metadata after a roundtrip. `test_apply_plan_defaults_concept_type_to_concept` pins the concept-type default.

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

### Don't: Leak LangChain types out of `xreadagent.agents` (+ `xreadagent.translation`)

```python
# WRONG — violates the layering rule
# In xreadagent/wiki/sources.py:
from langchain_core.messages import HumanMessage   # NO
```

**Why**: The wiki layer must be usable from any agent harness, not just LangChain. If LangChain churns again, we keep the engine. Confining LC types to `agents/` makes the boundary auditable.

**Phase 2A carve-out**: `xreadagent.translation` is also allowed to import `langchain*` because it builds the BabelDOC translator callable on top of a LangChain chat model (D2 from the Phase 2 PRD). The translation package is the *only* other entry point allowed to touch LangChain; `wiki/`, `pipeline/`, `schemas/`, `llm/`, `cli/` (except for re-exports of agent / translation classes) stay framework-agnostic.

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
- **Module-global patching for settings paths**: when a module uses a top-level constant like `_SETTINGS_FILE = Path.home() / ".xreadagent" / "settings.json"`, tests redirect it via `monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", tmp_path / "settings.json")` and `monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)`. This avoids touching the real home directory and keeps tests hermetic.
- **Heavy deps are opt-in**: tests requiring a real MinerU install live behind `@pytest.mark.mineru`; the BabelDOC engine smoke test lives behind `@pytest.mark.babeldoc` under `backend/tests/integration/`. Default `pytest backend/` skips both. See `backend/tests/README.md` for the full marker table + opt-in commands. Real-LLM smoke tests will live behind `@pytest.mark.integration` (not yet introduced).

---

## Code Review Checklist

When reviewing a PR:

- [ ] Every new `.py` has the AGPL SPDX header
- [ ] Every new `BaseModel` extends `_Strict` (or has a documented reason not to)
- [ ] camelCase vs snake_case matches the schema family (state JSON vs agent plan vs frontmatter)
- [ ] No imports from `langchain*` outside `xreadagent.agents.*` and `xreadagent.translation.*`
- [ ] Sidecar startup path stays langchain-free: no module-level agent imports in `api/`/`cli/`; `test_lazy_imports.py` green
- [ ] New long-running endpoint follows the job + `/ws/jobs` progress contract (no blocking POST)
- [ ] All state writes route through `wiki/atomic.py` helpers
- [ ] New agent has a `Planner` Protocol seam + a stub-planner test
- [ ] No `embed|vector|sqlite-vec|faiss|chroma` strings appear (D8 audit)
- [ ] Comments explain WHY, not WHAT
- [ ] `uv run ruff check .` + `uv run mypy backend/src` + `uv run pytest -xvs` all green
- [ ] New runtime dep added → `NOTICE` updated with license attribution
