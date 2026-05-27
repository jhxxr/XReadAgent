# Research: Copilot Sidebar Codebase Exploration

- **Query**: Explore the XReadAgent codebase for building a Copilot Sidebar feature
- **Scope**: internal
- **Date**: 2026-05-27

## 1. Backend Agent Architecture

### Overview

All agents live under `backend/src/xreadagent/agents/`. There are three main agents following a consistent pattern:

| Agent | File | Orchestrator | Purpose |
|---|---|---|---|
| `IngestAgent` | `agents/ingest.py` | `agents/orchestrator.py` | Ingest a PDF/document into the wiki |
| `QueryAgent` | `agents/query.py` | `agents/query_orchestrator.py` | Answer a question from the wiki knowledge base |
| `CrystallizeAgent` | `agents/crystallize.py` | (inline `apply_crystallize`) | Promote query results into wiki pages |

### Common Agent Pattern

All three agents follow the same structure:

1. **Pluggable planner protocol** -- e.g. `QueryPlanner` is a `Protocol` with `__call__(prompt, schema) -> QueryAnswer`. Tests inject stubs; production uses LangChain.
2. **Constructor** takes `workspace`, `model` (string), optional `system_prompt`, optional `planner`, optional `headers`, `planner_method` (`"auto" | "tool" | "json"`), `max_tokens`.
3. **Single async method** that builds a prompt from workspace state, calls the planner, returns a typed result:
   - `IngestAgent.ingest(source, extract_path) -> IngestResult`
   - `QueryAgent.answer(question, topic?) -> QueryAgentOutcome`
   - `CrystallizeAgent.propose(query_archive_path) -> CrystallizeProposal`
4. **Prompt construction**: bundles system prompt + workspace state summary (existing papers/concepts) + the input data into a single string.
5. **Default planner**: uses `langchain.chat_models.init_chat_model` + `with_structured_output(Schema)` for tool-based structured output, with JSON-mode fallback on validation errors.

### Agent Construction Example (QueryAgent)

```python
# From wiki_router.py:298-312
workspace = _open_workspace(req.workspacePath)
model = _resolve_model(req.model)
agent = QueryAgent(workspace, model=model)
result = await answer_query(workspace, req.question, agent=agent, topic=req.topic)
```

The model string comes from the request body or `XREAD_AGENT_MODEL` env var.

### QueryAgent Return Shape

`QueryAgent.answer()` returns `QueryAgentOutcome`:
- `answer: QueryAnswer` -- structured Pydantic model with `question`, `answer_markdown`, `evidence: list[CitedEvidence]`, `sources_cited`, `layers_used`, `confidence`, `open_questions_raised`, `notes`
- `tokens_used: dict`
- `duration_s: float`

The orchestrator `answer_query()` wraps this into `QueryResult` which adds `query_page_path` and `files_touched`, and persists to `wiki/queries/{topic}/{date}-{slug}.md`.

### Key Files

| File Path | Description |
|---|---|
| `backend/src/xreadagent/agents/__init__.py` | Public API surface for agents package |
| `backend/src/xreadagent/agents/ingest.py` | IngestAgent + apply_plan |
| `backend/src/xreadagent/agents/query.py` | QueryAgent + QueryResult |
| `backend/src/xreadagent/agents/query_schema.py` | QueryAnswer, CitedEvidence Pydantic models |
| `backend/src/xreadagent/agents/query_orchestrator.py` | answer_query() orchestrator |
| `backend/src/xreadagent/agents/crystallize.py` | CrystallizeAgent + apply_crystallize |
| `backend/src/xreadagent/agents/orchestrator.py` | ingest_source() orchestrator |
| `backend/src/xreadagent/agents/_defaults.py` | DEFAULT_AGENT_MAX_TOKENS |

## 2. Frontend Layout

### App Shell

`frontend/src/components/shell/app-shell.tsx` is the root layout:

```
+------------------------------------------+
| AppShell (flex h-screen w-screen)        |
| +--------+---------------------------+--+|
| |AppSide | Main content area         |Co||
| |bar     | (HealthBanner + Outlet)   |pi||
| |(260px) |                           |lo||
| |        |                           |t ||
| +--------+---------------------------+--+|
+------------------------------------------+
```

- `AppSidebar` -- 260px fixed left sidebar with nav links (Workspace, Papers, Queries)
- `<Outlet />` -- TanStack Router outlet for page content
- `CopilotSidebar` -- currently a placeholder "Coming in Phase 2" dialog triggered by a floating FAB button (bottom-right)

### Existing CopilotSidebar Placeholder

`frontend/src/components/shell/copilot-sidebar.tsx` already exists. It uses `@radix-ui/react-dialog` to render a right-side sheet (slides in from right, `max-w-md`, full height). Currently shows a "Coming in Phase 2" message. The trigger is a fixed-position floating button at bottom-right with a `SparklesIcon`.

Key UI details:
- Uses `DialogPrimitive.Root` with `open/onOpenChange` state
- Content panel: `fixed top-0 right-0 z-50 h-full w-full max-w-md border-l`
- Has slide-in/slide-out animations
- Header with title + close button
- Body is a centered placeholder

### Route Structure

Uses TanStack Router. Routes defined in `frontend/src/router.tsx`:

| Path | Component | Description |
|---|---|---|
| `/` | redirect to `/workspace` | |
| `/workspace` | `WorkspaceRoute` | Papers/Concepts/Queries tabs |
| `/paper` | `PaperIndexRoute` | Paper listing |
| `/paper/$slug` | `PaperRoute` | Single paper view |
| `/paper/$slug/read` | `PaperReadRoute` | PDF reader |
| `/concept/$slug` | `ConceptRoute` | Single concept view |
| `/queries` | `QueriesRoute` | Query listing |
| `/query/$topic/$slug` | `QueryDetailRoute` | Single query view |

All routes are children of the root route which renders `AppShell`.

### Key Files

| File Path | Description |
|---|---|
| `frontend/src/components/shell/app-shell.tsx` | Root layout: sidebar + main + copilot |
| `frontend/src/components/shell/app-sidebar.tsx` | Left nav sidebar (260px) |
| `frontend/src/components/shell/copilot-sidebar.tsx` | Copilot placeholder (Phase 2 target) |
| `frontend/src/components/shell/health-banner.tsx` | Health status banner |
| `frontend/src/components/shell/theme-toggle.tsx` | Theme toggle button |
| `frontend/src/router.tsx` | TanStack Router route tree |
| `frontend/src/routes/workspace.tsx` | Workspace page with tabs |
| `frontend/src/lib/workspace.ts` | Workspace path localStorage persistence |

## 3. Existing Query Flow (POST /api/query)

### End-to-End Flow

1. **Frontend** calls `postQuery(req: QueryRequest)` from `lib/api.ts:228-234`
   - Body: `{ workspacePath, question, topic?, model? }`
   - Returns: `QueryResultResponse`

2. **Backend** `wiki_router.py:298-324` handles `POST /query`:
   - Resolves workspace from `workspacePath`
   - Resolves model from request body or `XREAD_AGENT_MODEL` env var
   - Constructs `QueryAgent(workspace, model=model)`
   - Calls `answer_query(workspace, question, agent=agent, topic=topic)`

3. **Orchestrator** `query_orchestrator.py:114-179`:
   - Calls `agent.answer(question, topic=topic)` to get `QueryAgentOutcome`
   - Archives result to `wiki/queries/{topic}/{date}-{slug}.md`
   - Appends to `state/conversation-log.jsonl`
   - Returns `QueryResult` with answer, page path, files touched, duration

4. **Agent** `query.py:137-148`:
   - Builds prompt from system prompt + workspace state + question
   - Calls planner (LangChain structured output -> `QueryAnswer`)
   - Returns `QueryAgentOutcome`

### QueryAnswer Schema

```python
class QueryAnswer(BaseModel):
    question: str
    answer_markdown: str
    evidence: list[CitedEvidence]  # source_wiki_path, quote, confidence
    sources_cited: list[str]
    layers_used: list[RetrievalLayer]  # "index"|"papers"|"concepts"|"extracts"|"search"
    confidence: Confidence  # "high"|"medium"|"low"
    open_questions_raised: list[str]
    notes: list[str]
```

### Response Wire Shape

```typescript
interface QueryResultResponse {
  question: string;
  answer: string;
  confidence: string;
  sourcesCited: string[];
  queryPagePath: string;
  filesTouched: string[];
  durationS: number;
}
```

### Key Files

| File Path | Description |
|---|---|
| `backend/src/xreadagent/api/wiki_router.py` | HTTP endpoints for wiki + ingest + query |
| `backend/src/xreadagent/agents/query_orchestrator.py` | answer_query() orchestrator |
| `backend/src/xreadagent/agents/query.py` | QueryAgent implementation |
| `backend/src/xreadagent/agents/query_schema.py` | QueryAnswer Pydantic model |
| `frontend/src/lib/api.ts` | postQuery() frontend client |
| `frontend/src/types/api.ts` | QueryRequest, QueryResultResponse types |

## 4. UI Component Patterns

### Available shadcn/ui Components

All under `frontend/src/components/ui/`:

| Component | File |
|---|---|
| Button | `ui/button.tsx` |
| Card | `ui/card.tsx` |
| Dialog | `ui/dialog.tsx` |
| Input | `ui/input.tsx` |
| ScrollArea | `ui/scroll-area.tsx` |
| Separator | `ui/separator.tsx` |
| Skeleton | `ui/skeleton.tsx` |
| Toaster | `ui/toaster.tsx` |
| Tooltip | `ui/tooltip.tsx` |
| Badge | `ui/badge.tsx` |
| Tabs | `ui/tabs.tsx` |

### Existing Non-UI Components

| Component | File | Description |
|---|---|---|
| AppShell | `shell/app-shell.tsx` | Root layout |
| AppSidebar | `shell/app-sidebar.tsx` | Left navigation |
| CopilotSidebar | `shell/copilot-sidebar.tsx` | Copilot placeholder |
| HealthBanner | `shell/health-banner.tsx` | Health status |
| ThemeToggle | `shell/theme-toggle.tsx` | Dark/light toggle |
| WorkspaceEmptyState | `workspace/workspace-empty-state.tsx` | Empty workspace |
| TranslateDialog | `reader/translate-dialog.tsx` | Translation dialog |
| PdfViewer | `reader/pdf-viewer.tsx` | PDF viewer |
| WikiMarkdown | `wiki/wiki-markdown.tsx` | Markdown renderer |

### Patterns Observed

- Uses `@radix-ui/react-dialog` for modal/sheet patterns (CopilotSidebar, TranslateDialog)
- Uses `@tanstack/react-query` for data fetching (`useQuery` with query keys)
- Uses `lucide-react` for icons
- Tailwind CSS with `cn()` utility from `lib/utils.ts`
- TanStack Router for routing

## 5. API Patterns

### Frontend API Client

`frontend/src/lib/api.ts` exports typed async functions:

- `apiBase` defaults to `"/api"` (Vite proxies to `localhost:8765`)
- `wsBase` for WebSocket connections
- Generic `request<T>(path, init?)` helper that does `fetch` + JSON parse + error handling
- `ApiError` class for structured errors
- Each endpoint has its own exported function: `postQuery()`, `postIngest()`, `getPapers()`, etc.

### Request Pattern

```typescript
export async function postQuery(req: QueryRequest): Promise<QueryResultResponse> {
  return request<QueryResultResponse>("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}
```

### Type Definitions

`frontend/src/types/api.ts` defines all wire types with camelCase fields matching the backend Pydantic models.

### Key Files

| File Path | Description |
|---|---|
| `frontend/src/lib/api.ts` | API client functions |
| `frontend/src/types/api.ts` | TypeScript type definitions |
| `frontend/src/lib/utils.ts` | cn() utility |
| `frontend/src/lib/workspace.ts` | Workspace path persistence |

## 6. Streaming Support

### Current State

**No SSE/streaming endpoints exist for query or ingest.** The `POST /api/query` endpoint returns a synchronous JSON response after the full agent run completes.

### WebSocket Infrastructure

The backend does have WebSocket support for translation events:

- `WS /ws/jobs/{job_id}` -- streams `TranslationEvent` JSON objects for translation progress
- `WS /ws/events` -- echo WebSocket (test/dev endpoint)

The frontend has WebSocket URL support via `wsBase` in `lib/api.ts` and `buildJobEventsWsUrl()`.

### Streaming Comments in Code

- `orchestrator.py:6`: "the function is async to keep the door open for a future streaming variant"
- The translation service uses `async for event in service.event_stream(job_id)` pattern over WebSocket

### Implications for Copilot Sidebar

To add streaming query responses, the backend would need:
1. A new streaming endpoint (either SSE via `StreamingResponse` or WebSocket)
2. The QueryAgent would need to yield intermediate results

The frontend already has the WebSocket infrastructure (`wsBase`, `buildJobEventsWsUrl`) that could be extended.

## Caveats / Not Found

- The `CopilotSidebar` component already exists as a placeholder -- the task is to fill it in, not create from scratch.
- No `Sheet` or `Resizable` shadcn components exist yet -- the copilot uses raw Radix Dialog primitives.
- The `POST /api/query` endpoint is synchronous (no streaming). Adding streaming would require backend changes.
- The `@tanstack/react-query` is already set up and used throughout for data fetching.
- The workspace path is stored in localStorage and passed to all API calls.
