# Rework Import / Workspace UX

## Goal

Fix three coupled UX/architecture gaps the user hit in the desktop app:
1. Importing a document immediately runs the full LLM wiki build with no choice — the user sometimes only wants a format-preserving translation.
2. Generated wiki folders land in the OS Downloads directory because there is no app-managed data directory; the folder picker has no default and "workspace = whatever folder you point at".
3. There is no GUI "create new workspace" flow — only "Open Workspace" (pick an existing folder). `init_empty()` is CLI-only.

The fix: introduce an **app-managed data directory** under Electron `userData`, add a **create-workspace** flow + registry/switcher in the GUI, and **decouple import** (register the document) from **processing** (translate / build-wiki as on-demand per-document actions).

## What I already know (from codebase inspection)

- **Import == ingest == auto wiki build.** `frontend/src/lib/use-workspace-actions.ts:117` `importDocument()` → `ingestMutation.mutate()` → `runIngestJob` → backend `ingest_source`. Pipeline is fixed: `converting → analyzing(LLM) → writing wiki pages` (`backend/src/xreadagent/api/ingest_jobs.py:55`). No "choose what to do" step.
- **Translation is a separate job/link** (`backend/src/xreadagent/translation/service.py`), not offered at import time.
- **No app data dir.** Only GUI workspace action is "Open Workspace" via `dialog.showOpenDialog({properties:["openDirectory"]})` with **no `defaultPath`** (`electron/src/main.ts:614`, also `menu.ts:101`, tray `main.ts:565`). The picked folder becomes `Workspace.root`; `wiki/` is created under it (`backend/src/xreadagent/wiki/workspace.py`). Hence wiki ends up wherever the dialog landed (often Downloads on Windows).
- **No GUI create-workspace.** `Workspace.init_empty()` (seeds index/log/overview/sources/manifests) is only called from `backend/src/xreadagent/cli/init_cmd.py:82`. GUI relies on lazy `ensure_layout()` at ingest/translate time.
- **Workspace layout is already correct** (`WORKSPACE_LAYOUT` → `wiki/ raw/ extracts/ translations/ state/` under root). The only problem is *where root is* and *how it's created*. Backend `Workspace` is the canonical path owner; frontend/electron must not rebuild layout rules (`.trellis/spec/cross-layer/workspace-and-files.md`, `.trellis/spec/backend/workspace-storage.md`).
- Backend jobs are already job-ified and independent (ingest job + translation job, each `POST` → `{jobId}` → `/ws/jobs/{id}`). Frontend just needs to split "import" into "register" + "trigger job on demand".
- Electron path helpers live in `electron/src/sidecar.ts` (`isPackaged`, `getAppPath`, `resourcesPath`); preload exposes `showOpenFolderDialog` / `showOpenFileDialog` / `getPathForFile` (`electron/src/preload.ts`). Workspace path persisted on frontend via `frontend/src/lib/workspace.ts` (`writeWorkspacePath` / `useWorkspacePath`).
- Spec rule: **do not auto-create workspaces from read-only API endpoints**; `_open_workspace` requires the dir to exist (`backend/src/xreadagent/api/main.py:333`, `wiki_router.py:115`).

## Decisions locked (via user)

1. **Storage root = Electron `app.getPath('userData')`** → `%APPDATA%/XReadAgent/workspaces/<slug>/`. (Rejected install-dir: Program Files is non-writable / wiped on update.) A "custom location" option may be offered, but the default+primary path is the managed data dir.
2. **Import = register only.** Importing converts + archives raw + records the source, but does **not** call the LLM. Each document then exposes two **independent** on-demand actions: `Translate (format-preserving)` and `Build Wiki`. **No combined one-click action in MVP.**
3. **Drop "Open arbitrary folder" entirely.** Project is still in development → no backward-compat / migration of the old folder-picker model. Workspaces are *only* the managed ones under the data dir.
4. **MVP includes full workspace management**: create / rename / delete / reveal-in-file-manager / switch, backed by a registry.

## Assumptions (to validate during codebase research)

- A new lightweight "register/convert-only" ingest mode can reuse the existing convert stage without the analyze/write-wiki stages (the pipeline already separates `converting` from `analyzing`/`writing` — `pipeline/router.py`, `agents/orchestrator.py`).
- A `workspaces.json` registry (slug, display name, abs path, lastOpenedAt) lives at the data-dir root, owned by Electron main (path concerns are Electron's job, not backend's).
- Document list / per-document action surface: need to confirm where the document/source list is rendered (`sources.json` → API → which frontend route/component) to attach Translate / Build-Wiki buttons and a "needs build" status.

## Open Questions

- New-workspace naming: free-text display name → slugified dir; collision → append `-2`, `-3`; reject empty/invalid. (default decision, not blocking)

## Research findings (resolved)

- **convert-only is free** — backend already separates register from build: `convert_source` (`pipeline/router.py`) does convert+archive+record source with NO LLM; `ingest_source` = `convert_source` + `agent.ingest`. Register = call `convert_source` only; Build Wiki = run the agent on an already-registered source (convert short-circuits). See `research/convert-only-vs-build-wiki.md`.
- **document list must move to sources.json** — the current Papers tab reads `wiki/papers/*.md` (`list_papers`), so registered-but-unbuilt docs would be invisible after decoupling. Need a new sources-backed document list (from `SourcesIndex`) with derived status `registered / wikiBuilt / translated`, and the per-document action buttons live there. See `research/document-list-and-status.md`.

## Requirements (evolving)

- Electron main resolves a managed data root under `userData`; creates `userData/workspaces/<slug>/` and a `workspaces.json` registry.
- GUI "New workspace": display name → create dir → backend seeds layout (`init_empty`) → register → open & switch to it.
- GUI workspace management: switch (list/dropdown), rename, delete (with confirm), reveal in OS file manager.
- "Open arbitrary folder" entry **removed** from menu / tray / empty-state.
- Import **registers** a document (convert + archive raw + record source) without triggering the LLM build.
- Per-document independent on-demand actions: `Translate` and `Build Wiki`, each with progress + status.
- Folder/file dialogs (still used for import source files) start at a sensible default; workspace selection no longer uses a folder dialog.

## Acceptance Criteria (evolving)

- [ ] Importing a PDF does NOT start an LLM wiki build; no model tokens are spent on import.
- [ ] Creating a new workspace produces a seeded workspace folder under `userData/workspaces/<slug>/` (never Downloads).
- [ ] A registered document can be translated (format-preserving) without ever building a wiki.
- [ ] A registered document can have its wiki built on an explicit, separate action.
- [ ] Workspace switch / rename / delete / reveal-in-file-manager all work from the GUI.
- [ ] The old "Open arbitrary folder as workspace" entry is gone (menu, tray, empty-state).

## Definition of Done (team quality bar)

- Tests added/updated (backend register-mode + workspace-create endpoint; electron path/registry units; frontend action-split).
- Lint / typecheck / tests green across backend + electron + frontend.
- Specs updated: `.trellis/spec/cross-layer/workspace-and-files.md`, `.trellis/spec/backend/workspace-storage.md` (new data-dir + register mode).
- Two-place sync (import suffix lists) preserved.

## Out of Scope (explicit)

- Cloud sync / multi-device.
- Reworking the wiki synthesis pipeline itself.
- Multi-document batch processing UI (beyond importing one-at-a-time as today).
- Backward-compat / migration of the old arbitrary-folder workspace model (project is pre-release).
- Combined "Translate + Build Wiki" one-click action.

## Technical Approach

- **Data dir (Electron main):** resolve `app.getPath('userData')`; expose `workspaces/` root + `workspaces.json` registry via new preload IPC (`workspace:list/create/rename/delete/reveal`). Electron owns path math; backend stays the canonical *layout* owner.
- **Create flow:** Electron creates `workspaces/<slug>/` then calls backend to seed layout. Add a backend endpoint that runs `Workspace.at(root).init_empty(title)` (reuse `cli/init_cmd.py` logic) — the only place allowed to create a workspace (read-only endpoints still must not auto-create).
- **Decoupled import:** add a **register/convert-only** ingest that runs the `converting` stage + source manifest write, skipping `analyzing`/`writing`. Likely a `mode` on the ingest job or a separate `convert_source`-only path (`pipeline/router.py` already isolates convert). Build Wiki becomes the existing full ingest (analyze+write) on an already-registered source.
- **Per-document actions:** document/source list gains `Translate` and `Build Wiki` buttons + status (registered / wiki-built / translated), each driven by the existing job + `/ws/jobs/{id}` stream.
- **Removal:** delete "Open Workspace" folder-dialog entries from `menu.ts`, tray + `main.ts`, and `workspace-empty-state.tsx`; replace with New/Switch.

## Decision (ADR-lite)

- **Context:** wiki landed in Downloads, import auto-burned tokens, no create flow.
- **Decision:** app-managed `userData/workspaces/<slug>/` data dir + registry; GUI create/switch/rename/delete; import registers only, with two independent per-document actions (Translate, Build Wiki). Drop arbitrary-folder model (pre-release, no migration).
- **Consequences:** users can no longer point at an arbitrary existing folder (acceptable pre-release); slightly more Electron-main surface (registry + IPC); backend gains a create endpoint and a convert-only ingest mode.

## Implementation Plan (small PRs)

- **PR1 — Data dir + registry + create endpoint:** Electron `userData/workspaces` resolution, `workspaces.json`, preload IPC (list/create/rename/delete/reveal); backend create-workspace endpoint calling `init_empty`. Unit tests for path/registry + endpoint.
- **PR2 — GUI workspace management:** New-workspace dialog, switcher, rename/delete/reveal; remove old folder-picker entries; frontend workspace state moves from single path to registry-backed. Tests.
- **PR3 — Decoupled import + per-document actions:** convert-only register mode (backend), import wiring (register, no LLM), per-document Translate / Build-Wiki buttons + status. Tests + spec updates.

## Technical Notes

- Backend canonical path owner: `backend/src/xreadagent/wiki/workspace.py` + `wiki/paths.py`. Do not duplicate layout in FE/Electron.
- Electron path resolution patterns: `electron/src/sidecar.ts`, dialogs in `electron/src/main.ts` / `menu.ts`, preload bridge `electron/src/preload.ts`.
- Frontend workspace state: `frontend/src/lib/workspace.ts`, actions `frontend/src/lib/use-workspace-actions.ts`, empty state `frontend/src/components/workspace/workspace-empty-state.tsx`.
- Ingest jobs: `backend/src/xreadagent/api/ingest_jobs.py`, orchestrator `agents/orchestrator.py` (`ingest_source`), convert stage in `pipeline/router.py`.
