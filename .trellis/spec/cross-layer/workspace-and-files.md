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

## Native File Selection

Electron main process owns native file/folder dialogs. Renderer workflows call preload APIs through `frontend/src/lib/platform.ts` and action hooks.

Supported import suffixes are mirrored in two places:

- Electron file dialog filters in `electron/src/main.ts`.
- Frontend drop-zone filtering in `frontend/src/lib/use-workspace-actions.ts`.

Update both together.

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
