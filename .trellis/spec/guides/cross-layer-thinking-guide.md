# Cross-Layer Thinking Guide

Use this guide before implementing a change that crosses backend, frontend, Electron, CLI, MCP, or workspace storage boundaries.

## Why This Matters Here

XReadAgent bugs often happen at protocol and filesystem boundaries:

- Backend Pydantic model changes but `frontend/src/types/api.ts` stays stale.
- HTTP JSON uses camelCase while WebSocket events intentionally use snake_case.
- Electron gets a new native capability but the preload/frontend type boundary is incomplete.
- A workspace mutation touches `wiki/`, `state/`, or `translations/` outside the owning flow.
- Vite dev proxy, Electron direct sidecar URLs, and packaged SPA serving drift apart.

## Before Implementing Cross-Layer Features

### 1. Map The Data Flow

Write the concrete path in terms of this repo's layers:

```text
Electron/native input -> renderer action -> frontend API client -> FastAPI route -> service/orchestrator -> workspace files -> API response/event -> renderer state
```

Trim the path to the layers the task actually touches, then name the files at each boundary.

### 2. Identify Contracts

For each boundary, decide:

- HTTP or WebSocket?
- camelCase or snake_case?
- Absolute filesystem path or workspace-relative POSIX path?
- Sync response or background job with `/ws/jobs/{jobId}`?
- Which layer validates input?
- Which tests prove the round trip?

### 3. Update Both Sides Together

Common paired files:

- Backend API model: `backend/src/xreadagent/api/*.py`
- Frontend API type: `frontend/src/types/api.ts`
- Frontend API helper: `frontend/src/lib/api.ts`
- Electron preload type/API: `electron/src/preload.ts`, `frontend/src/types/electron.d.ts`
- Workspace layout: `backend/src/xreadagent/wiki/workspace.py`, `backend/src/xreadagent/wiki/paths.py`

## Checklist

Before implementation:

- [ ] Read `.trellis/spec/cross-layer/index.md`.
- [ ] Listed every layer and file boundary touched by the task.
- [ ] Decided naming/casing at each protocol boundary.
- [ ] Decided whether the flow is synchronous or job-based.
- [ ] Searched for existing helpers before adding new ones.

After implementation:

- [ ] Backend and frontend schemas are aligned.
- [ ] Error behavior is tested at the boundary where users see it.
- [ ] Workspace writes stay inside the owning operation's allowed area.
- [ ] Browser dev and Electron modes still resolve URLs correctly.
- [ ] Relevant backend/frontend/electron tests were run.

## When To Create Flow Documentation

Create or update a spec/technical note when a flow:

- Touches three or more layers.
- Introduces a new event or persisted manifest shape.
- Changes workspace mutation boundaries.
- Has already caused a regression.
