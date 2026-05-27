# XReadAgent MVP — Wiki Browser + Agent API

## Goal

Wire the existing backend agents as HTTP endpoints and build a functional wiki browser UI so users can browse papers, concepts, and queries after ingesting documents. This completes the core loop: ingest → browse → query.

## Requirements

### R1: Backend — Wiki Read API

Add read-only endpoints to browse wiki content:

| Endpoint | Returns |
|---|---|
| `GET /api/wiki/papers` | List all papers (parse frontmatter from `wiki/papers/*.md`) |
| `GET /api/wiki/papers/{slug}` | Single paper markdown content + frontmatter |
| `GET /api/wiki/concepts` | List all concepts (parse frontmatter from `wiki/concepts/*.md`) |
| `GET /api/wiki/concepts/{slug}` | Single concept markdown content + frontmatter |
| `GET /api/wiki/queries` | List all query archives (scan `wiki/queries/**/*.md`) |
| `GET /api/wiki/queries/{topic}/{slug}` | Single query markdown content |
| `GET /api/wiki/index` | Raw `wiki/index.md` content |
| `GET /api/wiki/overview` | Raw `wiki/overview.md` content |

Response schemas:
- Paper summary: `{ slug, title, authors: string[], year: number|null, ingestedAt: string }` (matches existing `PaperSummary` in frontend `types/api.ts`)
- Concept summary: `{ slug, title, aliases: string[], paperCount: number }` (matches `ConceptSummary`)
- Query summary: `{ id, question, topic, archivedAt: string }` (matches `QuerySummary`)
- Single item: `{ slug, content: string, frontmatter: Record<string, unknown> }`

Implementation notes:
- Reuse the frontmatter-parsing pattern from `_summarize_papers()` / `_summarize_concepts()` in `agents/ingest.py` — extract into shared utility
- Use `Workspace.at(root)` with `workspacePath` query param (same pattern as translation endpoints)
- Validate workspace path with existing `validate_wiki_path()` for security

### R2: Backend — Ingest & Query HTTP Endpoints

Wire existing orchestrator functions as HTTP endpoints:

| Endpoint | Body | Returns |
|---|---|---|
| `POST /api/ingest` | `{ workspacePath, filePath, title? }` | `IngestResult` JSON |
| `POST /api/query` | `{ workspacePath, question, topic? }` | `QueryResult` JSON |

Implementation notes:
- `POST /api/ingest`: construct `Workspace`, build `IngestAgent` with model from settings/CLI, call `ingest_source()`
- `POST /api/query`: construct `Workspace`, build `QueryAgent`, call `answer_query()`
- Model string needs to be available at runtime — either from a settings file or passed in the request body (with a default from env)
- Add `model` field to request bodies as optional override

### R3: Frontend — Workspace Page (Wiki Browser)

Replace the empty-state placeholders with functional wiki browsing:

**Papers tab:**
- Fetch `GET /api/wiki/papers` with `useQuery`
- Display as a card grid or list: title, authors, year, ingested date
- Click navigates to `/paper/$slug`

**Concepts tab:**
- Fetch `GET /api/wiki/concepts`
- Display as cards: title, aliases, related paper count
- Click navigates to `/concept/$slug` (new route)

**Queries tab:**
- Fetch `GET /api/wiki/queries`
- Display as list: question, topic, date
- Click navigates to `/query/$id` (new route)

### R4: Frontend — Detail Pages

**`/paper/$slug` (PaperRoute — replace placeholder):**
- Fetch `GET /api/wiki/papers/$slug`
- Render markdown content with a simple markdown renderer (e.g., `react-markdown` or similar)
- Show frontmatter as header (title, authors, year)
- Link to `/paper/$slug/read` for PDF reader
- Link to `/paper/$slug/translate` if translation exists

**`/concept/$slug` (new route):**
- Fetch `GET /api/wiki/concepts/$slug`
- Render markdown content
- Show frontmatter header

**`/query/$id` (new route):**
- Fetch `GET /api/wiki/queries/{topic}/{slug}`
- Render markdown content
- Show "Crystallize" button (disabled for now, Phase 2)

### R5: Frontend — Markdown Rendering

- Install `react-markdown` + `remark-gfm` for GFM support
- Style markdown output to match shadcn design system
- Handle `[[wiki-links]]` — render as internal links to other wiki pages
- Handle code blocks, tables, images (if any)

## Acceptance Criteria

- [ ] `GET /api/wiki/papers` returns list of papers with frontmatter metadata
- [ ] `GET /api/wiki/papers/{slug}` returns full paper content
- [ ] `GET /api/wiki/concepts` returns list of concepts
- [ ] `GET /api/wiki/concepts/{slug}` returns full concept content
- [ ] `GET /api/wiki/queries` returns list of query archives
- [ ] `POST /api/ingest` successfully ingests a document and returns result
- [ ] `POST /api/query` successfully answers a question and returns result
- [ ] Workspace page Papers tab shows real paper data
- [ ] Workspace page Concepts tab shows real concept data
- [ ] Workspace page Queries tab shows real query data
- [ ] Paper detail page renders markdown with frontmatter header
- [ ] Concept detail page renders markdown with frontmatter header
- [ ] Query detail page renders markdown content
- [ ] `[[wiki-links]]` in markdown render as clickable internal links
- [ ] All new API endpoints have unit tests
- [ ] Frontend typecheck, lint, and tests pass
- [ ] Backend ruff and mypy clean

## Definition of Done

- All acceptance criteria pass
- Existing tests still pass (287 backend + frontend tests)
- No regressions in PDF reader or translation workflow

## Out of Scope (this task)

- Settings UI / LLM provider configuration page
- Copilot sidebar (ask/answer/evidence workflow)
- R-LINT (wiki health check agent)
- Crystallize UI (propose/apply workflow) — endpoint wired but no frontend
- Electron packaging
- File upload for ingest (use file path on disk for now)

## Technical Notes

- Backend entry: `backend/src/xreadagent/api/main.py`
- Frontend entry: `frontend/src/router.tsx`
- Existing API pattern: `request<T>(path, init?)` in `frontend/src/lib/api.ts`
- Existing types: `PaperSummary`, `ConceptSummary`, `QuerySummary` already defined in `frontend/src/types/api.ts`
- Workspace class: `backend/src/xreadagent/wiki/workspace.py`
- Frontmatter parsing: `_summarize_papers()` in `agents/ingest.py` (to be extracted)
- Agent construction needs `model` string — `IngestAgent(model=..., planner=...)` pattern
- Frontend markdown: need to install `react-markdown` + `remark-gfm`
