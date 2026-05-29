# Research: XReadAgent's Existing Translation Pipeline

- **Query**: What is already built for translation in XReadAgent? Trace the full data flow from user action to rendered output.
- **Scope**: Internal
- **Date**: 2026-05-29

## Findings

### Files Found

| File Path | Description |
|---|---|
| `backend/src/xreadagent/translation/service.py` | TranslationService orchestrator: job lifecycle, cache, manifest writes, conversation log |
| `backend/src/xreadagent/translation/worker.py` | AsyncTranslationWorker: subprocess spawning, event queue, async iterator |
| `backend/src/xreadagent/translation/babeldoc_adapter.py` | Adapter between BabelDOC's async API and XReadAgent's event protocol |
| `backend/src/xreadagent/translation/events.py` | Pydantic schemas for WS events (StageEvent, ModelDownloadEvent, FinishEvent, ErrorEvent) |
| `backend/src/xreadagent/translation/manifest.py` | TranslationsManifest + TranslationsIndex: persist/load/find/add translation entries |
| `backend/src/xreadagent/translation/__init__.py` | Package init |
| `backend/src/xreadagent/api/main.py` | FastAPI app: POST /api/translate, WS /ws/jobs/{job_id}, GET /api/translations/manifest, GET /api/workspaces/file |
| `frontend/src/routes/paper-read.tsx` | Paper read route: 3-tab layout (Original/Dual/Translated), TranslateDialog trigger |
| `frontend/src/components/reader/pdf-viewer.tsx` | PdfViewer component: single/dual mode, canvas-based rendering |
| `frontend/src/components/reader/translate-dialog.tsx` | TranslateDialog: model/lang config, POST + WS stream, stage progress checklist |
| `frontend/src/lib/pdfjs.ts` | PDF.js worker bootstrap (ensurePdfWorker) |
| `frontend/src/lib/api.ts` | API client: postTranslate, buildJobEventsWsUrl, getTranslationsManifest, buildWorkspaceFileUrl |
| `frontend/src/types/api.ts` | TypeScript types mirroring backend Pydantic schemas |
| `frontend/src/lib/workspace.ts` | Workspace path persistence in localStorage |
| `frontend/src/lib/notifications.ts` | Cross-platform notification utility (Electron IPC / Web Notification API) |
| `frontend/tests/components/reader/pdf-viewer.test.tsx` | PdfViewer tests (single mode, dual mode, error state) |
| `frontend/tests/routes/paper-read.test.tsx` | PaperReadRoute tests (no-workspace state, tab defaults) |
| `frontend/tests/components/reader/translate-dialog.test.tsx` | TranslateDialog tests |

### Full Data Flow: Translate Action

```
User clicks "Translate" in paper-read.tsx
  |
  v
TranslateDialog opens (target lang, model, mono/dual checkboxes)
  |
  v  [POST /api/translate]
  |   Body: {workspacePath, sourcePath, model, targetLang, sourceLang, mono, dual, apiKey?, baseUrl?}
  |   Response: {jobId}
  |
  v  [WS /ws/jobs/{jobId}]
  |   Backend: TranslationService.start_translation(request)
  |     1. Validate source_path exists
  |     2. compute_content_hash(source_path)
  |     3. TranslationsIndex.find(hash, lang, model) -- cache lookup
  |     4. Cache HIT: register synthetic job with FinishEvent, return jobId
  |     5. Cache MISS: build AdapterConfig + ChatConfig + WorkerJobConfig
  |     6. AsyncTranslationWorker.start(config) -- spawns subprocess
  |
  v  [Subprocess: _worker_entry]
  |   1. _make_chat(chat_cfg) -- rebuild LangChain chat model
  |   2. make_translator(chat) -- adapt to Callable[[text, src, dst], str]
  |   3. iter_translation_events(adapter, translator)
  |     a. _build_babeldoc_source -- background thread + asyncio loop
  |     b. _async_warmup_with_progress -- downloads ONNX + fonts on first run
  |     c. _build_translation_config -- load DocLayoutModel, wrap translator
  |     d. async_translate(bcfg) -- BabelDOC's 13-stage pipeline
  |   4. Push events onto multiprocessing Queue
  |
  v  [WS stream events, frontend reduces them]
  |   model_download_start / _progress / _done
  |   stage_start / stage_progress / stage_end (9 canonical stages)
  |   finish {mono_path, dual_path, duration_s, cached}
  |   error {stage, message, traceback_excerpt}
  |
  v  [On finish event]
  |   Backend: TranslationService._persist_finish
  |     1. Relativise mono_path + dual_path to workspace root
  |     2. TranslationsIndex.add(entry) -- atomic write to manifest.json
  |     3. WikiConversationLog.append({event: "translate", ...})
  |   Frontend: handleFinish callback
  |     1. queryClient.invalidateQueries(["translations-manifest"])
  |     2. Auto-switch tab to "dual" or "translated"
  |     3. notifyOnCompletion("Translation complete", ...)
  |     4. Close dialog after 600ms delay
```

### Backend Translation Module Architecture

**service.py** -- The `TranslationService` class is the single integration point:
- Constructor takes a `Workspace` and optional `AsyncTranslationWorker`
- `start_translation(request) -> job_id`: validates input, checks cache, spawns worker
- `event_stream(job_id) -> AsyncIterator[TranslationEvent]`: yields events until finish/error
- Cache-hit returns a synthetic `FinishEvent` immediately (no subprocess)
- On cache-miss, delegates to `AsyncTranslationWorker`
- On finish, writes manifest entry + conversation log
- BabelDOC version pinned at `0.6.2`

**worker.py** -- The `AsyncTranslationWorker` class:
- Uses `multiprocessing.get_context("spawn")` on Windows
- `WorkerJobConfig` is a plain dataclass (not Pydantic) for spawn-pickling
- `ChatConfig` carries model/api_key/base_url/headers/max_tokens -- rebuilt inside subprocess via `langchain.chat_models.init_chat_model`
- Tests inject `thread_runner` to avoid spawn overhead
- `_DONE` sentinel marks stream closure
- Late subscribers replay buffered events

**babeldoc_adapter.py** -- The boundary layer:
- `_STAGE_MAP` maps BabelDOC's 13+ stage names to 9 canonical tokens
- `_convert_event` translates raw dicts into typed Pydantic events
- `make_translator(chat)` adapts LangChain chat model to `Callable[[str, str, str], str]`
- `_build_babeldoc_source` runs BabelDOC's async API in a background thread with its own asyncio loop
- `_async_warmup_with_progress` monkey-patches `httpx.AsyncClient` to emit per-file download events
- Translation prompt: "Translate the following text from {src} to {dst}. Return only the translation..."
- `_CallableTranslator` wraps the callback into BabelDOC's `BaseTranslator` class

**events.py** -- Event protocol:
- 9 canonical stages: loading, parsing, ocr, layout, translation, typesetting, rendering, saving, finalize
- 4 event types: StageEvent, ModelDownloadEvent, FinishEvent, ErrorEvent
- Field names are snake_case (not camelCase) because these are WS-stream in-process schemas, not state-JSON sidecars
- `type` values are snake_case protocol tokens that mirror BabelDOC vocabulary

**manifest.py** -- Persistence:
- `TranslationEntry` keyed by `(sourceHash, targetLang, model)` triple
- `TranslationsIndex` provides load/save/find/add with atomic writes
- Paths are workspace-relative POSIX strings
- Adding an entry with an existing key replaces it (not de-dup)

### Frontend Translation Flow

**translate-dialog.tsx** -- The dialog component:
- Collects: target language (default "zh"), model (default "anthropic:claude-3-7-sonnet-latest"), mono checkbox, dual checkbox
- `handleStart`: POSTs `/api/translate`, subscribes to WS, reduces events via `reduce()` function
- Stage checklist renders 9 stages in pipeline order with pending/active/done status
- Download overlay shows asset name + byte progress during first-run warmup
- `websocketFactory` prop for test injection
- Dialog auto-closes 600ms after finish event

**paper-read.tsx** -- The route:
- Reads workspace path from localStorage via `readWorkspacePath()`
- Fetches translations manifest via TanStack Query
- `buildSources()` constructs URLs for original (`raw/{slug}.pdf`), mono, and dual PDFs
- `buildWorkspaceFileUrl()` builds URLs like `/api/workspaces/file?workspacePath=...&path=translations/{slug}.dual.pdf`
- Tab state is "pinned" after user manually changes it or after auto-switch on translate completion
- `handleFinish` callback invalidates manifest query and switches tab

**api.ts** -- The API client:
- `postTranslate(req: TranslateRequest)` -- POST to `/api/translate`
- `buildJobEventsWsUrl(jobId)` -- WS URL for job event stream
- `getTranslationsManifest(workspacePath)` -- GET manifest (returns empty on 404)
- `buildWorkspaceFileUrl(workspacePath, relativePath)` -- builds file serving URL
- `getApiBase()` reads `VITE_API_BASE` or falls back to `platform.ts`
- `getWsBase()` follows the same pattern for WebSocket URLs

### Backend API Endpoints (translation-related)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/translate` | POST | Start translation job, returns `{jobId}` |
| `/ws/jobs/{job_id}` | WS | Stream translation events until finish/error |
| `/api/translations/manifest` | GET | Get translation manifest for workspace |
| `/api/workspaces/file` | GET | Serve PDF files from `translations/`, `raw/`, or `extracts/` dirs |

### Security Boundaries

- `_FILE_ALLOWLIST = frozenset({"translations", "raw", "extracts"})` -- only these workspace subdirs are served over HTTP
- `state/`, `wiki/` are off-limits (conversation log, sources.json, wiki markdown)
- Path traversal prevention: resolve + `relative_to` + allowlist first segment
- Absolute paths rejected, `..` traversal blocked

### Workspace Data Layout (Translation)

```
{workspace}/
  raw/
    {slug}.pdf              # original PDF (immutable source)
  translations/
    manifest.json            # {version, entries: [{sourceSlug, sourceHash, targetLang, model, monoPath, dualPath, ...}]}
    {slug}.mono.pdf          # translated-only PDF
    {slug}.dual.pdf          # alternating-pages dual PDF (odd=original, even=translated)
  state/
    conversation-log.jsonl   # audit trail includes translate + translate_error events
```

### Key Type Contracts

**Backend (Pydantic, camelCase for state JSON)**:
- `TranslateRequest`: workspacePath, sourcePath, model, targetLang, sourceLang, mono, dual, headers, maxTokens, apiKey, baseUrl
- `TranslateResponse`: jobId
- `TranslationEntry`: sourceSlug, sourceHash, targetLang, model, monoPath, dualPath, translatedAt, durationS, babeldocVersion
- `TranslationsManifest`: version, entries

**Frontend (TypeScript mirrors in types/api.ts)**:
- Same shapes, same field names (camelCase)
- `TranslationEvent` is a discriminated union: StageEvent | ModelDownloadEvent | FinishEvent | ErrorEvent
- `StageName` = 9 literal string types

### Testing Infrastructure

- Backend: `AsyncTranslationWorker` accepts `runner` parameter for test injection (`thread_runner` instead of real subprocess)
- Backend: `babeldoc_adapter.iter_translation_events` accepts `raw_event_source` for test mocking
- Frontend: `TranslateDialog` accepts `websocketFactory` prop for test injection
- Frontend: `pdf-viewer.test.tsx` mocks `pdfjs-dist` and canvas context
- Frontend: `paper-read.test.tsx` mocks pdfjs, fetch, and localStorage

### Related Specs

- `.trellis/spec/backend/index.md` -- Phase 2A translation backend marked complete, Phase 2B PDF reader marked "Next"
- `.trellis/spec/backend/error-handling.md` -- Subprocess isolation pattern, file-serving security boundary
- `.trellis/spec/guides/cross-layer-thinking-guide.md` -- Electron/Renderer boundary, WS URL construction rules
- `.trellis/spec/frontend/index.md` -- Stack pinning (pdfjs-dist exact pin), component guidelines

## Caveats / Not Found

- The translation pipeline is fully built for Phase 2A. The Phase 2B frontend reader is also built and working. The current task (05-29-pdf-js) appears to be enhancements/polish on top of this existing foundation.
- The `__init__.py` for the translation package was not read in detail; it likely just re-exports the public API surface.
- No external search was performed as this was a pure internal investigation.