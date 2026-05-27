# Copilot Sidebar: In-App Ask/Answer with Evidence

## Goal

Replace the placeholder CopilotSidebar with a functional conversational research interface. Users can ask questions about their wiki from any page, get answers backed by their ingested documents, and see cited evidence — completing the "research loop" (ingest → browse → query → ask).

## What I already know

- A `CopilotSidebar` placeholder already exists at `frontend/src/components/shell/copilot-sidebar.tsx` — slides in from right, shows "Coming in Phase 2"
- `AppShell` layout already has a slot for it (right sidebar area)
- `POST /api/query` endpoint works — returns `QueryResultResponse` with `answer`, `confidence`, `sources[]`, `queryPagePath`, `filesTouched`, `durationS`
- `QueryAnswer` schema (backend): `question`, `answer_markdown`, `evidence[]` (source_wiki_path, quote, confidence), `sources_cited[]`, `confidence`, `open_questions_raised[]`, `notes[]`
- QueryAgent takes `(workspace, model)` and calls `answer_query(workspace, question, topic?)`
- Query results are archived to `wiki/queries/{topic}/{date}-{slug}.md`
- Backend has no streaming/SSE for queries currently — synchronous JSON only
- WebSocket exists for translation job events — pattern could be reused
- Frontend uses TanStack Query, typed `request<T>()` helper, shadcn/ui components
- Available shadcn components: Button, Card, Dialog, Input, ScrollArea, Separator, Skeleton, Toaster, Tooltip, Badge, Tabs
- `WikiMarkdown` component already handles `[[wiki-links]]` and markdown rendering

## Assumptions (temporary)

- Sidebar should be toggleable (not always visible) to preserve screen real estate
- Query model comes from env var / settings (same as POST /api/query)
- MVP doesn't need conversation history persisted — each session is standalone
- Evidence = list of source files cited by the agent with quotes and confidence

## Open Questions

(none — all resolved)

## Decision (ADR-lite)

**Context**: Existing sidebar uses Radix Dialog (modal overlay with backdrop). A copilot should let users browse wiki pages while asking questions.

**Decision**: Switch to a plain slide-in panel (no backdrop, page content still clickable). Keep the floating trigger button.

**Consequences**: Better UX for research workflow. Slightly more CSS work to position the panel. No Radix Dialog dependency needed for this component.

## Requirements

### R1: Copilot Sidebar UI
- Replace placeholder with a non-modal slide-in panel (right side, full height)
- Floating trigger button (bottom-right, same as current)
- Text input at bottom of panel, message history above
- Show loading state while query is in progress
- Display answer with markdown rendering (reuse WikiMarkdown)
- Display evidence panel: source paths, quotes, confidence badges

### R2: Query Integration
- Call existing POST /api/query on submit
- Parse and display the full QueryResultResponse
- Handle errors gracefully (network, validation, empty wiki)

### R3: Evidence Display
- List cited evidence with source wiki path (clickable link to wiki page)
- Show quoted text from each source
- Confidence badge (high/medium/low) per evidence item

## Acceptance Criteria

- [ ] Non-modal slide-in panel opens/closes via floating button (no backdrop)
- [ ] Can type a question and submit (Enter or button click)
- [ ] Answer renders as markdown with wiki-links
- [ ] Evidence panel shows cited sources with quotes
- [ ] Confidence badges display correctly (high/medium/low)
- [ ] Loading spinner shown during query
- [ ] Error message shown on failure
- [ ] Links in evidence navigate to wiki pages
- [ ] Message history preserved while sidebar is open
- [ ] ScrollArea scrolls to latest message
- [ ] New frontend tests pass
- [ ] Frontend typecheck, lint, and tests pass
- [ ] No regressions in existing features

## Definition of Done

- Tests added/updated (unit/integration where appropriate)
- Lint / typecheck / CI green
- Backend ruff and mypy clean
- No regressions in existing features

## Out of Scope (explicit)

- Streaming/SSE for query responses (future enhancement)
- Conversation persistence across sessions
- Crystallize UI (propose/apply workflow)
- Settings UI / model configuration
- File upload for ingest
- R-LINT agent

## Technical Notes

- Backend entry: `backend/src/xreadagent/api/main.py`
- Query agent: `backend/src/xreadagent/agents/query.py`
- Query schema: `backend/src/xreadagent/agents/query_schema.py`
- Existing placeholder: `frontend/src/components/shell/copilot-sidebar.tsx`
- App shell: `frontend/src/components/shell/app-shell.tsx`
- WikiMarkdown: `frontend/src/components/wiki/wiki-markdown.tsx`
- API helpers: `frontend/src/lib/api.ts`
- Types: `frontend/src/types/api.ts`
- Existing `postQuery()` in api.ts already wired up
