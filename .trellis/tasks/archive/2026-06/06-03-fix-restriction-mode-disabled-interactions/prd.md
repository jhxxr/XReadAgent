# Fix Restriction Mode Disabled Interactions

## Goal

Users can enter the app/workspace screen and still perform the expected first actions: choose a workspace and import a document. The current workspace UI exposes disabled import buttons and a non-functional workspace switcher even though the backend already has an ingest endpoint, leaving users unable to do useful work after entering the app.

## Requirements

* The workspace switcher opens a native folder picker in Electron and persists the selected workspace path.
* The empty-state `Import paper` button and header `Import` button are enabled when a workspace path is available.
* Import opens a native file picker in Electron for supported document types and submits the selected file path to the existing `/api/ingest` client.
* After a successful import, the workspace paper/concept/query lists refresh and the user gets a clear success notification.
* When no workspace path is set, the empty state offers a working action to select one instead of a disabled import action.
* Browser/dev mode should not throw if the Electron bridge is unavailable; unsupported native file picking should show a helpful message.

## Acceptance Criteria

* [ ] The sidebar workspace switcher is clickable and uses `window.electronAPI.showOpenFolderDialog`.
* [ ] The workspace empty state renders enabled, clickable first-action buttons instead of disabled placeholders.
* [ ] Selecting a file calls `postIngest({ workspacePath, filePath })`.
* [ ] Successful ingest invalidates workspace list queries.
* [ ] Tests cover folder selection, import triggering, and unsupported-browser fallback behavior.
* [ ] Frontend lint/type-check/tests pass for the affected area.

## Definition of Done

* Tests added or updated for the interaction path.
* Lint/type-check/test commands are run, with failures fixed or reported.
* No unrelated user changes are reverted.

## Technical Approach

Add a narrow frontend import hook for native file/folder picking and ingest mutation. Extend the Electron preload/main IPC surface with a `showOpenFileDialog` method parallel to the existing folder dialog. Wire the hook into `WorkspaceRoute`, `WorkspaceEmptyState`, and `AppSidebar`, while preserving browser-mode fallback behavior.

## Decision (ADR-lite)

Context: The backend already exposes `/api/ingest` and the frontend API client already exposes `postIngest`; the gap is UI and native file selection wiring.

Decision: Reuse the existing `postIngest` client and Electron IPC pattern instead of introducing upload/multipart support.

Consequences: This restores packaged Electron behavior quickly. Browser dev mode cannot import arbitrary local files because the backend expects a filesystem path; it will show a clear unsupported message instead.

## Out of Scope

* Streaming ingest progress.
* Drag-and-drop upload.
* Browser multipart upload support.
* Backend ingest implementation changes.

## Technical Notes

* `frontend/src/routes/workspace.tsx` has a disabled header import button.
* `frontend/src/components/workspace/workspace-empty-state.tsx` has a disabled placeholder import button.
* `frontend/src/components/shell/app-sidebar.tsx` renders a workspace switcher button without an action.
* `electron/src/preload.ts` already exposes `showOpenFolderDialog`; add file picker alongside it.
* `frontend/src/lib/api.ts` already exposes `postIngest`.
