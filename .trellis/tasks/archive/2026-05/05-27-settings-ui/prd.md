# Settings UI: LLM Provider and Workspace Configuration

## Goal

Add a settings page so users can configure the LLM model and workspace path from the UI instead of relying on env vars and localStorage hacks. This makes the app self-service and removes the need to restart the backend to change models.

## What I already know

- Model config: `_resolve_model()` in `wiki_router.py` checks request body `model` field, then `XREAD_AGENT_MODEL` env var. Format: `provider:model` (e.g. `openai:gpt-4o`)
- API keys: env vars only (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`)
- Workspace path: stored in localStorage under `xreadagent.workspacePath`, passed per-request
- Sidebar has a disabled "Settings" button labeled "Phase 2" (`app-sidebar.tsx:93-106`)
- No backend settings endpoints exist
- No settings route in frontend router
- `LLMGateway` + `LLMGatewayConfig` exist in `llm/` but are unused by agents (LangChain's `init_chat_model()` is used instead)
- `AnthropicProvider` in `llm/providers/anthropic.py` is a stub (raises `NotImplementedError`)
- Only `OpenAICompatProvider` has a real implementation

## Requirements

### R1: Backend — Settings API
- `GET /api/settings` — returns current settings (model, workspace path)
- `PUT /api/settings` — updates settings (persisted to a JSON file on disk)
- Settings file: `~/.xreadagent/settings.json` or workspace-relative
- Fields: `model` (string), `workspacePath` (string)
- API keys stay as env vars (security: don't persist secrets to disk via HTTP)

### R2: Frontend — Settings Page
- New route `/settings` with a form
- Model input: text field with placeholder `provider:model` (e.g. `openai:gpt-4o`)
- Workspace path: text field with browse hint
- Save button → PUT /api/settings
- Load current settings on mount via GET /api/settings

### R3: Frontend — Sidebar Integration
- Enable the "Settings" button in the sidebar (remove "Phase 2" label)
- Navigate to `/settings` on click

## Acceptance Criteria

- [ ] `GET /api/settings` returns current model and workspace path
- [ ] `PUT /api/settings` persists settings to disk
- [ ] Settings page renders with form fields
- [ ] Save button updates settings via API
- [ ] Sidebar "Settings" button navigates to `/settings`
- [ ] Model setting is used by ingest/query endpoints when not overridden in request
- [ ] Frontend typecheck, lint, and tests pass
- [ ] Backend ruff and mypy clean

## Out of Scope

- API key configuration via UI (security concern, keep as env vars)
- Provider-specific settings (base URL, temperature, etc.)
- Settings validation (e.g., checking if model string is valid)
- Multi-workspace support
- Settings import/export

## Technical Notes

- Backend entry: `backend/src/xreadagent/api/main.py`
- Model resolution: `backend/src/xreadagent/api/wiki_router.py` (`_resolve_model()`)
- Sidebar: `frontend/src/components/shell/app-sidebar.tsx`
- Router: `frontend/src/router.tsx`
- Existing localStorage: `frontend/src/lib/workspace.ts`
