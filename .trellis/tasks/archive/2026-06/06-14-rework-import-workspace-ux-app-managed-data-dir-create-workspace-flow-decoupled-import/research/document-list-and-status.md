# Research: document list rendering + status fields

## Critical finding

The current "Papers" list is sourced from **`wiki/papers/*.md`**, NOT from the source
manifest. So a **registered-but-not-built** document will NOT appear once import is
decoupled. A new sources-backed document list is required.

## Evidence

- Frontend `frontend/src/routes/workspace.tsx` → `PapersTab` calls `getPapers(workspacePath)`
  (`frontend/src/lib/api.ts`) → backend `GET /api/wiki/papers`
  (`backend/src/xreadagent/api/wiki_router.py:164`) → `list_papers(workspace)`
  (`backend/src/xreadagent/wiki/frontmatter_utils.py:47`) which reads frontmatter from
  `wiki/papers/*.md`. **No wiki page = not listed.**
- Tabs are Papers / Concepts / Queries; header workspace name is hardcoded
  `"Default Workspace"` (`workspace.tsx:243,259`) — to be replaced by the switcher.
- The source-of-truth for *registered* documents is `state/sources.json` via
  `SourcesIndex.load(workspace)` (`backend/src/xreadagent/wiki/sources.py`). `Source`
  carries `slug,title,kind,sourcePath,contentHash,ingestedAt,pageCount,extractPath,lastError`.

## Design implication

- Add a backend endpoint listing **sources** (from `SourcesIndex`), with a derived status:
  - `registered` (always, once converted)
  - `wikiBuilt` iff `wiki/papers/{slug}.md` exists
  - `translated` iff a `translations/manifest.json` entry + PDFs exist
    (reuse `_entry_paths_exist` in `translation/service.py`).
- Add a frontend "Documents" view (likely a new tab or replacing the empty/Papers entry)
  that renders sources with status badges + per-document `Translate` and `Build Wiki`
  buttons, each firing the existing job + `/ws/jobs/{id}` stream.
- Per-document actions belong on the source row; keep operation write-isolation
  (translate vs wiki) per `.trellis/spec/cross-layer/workspace-and-files.md`.
