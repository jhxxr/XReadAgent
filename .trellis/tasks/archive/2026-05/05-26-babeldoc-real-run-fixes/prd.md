# BabelDOC real-run fixes — streaming + warmup init + integration test

## Goal

Make `xreadagent translate` actually translate a PDF end-to-end against the real BabelDOC 0.6.2 engine, with real-time stage events streaming over WS. Phase 2 shipped a feature that passes 274 unit tests but cannot complete a single real translation; this task closes that gap and adds an integration test so the gap can never reopen unseen.

## What I already know

### From Phase 2 verification (2026-05-26)

- `.venv/Scripts/xreadagent.exe translate workspaces/scratch/raw/fncom-18-1431815.pdf --workspace workspaces/scratch --model anthropic:glm-5.1 --dual-only --env-override --user-agent claude-cli/2.0 --max-tokens 8192` was launched and ran for 17 minutes with **zero stage events emitted**, **zero PDFs produced**, and only an empty `cache.v1.db` created in `~/.cache/babeldoc/`. No huggingface model files downloaded.

### Bug A — streaming defeated by buffering

`backend/src/xreadagent/translation/babeldoc_adapter.py:486-531` (`_build_babeldoc_source`):

```python
async def _collect() -> list[dict[str, Any]]:
    buffer: list[dict[str, Any]] = []
    async for raw in do_translate_async_stream(bcfg):
        if isinstance(raw, dict):
            buffer.append(raw)
    return buffer

events = asyncio.run(_collect())
return iter(events)
```

`asyncio.run(_collect())` blocks until the **entire** BabelDOC pipeline finishes before any event reaches the worker queue. Violates PRD R-TRANSLATE-BACKEND ("WS streams stage events") and the Q3 ADR ("Detailed stage events. 1:1 mapping to BabelDOC's 13-stage pipeline."). The original code comment acknowledges the trade-off: *"mixing async + sync generator semantics across the asyncio bridge is fragile under pytest's event-loop policy."* — so any fix must keep the unit tests stable AND stream in real time.

### Bug B — `init()` + `warmup()` never called

BabelDOC 0.6.2's contract (verified by reading `.venv/Lib/site-packages/babeldoc/`):

- `babeldoc.format.pdf.high_level.init()` → `create_cache_folder()` (cheap).
- `babeldoc.assets.assets.async_warmup()` / `warmup()` → downloads ONNX model + fonts + cmaps (~80 MB) via `httpx` + `asyncio.gather`. **No progress callbacks.**

Our adapter calls neither. BabelDOC's `do_translate_async_stream` then either hangs waiting for missing assets or fails silently mid-pipeline. PRD Q4 specifies first-run download events emit through the same WS stream as `model_download_start` / `_progress` / `_done`, but BabelDOC gives us **no native progress hooks** — we either accept granularity loss (start/done only) or monkey-patch `httpx`.

### Bug C — test-strategy gap

All 274 Phase 2A backend tests inject canned events:

- `babeldoc_adapter.py` tests use `raw_event_source=` to bypass `_build_babeldoc_source`.
- `worker.py` tests monkey-patch `_worker_entry` to skip BabelDOC entirely.
- `service.py` / `translate_api.py` tests stub the worker.

Both bugs above passed `ruff + mypy strict + pytest -x -q` green. There is **no test that actually loads the real `babeldoc` package** through our adapter surface. We need at least one integration test, gated behind `@pytest.mark.babeldoc`, that exercises `init()` + `warmup()` + a minimal `do_translate_async_stream` round-trip so this class of bug surfaces in CI (when the marker is enabled locally).

### Environment data point (not a blocker)

`from babeldoc.format.pdf import high_level` takes >60s on Windows + Python 3.13 + babeldoc 0.6.2 — eager midend module loading (ONNX runtime + 30+ submodules). Affects subprocess spawn latency: every fresh `xreadagent translate` invocation pays this cost. Worth measuring; possibly worth pre-warming inside the sidecar process so the user-visible wait is at sidecar startup, not at job start.

## Assumptions (to validate)

- A1. ~~We're willing to accept **coarse-grained model-download events**~~ — **superseded by Q2**: per-chunk progress via monkey-patched `httpx.AsyncClient`.
- A2. The streaming fix lives **entirely inside `_build_babeldoc_source`** — the worker's queue contract (`event_queue.put(dict)`) and the test surface (`raw_event_source=` injection) stay unchanged.
- A3. The integration test runs **on-demand only** (`pytest -m babeldoc`), not in default CI. Requires a real fixture PDF + a working LLM provider env, both of which complicate CI. Local dev + pre-release checks gate on it.
- A4. **Pre-warming at sidecar startup** is out of scope for v1 — leave it as a Phase 3 optimization once we have a startup banner.

## Open Questions

See "Decision Log" once we converge.

## Decision Log (ADR-lite)

### Q1 — Bug A streaming fix shape

- **Decision**: **Threaded event loop inside the adapter.** `_build_babeldoc_source` spins up a daemon thread that owns its own `asyncio.new_event_loop()`, runs `do_translate_async_stream`, and pushes each dict onto a `queue.Queue` as it arrives. The outer sync iterator drains the queue.
- **Consequences**: Zero changes to `worker.py`, the existing `raw_event_source=` injection point, the `event_queue` contract, or the trellis-checked code shape. Pytest event-loop policy stays unaffected because the asyncio loop is private to the thread. Trade-off: two queues inside the subprocess (thread queue → mp queue) with negligible overhead.

### Q2 — Warmup download progress granularity

- **Decision**: **Per-chunk progress events via scoped httpx monkey-patch.** Adapter wraps `babeldoc.assets.assets.httpx.AsyncClient` for the duration of the warmup call so each chunk received emits a `model_download_progress` event with `bytes_downloaded` / `bytes_total`. Monkey-patch is restored on exit (try/finally) so it can't leak.
- **Consequences**: Real progress bar in the UI during first-run download. Coupled to BabelDOC's internal httpx usage — a future BabelDOC version that switches to `requests` or a different HTTP lib would silently drop progress events (the translate itself still works). Integration test must cover both the monkey-patched + restored states.

### Q3 — Integration test scope

- **Decision**: **Identity translator + synthetic PDF.** Test uses `lambda text, src, tgt: text` as the translator callable and a 1-page PDF generated in `tests/fixtures/conftest.py` via `pymupdf`. Assertions: `init()` + `warmup()` succeed, stage events arrive in order, `{slug}.dual.pdf` lands on disk with page_count ≥ 1, no exceptions.
- **Consequences**: Fast (no LLM call, no network for translation), fully reproducible, no API keys required, no binary fixtures checked in. Trade-off: the LLMGateway → BabelDOC translator-callable adapter layer is NOT covered by this test — that path stays unit-tested only. Reopen with a `babeldoc_llm` marker if real-LLM coverage proves necessary.

### Q4 — Warmup timing

- **Decision**: **Warmup runs at first translate**, inside the adapter, with events flowing on the job's WS stream. A4 confirmed.
- **Consequences**: First-translate user waits 30-90s for the asset download with a real progress bar. Subsequent translates skip download events entirely (assets cached). No startup-banner UI is required in this task — that's a Phase 3 concern when we have the broader engine-readiness surface.

## Implementation Plan (3 sequential dispatches)

### Phase 2A — Streaming fix (`_build_babeldoc_source` → threaded loop)

1. Rewrite `_build_babeldoc_source` to spin up a daemon thread with `asyncio.new_event_loop()`, run `do_translate_async_stream`, push each dict to a `queue.Queue`, sentinel-terminate.
2. Outer sync iterator drains the queue, yields dict-by-dict, exits on sentinel.
3. Update existing unit tests if any assert on buffered-list semantics. The `raw_event_source=` injection path stays untouched.

### Phase 2B — Warmup init + per-chunk progress events

1. Adapter wraps `babeldoc.format.pdf.high_level.init()` (idempotent, cheap, no events).
2. Adapter wraps `babeldoc.assets.assets.warmup()` inside a scoped monkey-patch:
   - Save original `babeldoc.assets.assets.httpx.AsyncClient`.
   - Install a subclass that wraps `.stream()` / `.iter_bytes()` to count bytes and call a progress callback.
   - Callback emits `model_download_progress` dicts onto the same `queue.Queue` from 2A.
   - Restore original on exit (try/finally) — no leak.
3. Emit `model_download_start` once before warmup, `model_download_done` once after success, `ErrorEvent` on failure.
4. Detect already-cached path: if `~/.cache/babeldoc/` already has the ONNX + fonts, warmup completes in <1s and no httpx requests fire — the monkey-patch sees zero chunks so no progress events emit. Test this branch.

### Phase 2C — Integration test

1. Register `@pytest.mark.babeldoc` in `pyproject.toml` `[tool.pytest.ini_options].markers` (mirrors existing `mineru` marker).
2. New `backend/tests/integration/__init__.py` + `backend/tests/integration/test_babeldoc_real_run.py`.
3. Test body: generate 1-page PDF via pymupdf into `tmp_path`, build `AdapterConfig` pointing at it, build identity translator, call `iter_translation_events`, assert stage events arrived in order + dual PDF landed on disk.
4. Update `backend/tests/README.md` (or `.trellis/spec/backend/quality-guidelines.md`) with the opt-in command: `pytest -m babeldoc backend/tests/integration/`.
5. Manual real-run verification: append `verification.md` to the task dir with the actual CLI invocation + first/last 30 lines of stderr + page count.

### Phase 2D — Verification + commit

1. `pytest backend/ -x -q` — full suite (excluding integration marker) stays green.
2. `pytest -m babeldoc backend/tests/integration/ -x -q` — new integration test green.
3. `ruff check backend/` + `mypy --strict backend/src/xreadagent/translation` — green.
4. Manual `xreadagent translate workspaces/scratch/raw/fncom-18-1431815.pdf --workspace workspaces/scratch --model anthropic:glm-5.1 --dual-only --env-override --user-agent claude-cli/2.0 --max-tokens 8192` — first event within 30s, dual.pdf on disk at finish.

## Requirements

**R-STREAM-FIX**:
- `_build_babeldoc_source` MUST yield each `dict` from `do_translate_async_stream` **as it arrives**, not after the pipeline completes.
- Worker queue receives the first event within seconds of job start (not after the whole pipeline finishes).
- Existing tests injecting `raw_event_source=` continue to pass unchanged.

**R-WARMUP-INIT**:
- Adapter calls `babeldoc.format.pdf.high_level.init()` before constructing `TranslationConfig`.
- Adapter calls `babeldoc.assets.assets.warmup()` (or `async_warmup()` in the async path) before `do_translate_async_stream`.
- Warmup is wrapped so it emits **one** `model_download_start` event before the call, **per-chunk** `model_download_progress` events with `bytes_downloaded` / `bytes_total` (via a scoped monkey-patch on `babeldoc.assets.assets.httpx.AsyncClient` that wraps `.stream()` / `.iter_bytes()` responses), and **one** `model_download_done` event after success. On warmup failure, an `ErrorEvent` is emitted with the exception detail.
- The monkey-patch is **scoped** — installed inside the adapter's warmup wrapper and torn down on exit, not at module load — so it doesn't leak into other code paths or other tests.
- Warmup is **idempotent across runs**: a second `translate` invocation in the same workspace should see warmup complete near-instantly (assets cached on disk; BabelDOC's own cache handles this — verify, don't reimplement). In the cached path the wrapper emits **no** `model_download_*` events (no httpx download to instrument).

**R-INTEGRATION-TEST**:
- New marker `@pytest.mark.babeldoc` registered in `pyproject.toml` (alongside the existing `mineru` marker).
- One test: `backend/tests/integration/test_babeldoc_real_run.py::test_real_translate_smoke`. Loads real `babeldoc`, calls `init()` + `warmup()`, runs `do_translate_async_stream` on a tiny fixture PDF (≤2 pages, no LLM call — use an identity translator `lambda text, src, tgt: text`), asserts that the dual PDF lands on disk and that stage events arrived in order.
- Default `pytest backend/` skips it; `pytest -m babeldoc backend/` runs it.
- README + `backend/tests/README.md` (or `quality-guidelines.md`) documents how to opt in.

## Acceptance Criteria

- [ ] On a real run (`xreadagent translate <real PDF> --workspace <ws> --model <provider:model>`), the first stage event reaches stderr within 30 seconds of `[xreadagent] job_id = ...` (used to be: never).
- [ ] Same real run completes within reasonable time and writes `{ws}/translations/{slug}.dual.pdf` (and `.mono.pdf` if `--both`).
- [ ] First-translation run emits `model_download_start` → ... → `model_download_done` → `stage_start parsing` → ... → `finish` in order; second run (cache warm) skips the download events.
- [ ] `pytest -m babeldoc backend/` runs the integration test green; `pytest backend/` (default) still passes with the integration test skipped.
- [ ] No regression in the 274 existing Phase 2A backend tests.

## Definition of Done

- ruff + mypy strict + `pytest backend/ -x -q` green.
- `pytest -m babeldoc backend/ -x -q` green on a dev machine with `babeldoc==0.6.2` installed.
- One manual verification log captured in the task dir: `verification.md` with the real CLI invocation + first/last 30 lines of stderr + the resulting `dual.pdf` page count + manifest entry.
- No changes to the API wire schema (`POST /api/translate`, WS event payloads) — frontend ships unchanged.

## Out of Scope (v1)

- ~~Per-byte download progress~~ — superseded by Q2: shipping per-chunk progress via scoped httpx monkey-patch.
- **Sidecar-startup pre-warm**: would amortize the 60s `high_level` import across many translate calls; revisit in Phase 3 when there's a startup banner UI.
- **Recovering from `hyperscan` ARM-wheel issues on Apple Silicon**: PRD Phase 2 already deferred to v1.5; nothing changes here.
- **CI-side integration test**: the integration test runs on dev machines only — wiring it into GitHub Actions / etc. is a separate ops task.

## Technical Notes

- `_build_babeldoc_source` fix candidates:
  - **Threaded event loop**: run `do_translate_async_stream` in a background thread with its own `asyncio.new_event_loop()`, push each event onto a `queue.Queue`. Yield from the queue synchronously. Avoids the pytest event-loop policy headache because the loop is private to the thread.
  - **`asyncio.run_coroutine_threadsafe` + pump**: similar shape, more boilerplate.
  - **Just remove the sync iterator entirely**: the worker is already running in a subprocess; let it call `asyncio.run` directly inside `_worker_entry` and iterate the async generator there. Requires restructuring worker.py — bigger blast radius.
- Reference: BabelDOC's own `babeldoc/main.py` does `asyncio.run(...)` over its high-level entry — that's the pattern to mirror in the worker subprocess.
- Integration test fixture: smallest legal PDF is ~700 bytes (one empty page). For a meaningful smoke we want 1-2 real pages — generate via `pymupdf` in a fixture (`tests/fixtures/conftest.py`) so we don't check a binary into the repo.
- `pyproject.toml` `[tool.pytest.ini_options].markers` already has `babeldoc`-style register pattern (see existing `mineru` marker).

## Research References

- `[archived] research/layout-translation.md` (Phase 1 task) — full BabelDOC 0.6.2 API surface, AGPL implications, 13-stage pipeline, ProcessPoolExecutor + spawn-method requirement.
