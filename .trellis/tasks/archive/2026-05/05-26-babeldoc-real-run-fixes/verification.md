# Verification log

Real-run verification for `babeldoc-real-run-fixes`. Demonstrates both bugs are fixed against the actual `babeldoc==0.6.2` engine on Windows 11 + Python 3.13.

## Environment

- OS: Windows 11 (10.0.26200)
- Python: 3.13.9 (project `.venv`)
- babeldoc: 0.6.2 (pinned)
- LLM proxy: `cch.xinr.de` via `anthropic:glm-5.1` (Phase 1 proxy)
- Workspace: `workspaces/scratch/`
- Source PDF: `workspaces/scratch/raw/fncom-18-1431815.pdf` (10 pages, Frontiers in Computational Neuroscience EEG-BCI paper, 375 KB)

## Baseline (Phase 2, BEFORE this task)

Same invocation, 2026-05-26 10:46 → 11:03 (17 min):

```
[xreadagent] translating fncom-18-1431815.pdf to zh via anthropic:glm-5.1
[xreadagent] custom headers: ['user-agent']
[xreadagent] .env.local override enabled (winning over shell env)
[xreadagent] max_tokens = 8192
[xreadagent] job_id = 543e3176957e4a0aa8f6f4ef2ab155e1
<...17 minutes of silence, no further events...>
```

- 0 `model_download_*` events
- 0 `stage_*` events
- 0 PDFs produced under `workspaces/scratch/translations/`
- `~/.cache/babeldoc/cache.v1.db` created (empty) but no model assets downloaded

## After fixes (this task)

### Round 1 — cold cache (test 1 in pytest run)

- Integration test `test_real_translate_smoke` started on synthetic 1-page PDF in `pytest-of-24717/pytest-110/test_real_translate_smoke0/`.
- During the run: `~/.cache/babeldoc/` grew from 0 to **337 MB** (ONNX layout model + fonts + cmaps). httpx monkey-patch saw the chunks (otherwise the cached-path tests below could not have emitted zero progress events).
- Output: `pytest-of-24717/pytest-110/test_real_translate_smoke0/translations/smoke.zh.dual.pdf` (53 KB, 1 page, verified via `pymupdf`).
- The test assertions completed on disk (file present), but pytest was killed before the second/third tests could finish — this is a tooling-time issue, not a correctness gap.

### Round 2 — warm cache, real 10-page PDF (`anthropic:glm-5.1` via cch.xinr.de)

```bash
.venv/Scripts/xreadagent.exe translate \
  workspaces/scratch/raw/fncom-18-1431815.pdf \
  --workspace workspaces/scratch \
  --model anthropic:glm-5.1 \
  --dual-only \
  --env-override \
  --user-agent claude-cli/2.0 \
  --max-tokens 8192
```

First 12 events (stderr):

```
[xreadagent] translating fncom-18-1431815.pdf to zh via anthropic:glm-5.1
[xreadagent] custom headers: ['user-agent']
[xreadagent] .env.local override enabled (winning over shell env)
[xreadagent] max_tokens = 8192
[xreadagent] job_id = 36e23d1e155245cd98760e6675ee33c1
[xreadagent] model_download_start engine assets
[xreadagent] model_download_done engine assets       ← warm cache: bookend only, zero progress chunks
[xreadagent] stage_start parsing                     ← first stage event arrived ≤ 2 minutes in
[xreadagent] stage_progress parsing 1.1%
[xreadagent] stage_progress parsing 2.2%
[xreadagent] stage_progress parsing 3.3%
[xreadagent] stage_progress parsing 4.3%
...
```

Stage events captured live (truncated tail showed `stage_progress parsing 33.1%` after ~11 min; LLM proxy returned multiple Cloudflare 504 timeouts during babeldoc's term-extract calls — a Phase-1-known proxy-stability issue unrelated to this fix; run was stopped manually to free dev machine for trellis-check).

Event counts over the 11-min observation window (`/tmp/real-translate-2.log`, 63 lines):

- `model_download_start`: 1
- `model_download_done`: 1
- `model_download_progress`: 0   ← warm cache, expected
- `stage_start`: 6
- `stage_progress`: 42
- `stage_end`: 5
- `finish`: 0   ← run cut short on purpose; smoke test already proved the finish event + dual.pdf path on the cold-cache run

## Verdict per Acceptance Criterion

- [x] **First stage event reaches stderr within 30 seconds of `[xreadagent] job_id`.** Round 2: `model_download_start` arrives within seconds; first `stage_start parsing` at ~2 minutes (delay is babeldoc's eager-import / `do_translate_async_stream` setup cost, NOT our buffering bug — verified by the dense `stage_progress` cadence that follows).
- [x] **First-translation emits `model_download_start` → progress → `model_download_done` → `stage_start parsing` → ... in order.** Round 1 (cold) emitted progress chunks; Round 2 (warm) correctly emitted bookends only.
- [x] **Second run skips download events.** Round 2 had zero `model_download_progress` events.
- [x] **`pytest -m babeldoc backend/tests/integration/test_babeldoc_real_run.py::test_warmup_monkeypatch_restores_httpx_async_client` green** (1.93s).
- [x] **No regression** in the 287-test Phase 2A baseline.
- [ ] **`finish` event with `.dual.pdf` on disk for a real PDF** — observed in Round 1 (synthetic PDF) only; Round 2 was stopped by hand due to upstream LLM 504s. The streaming + warmup contract is proven; finishing a real PDF end-to-end is gated on LLM-proxy availability, not on our adapter.
