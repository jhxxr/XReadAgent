# Research: Frontend Existing PDF Reading and Translation Code

- **Query**: Research the existing frontend code in XReadAgent that relates to PDF reading and translation
- **Scope**: Internal
- **Date**: 2026-05-29

## Findings

### Files Found

| File Path | Description |
|---|---|
| `frontend/src/routes/paper-read.tsx` | Paper reading route — 3-tab viewer (Original / Dual / Translated) with PdfViewer, TranslateDialog, and manifest-driven source resolution |
| `frontend/src/routes/paper.tsx` | Paper detail route — shows frontmatter (title, authors, year, source) + wiki markdown; links to `/paper/$slug/read` |
| `frontend/src/router.tsx` | Flat route tree under one root; paper routes: `/paper`, `/paper/$slug`, `/paper/$slug/read` |
| `frontend/src/lib/api.ts` | All sidecar API functions: `getTranslationsManifest`, `buildWorkspaceFileUrl`, `postTranslate`, `buildJobEventsWsUrl`, plus wiki/ingest/query/settings functions |
| `frontend/package.json` | Already has `pdfjs-dist: 5.4.149` as a production dependency |
| `frontend/src/components/reader/pdf-viewer.tsx` | PdfViewer component using pdfjs-dist — renders all pages to `<canvas>`, supports "single" and "dual" modes |
| `frontend/src/components/reader/translate-dialog.tsx` | TranslateDialog — collects target lang/model, POSTs `/api/translate`, subscribes to WS stream, renders per-stage progress checklist |
| `frontend/src/types/api.ts` | All shared types: TranslationEntry, TranslationsManifest, TranslateRequest, TranslateResponse, StageName, StageEvent, FinishEvent, ErrorEvent, TranslationEvent, plus wiki/settings types |
| `frontend/src/lib/pdfjs.ts` | Worker bootstrap — idempotent `ensurePdfWorker()` that registers the pdfjs-dist worker URL via Vite `?url` import |
| `frontend/src/lib/workspace.ts` | Workspace path read/write via `localStorage` key `xreadagent.workspacePath` — Phase 3 placeholder |
| `frontend/src/lib/notifications.ts` | Cross-platform `notifyOnCompletion()` — Electron IPC in desktop, Web Notification API in browser |
| `frontend/src/lib/platform.ts` | Dual-environment URL resolution: `getApiBaseUrl()`, `getWsBaseUrl()`, `getSidecarBaseUrl()`, plus deep link/menu/restart IPC listeners |
| `backend/src/xreadagent/api/main.py` | FastAPI sidecar: `POST /api/translate`, `GET /api/translations/manifest`, `GET /api/workspaces/file`, `WS /ws/jobs/{job_id}`, plus wiki router and settings |
| `backend/src/xreadagent/translation/service.py` | TranslationService: cache-hit short-circuit, worker subprocess spawn, manifest persistence on finish, conversation log audit |
| `backend/src/xreadagent/translation/manifest.py` | TranslationsManifest / TranslationsIndex / TranslationEntry — Pydantic models, load/save/find/add, keyed on (sourceHash, targetLang, model) |
| `backend/src/xreadagent/translation/events.py` | WS event schemas: StageEvent, ModelDownloadEvent, FinishEvent, ErrorEvent — discriminated union TranslationEvent |

### Code Patterns

#### 1. Paper Read Route — Tab-based PDF viewer (`paper-read.tsx`)

The `/paper/$slug/read` route implements a 3-tab reading experience:

- **Sources resolution** (`buildSources`, line 36-57): constructs URLs for original (`raw/<slug>.pdf`), mono (`entry.monoPath`), and dual (`entry.dualPath`) PDFs via `buildWorkspaceFileUrl()`.
- **Tab auto-selection** (`defaultTab`, line 59-64): prefers dual > original > translated.
- **Tab pinning** (line 82-92): after manifest data arrives, auto-switches to the best tab unless the user has manually chosen one.
- **Post-translation flow** (`handleFinish`, line 94-115): invalidates the manifest query, switches to the completed tab, sends desktop notification, and closes the translate dialog.
- **Comment on Phase 2 limitation** (line 42-46): "Phase 2 has no source-path-discovery endpoint yet; we rely on the convention that the original PDF lives at `raw/<slug>.pdf`".

#### 2. PdfViewer Component (`pdf-viewer.tsx`)

- Uses `getDocument()` from `pdfjs-dist` to load the PDF.
- Renders every page to a `<canvas>` element — no virtual scrolling, no lazy loading.
- Two modes:
  - `single`: vertical stack of all pages.
  - `dual`: two-column grid, pairing odd/even pages (left=original, right=translation), matching BabelDOC's alternating-pages dual PDF.
- `pageWidth` prop defaults to 720px CSS width per page.
- Comment on Phase 2B intent (line 39-44): "Phase 2B keeps this deliberately simple: it loads the document, renders every page to a `<canvas>`, and laid out either one-column (single) or two-column (dual). No virtual scrolling, no thumbnails, no annotations — the goal is a working reader, not a full PDF.js application."

#### 3. TranslateDialog Component (`translate-dialog.tsx`)

- Collects target language (default "zh"), model (default "anthropic:claude-3-7-sonnet-latest"), mono/dual checkboxes.
- On submit: `postTranslate()` → gets `jobId` → opens WebSocket to `/ws/jobs/{jobId}` → processes `TranslationEvent` stream.
- `reduce()` function (line 304-372) handles all event types: model download, stage start/progress/end, finish, error.
- Renders a `StageChecklist` with 9 BabelDOC stages in pipeline order, plus a progress bar.
- Renders a `DownloadOverlay` for first-run engine asset downloads.

#### 4. PDF.js Worker Bootstrap (`pdfjs.ts`)

- Idempotent `ensurePdfWorker()` sets `GlobalWorkerOptions.workerSrc` using Vite's `?url` import suffix on `pdfjs-dist/build/pdf.worker.min.mjs`.
- Called by PdfViewer on mount before any `getDocument()`.

#### 5. API Layer (`api.ts`)

Translation-related functions:
- `getTranslationsManifest(workspacePath)` — returns `TranslationsManifest`, 404 → empty manifest `{version:1, entries:[]}`.
- `buildWorkspaceFileUrl(workspacePath, relativePath)` — builds URL for `/api/workspaces/file?workspacePath=...&path=...`.
- `postTranslate(req: TranslateRequest)` — POST to `/api/translate`, returns `{jobId}`.
- `buildJobEventsWsUrl(jobId)` — builds WebSocket URL for `/ws/jobs/{jobId}`.

#### 6. Backend Translation Endpoints (`main.py`)

- `POST /api/translate` — accepts `TranslateRequest` (camelCase), returns `TranslateResponse(jobId)`.
- `GET /api/translations/manifest?workspacePath=...` — returns `TranslationsManifest`; 404 if manifest file missing.
- `GET /api/workspaces/file?workspacePath=...&path=...` — serves files from `translations/`, `raw/`, `extracts/` only (strict allowlist); path traversal rejected.
- `WS /ws/jobs/{job_id}` — streams `TranslationEvent` JSON until finish/error.

#### 7. Translation Service (`service.py`)

- `TranslationRequest` dataclass: source_path, model, target_lang, source_lang, mono, dual, api_key, base_url, default_headers, max_tokens.
- Cache-hit: if `TranslationsIndex.find(hash, lang, model)` returns a hit with existing files, returns a synthetic job that immediately emits a `FinishEvent`.
- Cache-miss: builds `AdapterConfig` + `ChatConfig` + `WorkerJobConfig`, spawns `AsyncTranslationWorker`.
- On finish: writes manifest entry, writes to conversation log (`WikiConversationLog`), relativises paths.
- On error: logs failure to conversation log.

#### 8. Manifest Structure (`manifest.py`)

- `TranslationEntry`: sourceSlug, sourceHash, targetLang, model, monoPath, dualPath, translatedAt, durationS, babeldocVersion.
- `TranslationsManifest`: version (currently 1), entries list.
- `TranslationsIndex`: in-memory load/save with `find(hash, lang, model)` and `add(entry)` (replacement semantics).

### Related Specs

- `.trellis/spec/frontend/index.md` — Documents the full frontend stack including `pdfjs-dist` pinning and the component/reader architecture.
- `.trellis/spec/frontend/component-guidelines.md` — Named exports, `cn()`, CVA variants, `data-slot` styling, Radix primitives, accessibility rules.
- `.trellis/spec/guides/cross-layer-thinking-guide.md` — Cross-layer data flow conventions.

## Already Built vs Needs to Be Built (Phase 2B Assessment)

### Already Built

1. **PDF rendering** — `PdfViewer` component with canvas-based rendering in single/dual modes, using `pdfjs-dist 5.4.149` with worker bootstrap.
2. **Translation trigger UI** — `TranslateDialog` with full WS stream progress, stage checklist, and error handling.
3. **3-tab reader** — Original / Dual / Translated tabs with auto-selection and post-translation tab switching.
4. **API layer** — All translation-related API functions (manifest, file URL, translate POST, WS URL builder).
5. **Type definitions** — Full `TranslationEntry`, `TranslationsManifest`, `TranslateRequest`, `TranslateResponse`, `StageName`, `StageEvent`, `FinishEvent`, `ErrorEvent`, `TranslationEvent` types mirroring backend Pydantic models.
6. **Backend translation pipeline** — `POST /api/translate`, `GET /api/translations/manifest`, `GET /api/workspaces/file`, `WS /ws/jobs/{jobId}` all fully implemented.
7. **Cache logic** — Backend cache-hit detection, manifest find/add, workspace-relative path persistence.
8. **Notifications** — Cross-platform `notifyOnCompletion()` for translation completion.
9. **Workspace path** — localStorage-based workspace path read/write (placeholder for Phase 3 picker).

### Likely Needs to Be Built for Phase 2B

1. **Virtual scrolling / lazy page rendering** — Current `PdfViewer` renders ALL pages at once (no virtualization). For large PDFs this is a performance problem. The comment at line 39-44 explicitly calls this out as a Phase 2B simplification.
2. **Page thumbnails / sidebar** — No thumbnail navigation panel exists.
3. **Source path discovery endpoint** — The comment at `paper-read.tsx:42-46` states "Phase 2 has no source-path-discovery endpoint yet" — currently relies on the `raw/<slug>.pdf` convention.
4. **Text selection / annotation** — No text layer rendering (current approach is canvas-only, no `textLayer` or `annotationLayer` from pdfjs-dist).
5. **Zoom controls** — No zoom in/out/fit-width controls; page width is fixed at 720px.
6. **Page navigation** — No scroll-to-page, page number input, or keyboard page navigation.
7. **PDF loading progress** — No download progress indicator for large PDFs (just "Loading PDF...").
8. **Error recovery** — No retry mechanism for failed PDF loads or failed page renders.
9. **Mobile responsiveness** — Dual mode uses `md:grid-cols-2` which collapses on small screens, but no touch gestures or swipe support.

## Caveats / Not Found

- No `pdfjs-dist` configuration beyond the worker URL (no custom CMap URL, no standard font URL, no image resource path).
- No text layer (`pdfjs-dist` `TextLayerBuilder`) is configured — pages are rasterized to canvas only, meaning users cannot select/copy text from PDFs.
- The `paper-read.tsx` route hardcodes the original PDF path as `raw/${slug}.pdf` rather than discovering it dynamically.
- The `PdfViewer` does not clean up page resources when switching tabs or when the component unmounts beyond the basic `page.cleanup()` call.
- No existing tests were found for `pdf-viewer.tsx` or `translate-dialog.tsx` (the `frontend/tests/` directory was not searched but the spec mentions Vitest setup).