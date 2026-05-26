# Phase 2 — BabelDOC layout-preserving translation + PDF reader

## Goal

Add **layout-preserving PDF translation** (BabelDOC 0.6.2) as a subprocess-isolated worker that streams progress to the frontend, and a **dual-column PDF.js reader** that lets researchers compare original and translated PDFs side-by-side. Together: drop a non-English paper in, click "translate", get a beautifully laid-out bilingual reading experience grounded in the same workspace as the LLM-Wiki ingest.

## What I already know

### From Phase 1 (archived `.trellis/tasks/archive/2026-05/05-22-build-sciresearch-agent-literature-reading-knowledge-base/`)

- **plan.md §9 Phase 2** scope: "BabelDOC subprocess wrapper + WS streaming · Dual-column PDF reader (PDF.js, page-replace as chunks finish) · mono + dual export · First-run translation-engine download flow." Estimated 3 weeks original; we'll likely split into 2A backend / 2B frontend.
- **research/layout-translation.md** key findings:
  - Depend on `babeldoc==0.6.2` directly (NOT `pdf2zh-next` wrapper — pdf2zh-next adds 11 unused translator backends).
  - **AGPL-3.0** — already aligned with our D1 license decision.
  - Pin tight; BabelDOC officially says "All APIs should be considered internal — direct use is not supported."
  - 13-stage pipeline: DocLayout-YOLO ONNX layout detection + per-paragraph bbox text rewrite + CJK font subset (no LaTeX rebuild).
  - Run in `ProcessPoolExecutor` worker (BabelDOC's own reference impl uses `_translate_in_subprocess`).
  - mono + dual export built-in via `TranslationConfig.{no_mono, no_dual, use_alternating_pages_dual, watermark_output_mode}`.
  - API surface: `async_translate(config) -> TranslateResult` or `do_translate_async_stream(config)` for stage-by-stage events.
  - First-run lazy-download model assets (~50 MB ONNX + ~30–80 MB CJK fonts).
  - **Apple Silicon unverified** (`hyperscan` dep is x86-biased). Possible workaround: `vectorscan` — defer until Phase 3 macOS QA.
- **research/desktop-shell.md** key findings (still apply):
  - Dev mode = FastAPI + Vite browser tab (D5 locked).
  - Random port + SIDECAR_READY contract reserved for Phase 3 Electron production.
  - HTTP/WS over loopback (127.0.0.1) is the only frontend ↔ backend transport.

### Current code state (just committed at `950cfe9`, then archived/journaled)

- **Backend** has FastAPI sidecar at `backend/src/xreadagent/api/main.py` with `/healthz` + a placeholder `/ws/events` echo endpoint. Translation routes do NOT exist yet.
- **`pyproject.toml`** does NOT yet depend on `babeldoc`. Adding it pulls in `pymupdf` (AGPL — OK by D1), `onnxruntime`, `huggingface_hub`, `tenacity`, plus `hyperscan` indirectly. Tight pin required.
- **Frontend** has `frontend/src/routes/paper.tsx` as a stub placeholder card. No PDF rendering library yet. `package.json` does NOT yet depend on `react-pdf` or `pdfjs-dist`.
- **CLI** has `xreadagent ingest` / `query` / `show` but NO `translate` subcommand.
- **Workspace layout** (Phase 1): `raw/` (immutable sources), `extracts/` (markdown), `state/`, `wiki/`. **Translation outputs need a home** — likely `translations/{slug}.mono.pdf` + `translations/{slug}.dual.pdf` as a new top-level directory, or under `extracts/`.

## Assumptions (to validate)

- A1. Translation is **independent of ingest** at the data-flow level — translating a PDF does NOT trigger ingest, and ingesting a PDF does NOT trigger translation. They share the workspace but not the lifecycle. (Confirmation needed; see Q1.)
- A2. Initial language support: any language → **simplified Chinese (zh-CN)** as the primary target; English source is the most common case but BabelDOC supports many source languages.
- A3. The user wants a **PDF reader inside the app**, not a "translate and download" flow — meaning we need PDF.js rendering integrated into the frontend.
- A4. **Translation engine asset download is a one-time first-use step** with clear UI (similar to "Preparing engine…" pattern used by Reor / LM Studio / Ollama). Per D3 locked decision.
- A5. **`workspaces/{ws}/translations/` is the canonical output dir.** Slug matches the source — `{slug}.mono.pdf` (translated only) + `{slug}.dual.pdf` (alternating pages original/translation).
- A6. **The WS protocol is asymmetric** — server pushes events; client only sends a "subscribe to job ID" request. No client-to-server commands over WS (those use REST POST).

## Open Questions

All major architectural decisions resolved in 2026-05-25 brainstorm — see "Decision Log" below.

## Requirements

**R-TRANSLATE-BACKEND**:
- `POST /api/translate` accepts `{workspace_path, source_path, target_lang, model, mono, dual}` → returns `{job_id}`.
- `GET /ws/jobs/{job_id}` streams stage events (one of: `model_download_start` / `model_download_progress` / `model_download_done` / `stage_start` / `stage_progress` / `stage_end` / `finish` / `error`) with full stage payloads (page numbers, percent, paths).
- BabelDOC runs in `ProcessPoolExecutor` worker (spawn start method on Windows; subprocess isolation per `quality-guidelines.md` "Subprocess isolation for crashing converters").
- LLMGateway provides the translation callable, threaded into BabelDOC via config dict (api_key + base_url + model + default_headers + max_tokens, spawn-safe-picklable).
- Outputs: `{ws}/translations/{slug}.mono.pdf` + `{ws}/translations/{slug}.dual.pdf`.
- First-translation triggers asset download as `model_download_*` events in the same WS stream (NOT a separate install endpoint).

**R-TRANSLATE-CLI**:
- `xreadagent translate <source_path> --workspace <ws> --model <provider:model> [--target zh] [--mono-only|--dual-only|--both] [--user-agent ...] [--header ...] [--max-tokens N] [--env-override]` — mirrors `ingest` CLI.
- Print stage events to stderr; final paths to stdout.

**R-TRANSLATE-FRONTEND**:
- `/paper/$slug` stays the markdown wiki page.
- New route `/paper/$slug/read` — PDF.js reader.
- "Read in PDF" button on the wiki page navigates to `/read`.
- Reader tabs: **Original** / **Dual** / **Translated** (defaults to Dual if a dual PDF exists; otherwise Original).
- Top bar of reader has a **Translate** button. Clicking opens a small dialog (target language pre-set to zh; model dropdown reuses settings) → on confirm, POSTs to `/api/translate`, then auto-subscribes the WS stream, shows progress, swaps to Dual tab when finish event arrives.
- Engine-download events render as a "Preparing translation engine…" overlay before stage_start events begin.

**R-DATA-LAYOUT**:
- Translation outputs live under `workspaces/{ws}/translations/`. Slug matches source.
- `wiki/`, `state/`, `extracts/` are NOT touched by translation (D4-style isolation extends here).
- Translation manifest at `{ws}/translations/manifest.json` records `{source_slug, target_lang, mono_path?, dual_path?, translated_at, source_hash}` so the UI can list available translations per source.

## Acceptance Criteria

- [ ] User drops a non-English PDF into `raw/`, runs `xreadagent translate <path> --workspace …`, gets both `{slug}.mono.pdf` + `{slug}.dual.pdf` written under `translations/` within reasonable time.
- [ ] Dual PDF preserves layout — figures/equations/tables in original positions; only paragraph text replaced.
- [ ] First-translation experience: WS stream emits `model_download_start` → `model_download_progress` (3-10 events) → `model_download_done` → `stage_start parsing` → … → `finish`.
- [ ] BabelDOC subprocess crash propagates as `{type: "error", stage, message}` on WS; sidecar stays alive; other in-flight jobs unaffected.
- [ ] Re-running `translate` with the same source + target + model returns cached paths without re-running BabelDOC.
- [ ] Frontend `/paper/$slug/read` route loads `{slug}.dual.pdf` (or original if no dual exists), tab switching works.
- [ ] Translate button on `/read` POSTs `/api/translate`, WS subscribes, progress bar advances per stage event, on `finish` the page swaps to the new dual PDF.
- [ ] Wiki state remains byte-identical before/after a translation (verified by a `test_translation_isolation` test mirroring the Phase 1 D4 query isolation test).

## Definition of Done

- `babeldoc==0.6.2` pinned exactly. Bump-gate test: a smoke PDF round-trips identically before/after dependency change.
- NOTICE updated for `babeldoc` (AGPL-3.0), `pymupdf` (AGPL-3.0), `onnxruntime` (MIT), `huggingface_hub` (Apache-2.0), `pdfjs-dist` (Apache-2.0), and the layout model (DocLayout-YOLO — check upstream license; add to NOTICE).
- All Phase-1 hard rules continue to hold: AGPL SPDX, Pydantic `_Strict`, atomic writes, no LangChain outside `agents/`, no vector tier, no auto-promote, planner Protocol injection on the translation worker too.
- ruff + mypy strict + pytest green (backend); pnpm typecheck + lint + test + build green (frontend).
- New backend tests: subprocess invocation, event serialization, crash propagation, idempotent cache, LLMGateway config marshalling.
- New frontend tests: reader renders both single-PDF and dual-PDF correctly; translate dialog POST + WS sequence works (with mock backend).

## Decision Log (ADR-lite)

### Q1 — Translation × Ingest data flow
- **Decision**: **Independent flows**. Translation produces only PDFs under `translations/`. Ingest builds wiki only from the original extract. No cross-trigger.
- **Consequences**: Two separate user gestures. Wiki content is in source language (typically English). Users wanting a Chinese wiki must ingest from a translated source manually (out-of-scope v1).

### Q2 — BabelDOC LLM source
- **Decision**: **Reuse LLMGateway**. We adapt our chat client into BabelDOC's expected translator callable; provider config (api_key / base_url / headers / max_tokens) carried via spawn-picklable config dict.
- **Consequences**: One provider config drives both ingest and translation. Proxy compatibility hacks (Phase 1 `--user-agent` / `--env-override`) work identically. We accept a small adapter layer (~50 LOC).

### Q3 — WS event protocol
- **Decision**: **Detailed stage events**. 1:1 mapping to BabelDOC's 13-stage pipeline. Event shape:
  ```
  {type: "stage_start"|"stage_progress"|"stage_end"|"finish"|"error"
        |"model_download_start"|"model_download_progress"|"model_download_done",
   stage?: "parsing"|"ocr"|"layout"|"translation"|"typesetting"|"rendering"|"saving"|...,
   page?: int, percent?: float, payload?: {...}}
  ```
- **Consequences**: Frontend can render a per-stage progress bar AND a per-page checklist. Debugging translation issues (e.g. "stuck on OCR for page 7") is observable from the UI.

### Q4 — First-run engine download UX
- **Decision**: **Inline with first translate call**. The same WS stream emits `model_download_*` events before `stage_start parsing`. No separate install endpoint.
- **Consequences**: One job, one stream, one UI flow. Users never see a separate "install" gesture. Subsequent translates skip the download events (model on disk already).

### Q5 — Frontend reader nav placement
- **Decision**: **New sub-route `/paper/$slug/read`**. Wiki markdown page (`/paper/$slug`) and PDF reader (`/paper/$slug/read`) are sibling URLs linked by a "Read in PDF" button. Reader supports tabs: Original / Dual / Translated.
- **Consequences**: Two distinct purposes, two distinct URLs. Each is bookmarkable. Concept/Claim navigation stays prominent on the wiki page (not crowded by the PDF).

## Implementation Plan (Phase 2A backend → 2B frontend, two sequential dispatches)

### Phase 2A — Backend translation worker + API + CLI

1. Add `babeldoc==0.6.2` to `pyproject.toml`; verify `uv sync` clean on Windows. Pin transitively.
2. Update NOTICE with babeldoc / pymupdf / onnxruntime / huggingface_hub entries.
3. `backend/src/xreadagent/translation/`:
   - `manifest.py` — `TranslationsManifest` wrapping `translations/manifest.json` (atomic, Pydantic strict, camelCase wire schema).
   - `babeldoc_adapter.py` — pure-Python wrapper around BabelDOC's `do_translate_async_stream`; takes a translator callable + config dataclass; yields stage events.
   - `worker.py` — `ProcessPoolExecutor` runner; subprocess isolation per quality-guidelines pattern; LLMGateway config marshalled in.
   - `events.py` — Pydantic event schemas; serializer for WS payload.
   - `service.py` — `TranslationService` orchestrator (job lifecycle, manifest writes, cache-hit short-circuit, log.md append for `translate` op).
   - Tests with mocked subprocess for all of the above.
4. FastAPI surface:
   - `POST /api/translate` → returns `{job_id}` immediately, kicks off worker.
   - WS `/ws/jobs/{job_id}` — connect → replay buffered events → stream live → close on finish/error.
   - Test with a stub adapter that emits canned events.
5. CLI `xreadagent translate <src> --workspace <ws> --model <prov:model> [--target zh] [--mono-only|--dual-only|--both] [+ all the existing --header / --user-agent / --env-override / --max-tokens flags from Phase 1].

### Phase 2B — Frontend reader + translate UI

1. Add `pdfjs-dist` to `frontend/package.json`. Set up Vite worker import.
2. `src/components/reader/PdfViewer.tsx` — thin React wrapper around pdfjs-dist; supports `mode="single"|"dual"`.
3. New route `/paper/$slug/read` — fetches manifest + renders viewer; tab switcher Original/Dual/Translated.
4. `src/components/reader/TranslateDialog.tsx` — modal that POSTs `/api/translate`, opens WS, shows per-stage progress.
5. Wire "Read in PDF" button onto `/paper/$slug` stub.
6. Frontend tests: viewer renders PDF (with a tiny fixture); translate dialog POST + WS sequence handled correctly with mocked backend.

### Phase 2C (optional polish; defer if 2A+2B fully consume time)

- "Page-replace-as-finished" streaming UX (BabelDOC writes incrementally; reader can open finished pages while later pages are still translating).
- Glossary / terminology editor UI.

## Out of Scope (locked v2 — reopen explicitly to add)

- Translation of non-PDF formats (DOCX/PPTX/HTML).
- Glossary editor UI (engine supports glossaries; we just don't expose it in UI yet).
- Page-replace streaming UX (mentioned as 2C optional).
- macOS / Apple Silicon translation (deferred to v1.5 after `hyperscan` verified, per D6 Phase 1).
- Re-ingest of translated PDFs into the wiki (would double-count concepts; user can do it manually if they want).
- Multi-target-language batching (one target per call).
- A separate "engine settings" UI surface (download lives inside translate flow).

## Technical Notes

- `research/layout-translation.md` (archived Phase 1 task) has full BabelDOC API surface.
- BabelDOC's 13 stages from source: `Loading`, `Parsing`, `OCR`, `Layout`, `Translation`, `TypeSetting`, `Rendering`, `Saving`, `Finalize` plus per-page sub-events.
- ProcessPoolExecutor + `spawn` start method on Windows (already noted in plan §3).
- BabelDOC takes a translator callable matching `Callable[[str, str, str], str]` (text, source_lang, target_lang → translated text). We adapt LLMGateway's chat method into this shape with a small wrapper.
- Frontend pdfjs-dist worker: import as `pdfjs-dist/build/pdf.worker.min.mjs?url`, hand the URL to `GlobalWorkerOptions.workerSrc`.


## Research References

- `[archived] research/layout-translation.md` — full BabelDOC API surface, AGPL implications, 13-stage pipeline.
- `[archived] research/desktop-shell.md` — transport (WS over loopback) + dev-vs-Electron flow.
