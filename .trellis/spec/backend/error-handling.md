# Error Handling

> Domain error model for XReadAgent's Python backend.

---

## Overview

XReadAgent uses **typed domain errors at boundaries** and **graceful degradation inside `apply_*` functions**. Three principles:

1. **Errors live next to their subsystem**: `pipeline.types`, `wiki.paths`, `agents` each define their own error classes. No global `errors.py`.
2. **Boundary inputs are validated; internal code trusts its inputs**: the FastAPI handler / CLI / agent tool wrapper validates; functions inside `wiki/*` and `pipeline/*` may assume their inputs are well-formed.
3. **Apply functions degrade, don't abort**: when applying a multi-patch plan, a single bad patch must not throw away the rest. Surface the failure in the result, continue with the next patch.

---

## Error Types

### Pipeline errors — `xreadagent.pipeline.types`

| Error | Raised when | Caller does |
|---|---|---|
| `WrongConverterError` | A `.pdf` is handed to `convert_with_markitdown`, or a `.docx` to `MineruConverter`. | Re-route via the suffix router — usually a programming error in the caller. |
| `UnsupportedFormatError` | The router sees a suffix outside `.pdf / .docx / .pptx / .xlsx / .html / .htm / .epub / .md / .txt`. | Surface to user with the list of supported suffixes. |
| `MineruNotInstalledError` | `MineruConverter.convert(...)` runs but `mineru` CLI is not on PATH. | UI shows "Preparing PDF engine…" with download instructions. Don't auto-install. |
| `subprocess.CalledProcessError` (uncaught) | MinerU subprocess crashes mid-conversion. | Surface as a failed ingest with the captured stderr; the FastAPI sidecar does not crash. |

### Wiki errors — `xreadagent.wiki.paths`

| Error | Raised when |
|---|---|
| `ValueError` (with descriptive message) | `validate_wiki_path` sees `..`, absolute paths, or forbidden chars `<>:"\|?*`. |
| `ValueError` | `stable_source_slug` / `concept_slug` receive empty input. |

Wiki primitives raise `ValueError` rather than custom classes because they're internal API surface. Callers (router, agents) wrap them when surfacing to the user.

### Agent errors

Agent code intentionally avoids custom error classes for "plan was unsatisfiable" cases. Instead:

- `apply_plan` / `apply_crystallize` return their `*Result` dataclass with `files_touched` containing markers like `"[missing] wiki/papers/{slug}.md"` for patches that couldn't apply. Caller inspects the list.
- LLM planner failures (provider down, schema validation failure) propagate as `langchain_core` exceptions — caller catches and surfaces.

---

## Error Handling Patterns

### Pattern: Validate at boundary, trust internally

```python
# Boundary (api/main.py or agent tool wrapper):
def handle_ingest_request(req: IngestRequest) -> IngestResponse:
    workspace = Workspace.at(req.workspace_root)  # raises if root is invalid
    raw_path = validate_wiki_path(workspace.root, req.raw_path)  # raises if bad
    ...

# Internal (wiki/sources.py):
def add_or_update(self, source: Source) -> bool:
    # No re-validation. Trust that `source` is a well-formed Pydantic model.
    ...
```

Why: re-validating at every layer wastes cycles and dilutes the meaning of "validated". The boundary validates once; everything downstream trusts.

---

### Pattern: Degrade in apply functions, don't abort

```python
# crystallize.py — apply_crystallize behavior
result = CrystallizeResult(plan=plan, files_touched=[])
for patch in plan.paper_patches:
    target = workspace.papers_dir / f"{patch.paper_slug}.md"
    if not target.exists():
        result.files_touched.append(f"[missing] {target.relative_to(workspace.root)}")
        continue   # don't abort the whole plan
    _apply_paper_patch(target, patch)
    result.files_touched.append(str(target.relative_to(workspace.root)))
```

**Why**: A crystallize plan may legitimately mix valid + invalid patches if the LLM imagined a paper slug. Aborting on first failure punishes the user for the LLM's mistake. Surfacing the failure inline lets the UI render which patches succeeded.

**Anti-pattern**: `raise PaperNotFoundError` inside `_apply_paper_patch` and let it bubble up — wipes out everything the user was about to crystallize.

---

### Pattern: Subprocess isolation for crashing converters

```python
# MineruConverter.convert uses subprocess.Popen
# A SegFault inside the MinerU ONNX model never reaches the FastAPI process.
proc = subprocess.Popen([self._cli, "-p", str(input_path), "-o", str(output_dir), ...],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in proc.stdout:
    if progress: progress(line.rstrip())
proc.wait(timeout=timeout_s)
if proc.returncode != 0:
    raise MineruConversionError(...)
```

**Why**: heavy ML deps crash sometimes. The FastAPI sidecar must survive a single bad PDF — only the affected ingest fails. Same pattern applies to BabelDOC in Phase 2.

---

### Pattern: Path validation is the security boundary

```python
# wiki/paths.py
def validate_wiki_path(workspace_root: Path, candidate: str | Path) -> Path:
    raw = str(candidate)
    if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
        raise ValueError(f"absolute path not allowed: {raw!r}")
    if any(c in raw for c in '<>:"|?*'):
        raise ValueError(f"forbidden char in path: {raw!r}")
    resolved = (workspace_root / raw).resolve()
    if not str(resolved).startswith(str(workspace_root.resolve())):
        raise ValueError(f"path traversal blocked: {raw!r}")
    return resolved
```

**Why**: LLMs will, sooner or later, propose a path with `..` in it. Without `validate_wiki_path`, the agent could rewrite `~/.ssh/authorized_keys`. Every agent tool that takes a path argument routes through it.

---

### Pattern: Auto-repair structured output

`agents/json_planner.py` provides a JSON-mode fallback for the `IngestPlan` / `QueryAnswer` / `CrystallizePlan` structured-output path. It exists because some Anthropic-compatible proxies (notably GLM-5.1 via translation shims like `cch.xinr.de`) emit nested `list[BaseModel]` fields as JSON-encoded strings instead of real lists. Pydantic strict mode (rightly) rejects that.

When agents are constructed with `planner_method="auto"` (the default), the planner calls `with_structured_output(...).invoke()` first; on a `ValidationError` whose root cause is `list_type` (a string landed where a list was expected) the planner re-issues the request through `make_json_planner(chat)` which:

1. Asks the model to return raw JSON only (no prose, no fences).
2. Strips ```json / ``` fences if the model adds them anyway.
3. Extracts the first balanced `{...}` block when the model surrounds the JSON with prose.
4. Walks top-level fields and `json.loads`-unwraps any whose schema declares `list[BaseModel]` but whose value is a string.

The retry is observed via a one-line `[xreadagent] structured-output (tool) returned a nested list as a string; retrying with JSON-mode planner` to stderr so users debugging proxy issues see it without `-v`. `planner_method="tool"` and `"json"` force one strategy unconditionally — useful for tests and for users with known-good or known-bad providers.

---

## Common Mistakes

### Mistake: Re-validating inside loops

**Symptom**: PR adds `validate_wiki_path(...)` inside the per-source loop in `apply_plan`.

**Cause**: copy-pasted from a boundary handler.

**Fix**: validate once at the boundary (the agent tool that produced the slug), trust the rest of the call chain.

**Prevention**: code review checklist item — "does this re-validate input that's already trusted?"

---

### Mistake: Catching `Exception` blanket

**Symptom**: `try: ... except Exception: log.warning("something failed")`.

**Cause**: defensive paranoia.

**Fix**: catch the specific error (`MineruNotInstalledError`, `ValueError`, etc.) you can actually handle. Let the rest crash to a clear stack trace.

**Prevention**: `ruff` rule `BLE001` (broad-exception-caught) is enabled — if it warns, narrow the catch instead of suppressing.

---

### Mistake: Raising on missing optional file

**Symptom**: `load_distillation(workspace, slug)` raises `FileNotFoundError` instead of returning `None` for a paper that hasn't been distilled yet.

**Cause**: assumed all sources have distillation.

**Fix**: optional reads return `Optional[Payload]`. Reserve exceptions for unexpected conditions, not for "this thing doesn't exist yet".

**Prevention**: convention — any `load_*` that may return-no-data is typed `-> X | None`.

---

## API Error Responses (future, Phase 2)

When the FastAPI sidecar surfaces errors to the UI, the format will be:

```json
{
  "error": {
    "type": "MineruNotInstalledError",
    "message": "MinerU CLI not found on PATH. Install via: ...",
    "actionable": "open_settings_pdf_engine"
  }
}
```

The `actionable` field tells the UI which remediation flow to surface. Phase 2 spec will pin this contract.
