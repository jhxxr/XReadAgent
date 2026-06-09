# Source Path And Translation Flow

## Summary

PDF import, the PDF reader, and BabelDOC translation already exist, but they
do not share a single source-file contract yet. Import copies the original PDF
to `raw/_processed/{slug}.pdf` and records that path in `state/sources.json` as
`Source.sourcePath`; the reader and translate dialog currently guess
`raw/{slug}.pdf`.

## Current Flow

- Renderer import buttons live in `frontend/src/routes/workspace.tsx` and
  `frontend/src/components/workspace/workspace-empty-state.tsx`.
- `useWorkspaceActions().importDocument()` opens Electron's native file picker
  through `window.electronAPI.showOpenFileDialog()` and posts
  `POST /api/ingest` with `{ workspacePath, filePath }`.
- Electron exposes the file picker in `electron/src/preload.ts`; the main
  process implements it in `electron/src/main.ts` with PDF/document filters.
- Backend `POST /api/ingest` in `backend/src/xreadagent/api/wiki_router.py`
  calls `ingest_source()`.
- `backend/src/xreadagent/pipeline/router.py` computes the content hash, builds
  the stable source slug, converts the document, and copies the chosen file to
  `workspace.raw_processed_dir / f"{slug}{suffix}"`.
- The persisted `Source.sourcePath` is workspace-relative, for example
  `raw/_processed/attention-is-all-you-need-abcdef123456.pdf`.

## Translation Flow

- `frontend/src/routes/paper-read.tsx` renders the reader and opens
  `TranslateDialog`.
- `TranslateDialog` posts `POST /api/translate` and subscribes to
  `/ws/jobs/{jobId}`.
- Backend `POST /api/translate` accepts `workspacePath`, `sourcePath`, model,
  language, and output options, then passes `Path(sourcePath)` to
  `TranslationService.start_translation()`.
- `TranslationService` validates that exact file, hashes it, calls BabelDOC via
  the worker, and persists output paths under `translations/manifest.json`.
- Translation manifest entries use workspace-relative paths for mono/dual PDFs.

## Gaps

- `paper-read.tsx` builds the original URL as `raw/${slug}.pdf`, which does not
  match the actual import archive path.
- `paper-read.tsx` passes `${workspacePath}/raw/${slug}.pdf` to
  `TranslateDialog`, so translation fails for normal imports.
- The backend already has the canonical source path in `state/sources.json`, but
  the paper summary/detail API does not expose it in a typed way.
- The sidecar entrypoint calls `create_app(lifespan=lifespan)` without a
  production `TranslationService` factory, so `/api/translate` can return 503
  outside tests unless the app is wired during startup.

## Likely MVP Direction

- Expose canonical paper source metadata by slug from the backend, preferably
  by adding `sourcePath` to paper summary/detail responses while keeping
  existing frontmatter intact.
- Use the workspace-relative `sourcePath` to build the Original tab URL through
  `/api/workspaces/file`.
- Convert the same relative path to an absolute path when posting
  `/api/translate`: `workspacePath/sourcePath`.
- Wire production sidecar startup with a workspace-scoped `TranslationService`
  factory.
- Add tests across backend API, frontend API/types, reader route behavior, and
  sidecar translation wiring.
