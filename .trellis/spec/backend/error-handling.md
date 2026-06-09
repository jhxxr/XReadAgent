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

### Pattern: HTTP file-serving endpoint security

#### Scope / Trigger

Any FastAPI route that serves bytes from inside a workspace to the browser — currently `GET /api/workspaces/file`, but the pattern is the canonical template for future "serve a workspace artifact" endpoints (extract markdown, raw source PDF, log tails, etc.). Triggered because this is a new cross-layer contract + filesystem boundary, and a leak here is a path-traversal CVE.

#### Signature

```python
@app.get("/api/workspaces/file")
async def workspace_file_endpoint(
    workspacePath: str = Query(...),    # camelCase query param to match wire contract
    path: str = Query(...),              # workspace-relative path
) -> FileResponse: ...
```

#### Contract

| Field | Type | Constraint |
|---|---|---|
| `workspacePath` | `str` | absolute path to an existing directory; opened via `Workspace.at(...)` |
| `path` | `str` | workspace-relative; first segment must be in the allowlist |

Response body: raw file bytes; `Content-Type` is `application/pdf` for `.pdf` else `application/octet-stream`. No JSON envelope — browsers consume this directly via `<embed>` / PDF.js worker.

#### Validation & Error Matrix

| Condition | Status | Detail |
|---|---|---|
| `workspacePath` empty / not a directory | 400 | `workspacePath is required` / `... is not an existing directory: <path>` |
| `path` empty | 400 | `path is required` |
| `path` absolute or starts with `/` / `\` | 400 | `path must be workspace-relative` |
| Resolved path escapes the workspace root (`relative_to` fails) | 400 | `path escapes workspace` |
| First segment of resolved path NOT in `_FILE_ALLOWLIST = {"translations", "raw", "extracts"}` | 403 | `reading from <root> is not permitted; allowed roots: [...]` |
| Resolved path missing or not a regular file | 404 | `file not found` |

#### Good / Base / Bad

- **Good**: `path=translations/foo.dual.pdf` → 200 + PDF bytes.
- **Base**: `path=translations/missing.pdf` → 404 (file simply absent).
- **Bad**:
  - `path=../../etc/passwd` → 400 (escape).
  - `path=state/queries.json` → 403 (deny-list root: never expose state/wiki/logs over HTTP).
  - `path=/abs/path` → 400 (absolute path rejected before resolution).

#### Required tests (`backend/tests/test_workspace_api.py`)

- 200 + correct bytes when file exists in each allowed root.
- 400 on traversal: `..`, multiple `..`, mixed-slash variants.
- 400 on absolute path: both Unix `/abs` and Windows `C:\abs`.
- 403 on every deny-list root (`state`, `wiki`, logs at workspace root).
- 404 on missing file under an allowed root.

Assertion points: `response.status_code`, the structured `detail` string (test the contract, not the prose — match a stable token like `"escapes workspace"`).

#### Wrong vs Correct

```python
# Wrong — concatenation + existence check leaks traversal
target = workspace.root / relative
if not target.exists():
    raise HTTPException(404)
return FileResponse(target)
# `relative = "../../etc/passwd"` resolves outside root and is served.

# Correct — resolve, contain via relative_to, allowlist root segment
root = workspace.root.resolve()
resolved = (root / relative).resolve()
rel = resolved.relative_to(root)               # raises ValueError on escape
if rel.parts[0] not in _FILE_ALLOWLIST:        # deny everything else
    raise HTTPException(403, ...)
return FileResponse(resolved, media_type=...)
```

**Why the allowlist is mandatory, not just the traversal guard**: even an in-workspace file can be sensitive (`state/queries.json` contains user queries, `wiki/log.md` contains synthesis history). The pre-defined `_FILE_ALLOWLIST = {"translations", "raw", "extracts"}` is the second layer — only artifacts that are already "user-facing reading material" are reachable over HTTP. Adding a new root requires editing the allowlist, which is the review checkpoint.

> **Warning**: never weaken the allowlist into a deny-list ("allow everything except state/"). New subdirs added in the future would be silently exposed. Allow-list is the secure default.

### Pattern: PDF source path contract for reader + BabelDOC

#### Scope / Trigger

Any change that touches PDF import, paper read APIs, PDF.js reader loading, or
BabelDOC translation handoff. This is a cross-layer storage -> API -> UI ->
translation contract and must stay explicit.

#### Signatures

- `GET /api/wiki/papers?workspacePath=...` returns each paper summary with
  `sourcePath: string | null` and `sourceKind: string`.
- `GET /api/wiki/papers/{slug}?workspacePath=...` returns the same fields on
  `WikiPageResponse`.
- `POST /api/translate` still accepts an absolute filesystem `sourcePath`.
- `GET /api/workspaces/file` still accepts a workspace-relative `path`.

#### Contracts

`Source.sourcePath` in `state/sources.json` is the canonical imported-source
path. PDF import archives originals under `raw/_processed/{slug}.pdf`, so the
reader must not guess `raw/{slug}.pdf`.

| Field | Type | Constraint |
|---|---|---|
| `sourcePath` | `string | null` | workspace-relative path copied from `Source.sourcePath`; `null` when no source row exists |
| `sourceKind` | `string` | copied from `Source.kind`; empty string when no source row exists |

The renderer uses `sourcePath` in two ways:

- Original PDF display: pass workspace-relative `sourcePath` to
  `/api/workspaces/file`.
- Translation: join `workspacePath` + `sourcePath` into an absolute local path
  before posting `/api/translate`.

#### Validation & Error Matrix

| Condition | Behavior |
|---|---|
| source row missing | API returns `sourcePath: null`, `sourceKind: ""`; UI shows no-PDF state |
| `sourcePath` exists but is not `.pdf` | UI disables translation and does not call `/api/workspaces/file` for Original |
| `sourcePath` points outside allowlisted roots | `/api/workspaces/file` rejects it via existing allowlist/traversal checks |
| absolute translate `sourcePath` missing | `/api/translate` returns 422 from `TranslationService.start_translation` |

#### Good / Base / Bad

- Good: imported PDF row has `sourcePath="raw/_processed/paper-abc.pdf"`; reader
  displays that file and translation uses `<workspace>/raw/_processed/...pdf`.
- Base: imported DOCX row has `sourcePath="raw/_processed/notes.docx"`; reader
  remains reachable but says no PDF source is available.
- Bad: reader constructs `raw/{slug}.pdf`; normal imports fail because the file
  lives under `raw/_processed/`.

#### Tests Required

- Backend wiki API tests assert `sourcePath` / `sourceKind` on list and detail.
- Frontend reader tests assert the PDF.js URL uses the canonical
  `raw/_processed/...pdf` path and non-PDF sources disable translation.
- Translate API tests assert missing absolute source paths return 422.

#### Wrong vs Correct

```typescript
// Wrong: filename convention drift.
sourcePath={`${workspacePath}/raw/${slug}.pdf`}

// Correct: sourcePath comes from state/sources.json through the paper API.
sourcePath={joinWorkspacePath(workspacePath, paper.sourcePath)}
```

### Pattern: Factory-created translation services must map back to WS jobs

#### Scope / Trigger

Any change to `create_app()`, `python -m xreadagent.api`, or
`/api/translate` + `/ws/jobs/{job_id}` wiring.

#### Signatures

```python
create_app(
    *,
    translation_service: TranslationService | None = None,
    translation_service_factory: Callable[[Workspace], TranslationService] | None = None,
) -> FastAPI
```

#### Contracts

Tests may pin one `translation_service`, but production uses
`translation_service_factory` because the active workspace is only known from
the request body. Factory-created services are cached per resolved workspace
root, and every started `job_id` is mapped back to the service that created it.
The websocket handler must resolve the service by job id; otherwise production
jobs start successfully but `/ws/jobs/{job_id}` closes with "translation service
not configured".

#### Validation & Error Matrix

| Condition | Behavior |
|---|---|
| pinned service exists | both POST and WS use the pinned service |
| factory exists, first workspace request | create and cache a service for that workspace root |
| factory exists, repeated same workspace | reuse cached service |
| factory exists, second workspace | create a distinct service |
| WS job id has no pinned or mapped service | close with 1008 configured-service error |
| mapped service rejects unknown job | send an `error` frame with `unknown job_id` |

#### Good / Base / Bad

- Good: `POST /api/translate` with workspace A starts job `j1`; `/ws/jobs/j1`
  streams from workspace A's service.
- Base: tests inject a pinned stub service and no factory.
- Bad: `POST` uses a factory but `WS` reads only `app.state.translation_service`;
  the user sees a job id but no progress stream.

#### Tests Required

- API tests assert factory services are cached per workspace root.
- Entrypoint tests assert `_build_server()` wires a real factory.
- Translate API tests assert factory-created jobs can stream events over WS.

#### Wrong vs Correct

```python
# Wrong: works only for pinned-test service.
service = app.state.translation_service

# Correct: preserve the job -> service association established by POST.
service = _resolve_translation_service_for_job(app, job_id)
```

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
