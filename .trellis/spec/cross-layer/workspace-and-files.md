# Workspace And Files

## Workspace Path Source Of Truth

Backend `Workspace` owns canonical workspace layout and path accessors. Frontend and Electron should pass workspace roots and relative paths, not rebuild backend layout rules.

Reference files:

- `backend/src/xreadagent/wiki/workspace.py`
- `backend/src/xreadagent/wiki/paths.py`
- `frontend/src/lib/workspace.ts`
- `frontend/src/lib/use-workspace-actions.ts`

## Relative Path Convention

Persisted paths in manifests and API payloads should be workspace-relative POSIX strings:

- `raw/_processed/<slug>.pdf`
- `extracts/<slug>.md`
- `translations/<slug>.dual.pdf`
- `wiki/queries/<topic>/<date>-<slug>.md`

Backend should use `.relative_to(workspace.root).as_posix()` where possible.

## Serving Workspace Files

The backend only serves a narrow allowlist from `/api/workspaces/file`:

- `translations`
- `raw`
- `extracts`

It intentionally does not serve `state` or `wiki` through the generic file endpoint. Keep path traversal checks and allowlist behavior in place.

Reference file: `backend/src/xreadagent/api/main.py`.

## Managed Workspace Directory

Workspaces are app-managed, not arbitrary user folders. The Electron main process owns the data directory and registry:

- Root: `<userData>/workspaces/<slug>/` (Electron `app.getPath("userData")`).
- Registry: `<userData>/workspaces.json` (slug, display name, abs path, timestamps).
- Lifecycle IPC: `workspace:list/create/rename/delete/touch/reveal` (`electron/src/workspaces.ts`, exposed via `electron/src/preload.ts`).

Creation is a two-step orchestration owned by the renderer (`frontend/src/lib/use-workspaces.ts`): (1) Electron allocates the slugged directory + registry entry, (2) the backend seeds the layout via `POST /api/workspaces/create`. If step 2 fails, step 1 is rolled back. There is no native "open arbitrary folder" entry (removed from menu/tray); the in-app `WorkspaceManagerDialog` is the only switcher.

## Native File Selection

Electron main process owns native file dialogs. Renderer workflows call preload APIs through `frontend/src/lib/platform.ts` and action hooks. Only the **file** dialog (`show-open-file-dialog`, for picking a document to import) remains — the folder dialog was removed with the arbitrary-folder workspace model.

Supported import suffixes are mirrored in two places:

- Electron file dialog filters in `electron/src/main.ts`.
- Frontend drop-zone filtering in `frontend/src/lib/use-workspace-actions.ts`.

Update both together.

## Import Is Convert-Only

Importing a document **registers** it (convert + archive + `state/sources.json`) but does NOT build the wiki — no LLM tokens are spent on import. The Documents list (`frontend/src/components/workspace/documents-tab.tsx`, backed by `GET /api/sources`) surfaces each registered document with status and two independent per-document actions: **Translate** (format-preserving) and **Build Wiki**. Keep import decoupled from wiki synthesis.

## Workspace Mutation Isolation

Preserve operation-specific write boundaries:

- Query writes query archive + conversation log only.
- Translation writes translations + conversation log only.
- Conversion writes extracts/raw processed/sources + wiki log.
- Ingest writes synthesized wiki pages through the agent apply path.

If a task changes these boundaries, update backend tests and this spec.

## Anti-Patterns

- Do not make frontend construct paths to `state/` files.
- Do not serve hidden or audit state through a generic file endpoint.
- Do not store absolute local filesystem paths inside workspace manifests unless the path cannot be relativized and the caller has a clear fallback.
- Do not add a second supported-file-type list without a synchronization test or explicit note.
