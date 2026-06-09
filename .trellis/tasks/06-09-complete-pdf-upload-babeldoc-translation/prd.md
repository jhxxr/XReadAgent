# Complete PDF Upload Format-Preserving Translation Via BabelDOC

## Goal

Make the desktop PDF import-to-translation loop work end to end: a user imports
a PDF into a workspace, opens the paper in the reader, sees the original PDF,
clicks Translate, and BabelDOC creates mono/dual translated PDFs that appear in
the reader without manually fixing paths.

## What I Already Know

- Electron already exposes a native file picker for document import.
- The frontend already has Import buttons, a PDF reader route, a Translate
  dialog, translation progress over WebSocket, and translation manifest reads.
- Backend already has `POST /api/ingest`, `POST /api/translate`,
  `/ws/jobs/{jobId}`, `/api/translations/manifest`, and
  `/api/workspaces/file`.
- Import currently archives the selected PDF to
  `raw/_processed/{slug}.pdf` and stores that workspace-relative path in
  `state/sources.json` as `Source.sourcePath`.
- The reader currently guesses `raw/{slug}.pdf`, so normal imported PDFs are
  not found by the Original tab or by translation.
- Production sidecar startup appears to call `create_app()` without a
  translation service factory, so `/api/translate` may be unavailable outside
  tests unless startup wires it.

## Requirements

- Expose the canonical source PDF path for each paper through the backend API.
- Preserve the path as a workspace-relative string, matching the existing
  `Source.sourcePath` contract.
- Update frontend API types and reader code to use the canonical source path
  instead of guessing `raw/{slug}.pdf`.
- Build original PDF URLs with `/api/workspaces/file` using the canonical
  workspace-relative source path.
- Start translation with an absolute filesystem source path derived from
  `workspacePath + sourcePath`.
- Keep translation outputs and manifest behavior unchanged: outputs land under
  `translations/`, and the reader switches to dual/translated output after the
  finish event.
- Wire the sidecar entrypoint so production `/api/translate` has a real
  workspace-scoped `TranslationService`.
- Surface a clear unavailable state when a paper has no PDF source path instead
  of attempting translation with a guessed path.
- Keep the reader route reachable for non-PDF imports, but show a no-PDF state
  and disable translation rather than hiding the route elsewhere.

## Acceptance Criteria

- [x] After importing a PDF, opening `/paper/{slug}/read` loads the original
      PDF from the workspace archived path.
- [x] Clicking Translate for an imported PDF posts a `sourcePath` that points to
      the existing archived PDF and does not return "source file not found".
- [x] Translation completion still refreshes the manifest and switches to the
      dual PDF when one is produced.
- [x] Backend tests cover source path exposure for paper list/detail and the
      production translation service factory.
- [x] Frontend tests cover reader source path selection and no-PDF state when no
      PDF source is available.
- [x] Lint/typecheck/tests pass for touched layers.

## Definition Of Done

- Tests added or updated for backend and frontend contracts.
- Relevant lint and type-check commands pass.
- No business logic is added to Electron main; Electron remains limited to
  native file picking and sidecar lifecycle.
- Workspace file serving remains allowlisted and traversal-safe.
- No changes to BabelDOC output layout or manifest schema unless required for
  the source-path contract.

## Technical Approach

Use existing workspace metadata rather than introducing a second upload
manifest. Backend already records the canonical archived source in
`state/sources.json`; the API should surface that field so the reader can use
one source of truth. The frontend should treat `sourcePath` as
workspace-relative for serving and convert it to an absolute path only at the
translation boundary, because the translation service currently accepts a local
filesystem path.

## Decision (ADR-Lite)

**Context**: Import, reader, and translation were implemented in separate
phases and drifted on the original PDF path convention.

**Decision**: Make `Source.sourcePath` the canonical imported-PDF contract for
the reader and BabelDOC path handoff. For non-PDF imports, keep the reader route
available but render a no-PDF state and disable translation.

**Consequences**: Existing imported workspaces can work without renaming files,
because `state/sources.json` already contains the archived path. The UI becomes
less dependent on filename conventions. Non-PDF imported documents may still
need a no-PDF state in the reader.

## Out Of Scope

- Multipart browser upload for non-Electron web mode.
- Reworking the ingestion pipeline or MinerU behavior.
- Changing BabelDOC progress protocol or output file naming.
- Adding translation settings beyond the existing dialog fields.
- Translating DOCX/HTML/Markdown imports through BabelDOC.

## Research References

- `research/source-path-and-translation-flow.md` - codebase trace of import,
  source path persistence, reader path guessing, and translation service wiring.

## Technical Notes

- Relevant frontend files:
  - `frontend/src/lib/api.ts`
  - `frontend/src/types/api.ts`
  - `frontend/src/routes/paper.tsx`
  - `frontend/src/routes/paper-read.tsx`
  - `frontend/src/components/reader/translate-dialog.tsx`
  - `frontend/src/lib/use-workspace-actions.ts`
- Relevant backend files:
  - `backend/src/xreadagent/api/main.py`
  - `backend/src/xreadagent/api/__main__.py`
  - `backend/src/xreadagent/api/wiki_router.py`
  - `backend/src/xreadagent/wiki/frontmatter_utils.py`
  - `backend/src/xreadagent/wiki/sources.py`
  - `backend/src/xreadagent/pipeline/router.py`
  - `backend/src/xreadagent/translation/service.py`
  - `backend/src/xreadagent/translation/manifest.py`
- Relevant Electron files:
  - `electron/src/main.ts`
  - `electron/src/preload.ts`
