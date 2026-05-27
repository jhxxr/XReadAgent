# Research: Settings/Configuration Infrastructure Exploration

- **Query**: Understand current settings/configuration infrastructure across backend and frontend
- **Scope**: internal
- **Date**: 2026-05-27

## Findings

### 1. Current Model Configuration

**Model string format**: `provider:model` (e.g. `openai:gpt-4o`, `anthropic:claude-sonnet-4-6`, `google_genai:gemini-2.5-pro`, `ollama:llama3.1:70b`)

**Resolution chain** (two separate paths):

- **CLI path** (`backend/src/xreadagent/cli/ingest_cmd.py`, `query_cmd.py`): Model is passed as a `--model` CLI flag. The CLI calls `ensure_provider_credentials(model)` from `cli/env.py` which checks the required env var is set.

- **API path** (`backend/src/xreadagent/api/wiki_router.py:122-135`): The `_resolve_model()` helper checks:
  1. `model` field from the request body (optional)
  2. `XREAD_AGENT_MODEL` env var (fallback)
  3. Raises HTTP 422 if neither is set

**Key env var**: `XREAD_AGENT_MODEL` -- the only env var for specifying which model to use.

**Files**:
| File Path | Description |
|---|---|
| `backend/src/xreadagent/api/wiki_router.py` | `_resolve_model()` at line 122 -- model resolution for API |
| `backend/src/xreadagent/cli/env.py` | `required_env_var_for_model()` at line 107 -- provider-to-env-var mapping |
| `backend/src/xreadagent/cli/llm_flags.py` | CLI flags for `--model`, `--header`, `--max-tokens`, `--env-override` |
| `backend/src/xreadagent/llm/gateway.py` | `_split_model()` at line 57 -- parses `provider:model` string |
| `backend/src/xreadagent/agents/_defaults.py` | `DEFAULT_AGENT_MAX_TOKENS = 16384` |

### 2. Backend Settings/Config Module

**There is NO dedicated settings.py or config.py for the backend application.** Configuration is distributed:

- **LLM config** (`backend/src/xreadagent/llm/config.py`): Pydantic models `ProviderConfig` (base_url, api_key, default_headers) and `LLMGatewayConfig` (providers dict). However, these are NOT wired to any persistent storage -- they are constructed programmatically.

- **Env loading** (`backend/src/xreadagent/cli/env.py`): A minimal `.env.local` parser (no python-dotenv dependency). Loads from workspace root or CWD. Supports `override=True` mode for agent sandboxes.

- **No centralized config file**: The backend has no `settings.json`, `config.yaml`, or similar. All configuration flows through env vars or per-request body fields.

**Provider-to-API-key mapping** (from `cli/env.py:29-36`):
```
openai       -> OPENAI_API_KEY
anthropic    -> ANTHROPIC_API_KEY
google_genai -> GOOGLE_API_KEY
google       -> GOOGLE_API_KEY
gemini       -> GOOGLE_API_KEY
ollama       -> (none needed)
```

**Files**:
| File Path | Description |
|---|---|
| `backend/src/xreadagent/llm/config.py` | Pydantic config models (ProviderConfig, LLMGatewayConfig) |
| `backend/src/xreadagent/cli/env.py` | `.env.local` parser, provider credential validation |
| `.env.example` | Template showing all supported env vars |
| `.env.local` | Actual local env (contains ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL) |

### 3. Frontend Settings UI

**There is NO settings page or route.** The sidebar has a disabled "Settings" button labeled "Phase 2":

- `frontend/src/components/shell/app-sidebar.tsx:93-106`: The Settings button is `disabled` with a "Phase 2" badge.

**Router** (`frontend/src/router.tsx`): No `/settings` route exists. Current routes: `/workspace`, `/paper`, `/paper/$slug`, `/paper/$slug/read`, `/concept/$slug`, `/queries`, `/query/$topic/$slug`.

**Existing localStorage usage**:
| Key | Module | Purpose |
|---|---|---|
| `xreadagent.workspacePath` | `frontend/src/lib/workspace.ts` | Workspace path persistence |
| `xreadagent.theme` | `frontend/src/lib/theme.tsx` | Theme preference (light/dark/system) |

**Files**:
| File Path | Description |
|---|---|
| `frontend/src/components/shell/app-sidebar.tsx` | Disabled Settings button at line 93 |
| `frontend/src/router.tsx` | Route definitions (no settings route) |
| `frontend/src/lib/workspace.ts` | `readWorkspacePath()` / `writeWorkspacePath()` localStorage helpers |
| `frontend/src/lib/theme.tsx` | Theme localStorage pattern (good reference for settings storage) |

### 4. Workspace Path Configuration

**Storage**: `localStorage` under key `xreadagent.workspacePath` (`frontend/src/lib/workspace.ts`).

**Usage pattern**: Every API call requires `workspacePath` as a query parameter or request body field. The frontend reads it from localStorage and passes it to every API function:
- `getPapers(workspacePath)`, `getConcepts(workspacePath)`, etc. -- query param
- `postIngest({ workspacePath, ... })`, `postQuery({ workspacePath, ... })` -- body field
- `postTranslate({ workspacePath, ... })` -- body field

**Backend handling**: `_open_workspace()` in both `api/main.py:219-239` and `api/wiki_router.py:105-119` validates the path exists and is a directory, then wraps it in a `Workspace` object.

**No workspace picker UI exists.** The sidebar shows "Workspace > Default" as a static button (`app-sidebar.tsx:45-59`). The `WorkspaceRoute` reads from localStorage and shows `WorkspaceEmptyState` if empty.

**Files**:
| File Path | Description |
|---|---|
| `frontend/src/lib/workspace.ts` | localStorage read/write for workspace path |
| `frontend/src/routes/workspace.tsx` | Uses `readWorkspacePath()` at line 226 |
| `frontend/src/components/shell/copilot-sidebar.tsx` | Uses `readWorkspacePath()` at line 250 |
| `frontend/src/components/reader/translate-dialog.tsx` | Receives `workspacePath` as prop |
| `backend/src/xreadagent/wiki/workspace.py` | `Workspace` dataclass with all path derivations |

### 5. API Key Handling

**Two distinct patterns exist**:

**Pattern A -- Env vars (CLI + ingest/query API)**:
- API keys are read from environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)
- Loaded via `.env.local` file or shell exports
- The LangChain `init_chat_model()` reads these automatically from the env
- The `LLMGatewayConfig` / `ProviderConfig` in `llm/config.py` has `api_key` fields but they are NOT populated from env vars -- the LangChain path bypasses the gateway entirely

**Pattern B -- Request body (translate API)**:
- `POST /api/translate` accepts `apiKey` and `baseUrl` in the request body (`api/main.py:73-74`)
- These are passed through to `TranslationRequest` -> `ChatConfig` -> the BabelDOC worker subprocess
- The frontend `TranslateDialog` does NOT currently send `apiKey`/`baseUrl` (the fields exist in the TypeScript type but the dialog doesn't populate them)

**Important note**: The `IngestAgent` and `QueryAgent` use LangChain's `init_chat_model()` which reads API keys from env vars automatically. The custom `LLMGateway` class exists but is NOT used by the agent layer -- it's a parallel implementation.

**Files**:
| File Path | Description |
|---|---|
| `backend/src/xreadagent/cli/env.py` | `_PROVIDER_KEY_ENV` mapping, `ensure_provider_credentials()` |
| `backend/src/xreadagent/llm/providers/openai_compat.py` | Uses `config.api_key` for Authorization header |
| `backend/src/xreadagent/agents/ingest.py` | `_make_default_planner()` uses LangChain `init_chat_model()` |
| `backend/src/xreadagent/api/main.py` | `TranslateRequest` has `apiKey`/`baseUrl` fields |
| `backend/src/xreadagent/translation/service.py` | `TranslationRequest` has `api_key`/`base_url` fields |
| `frontend/src/types/api.ts` | `TranslateRequest` type has `apiKey?`/`baseUrl?` |

### 6. Existing Settings Patterns

**No `POST /api/settings` or `GET /api/settings` endpoint exists.** Grep found zero matches for settings endpoints.

**No frontend settings storage beyond theme and workspace path.** No `xreadagent.settings` or similar localStorage key.

**Existing patterns to build on**:

1. **Theme pattern** (`lib/theme.tsx`): React Context + localStorage. `ThemeProvider` wraps the app, `useTheme()` hook exposes `theme`/`setTheme`. This is the cleanest reference for a settings context.

2. **Workspace path pattern** (`lib/workspace.ts`): Simple localStorage read/write functions without React context. Used directly by route components.

3. **Translate dialog pattern** (`translate-dialog.tsx`): Shows how model string is entered inline (text input with default `anthropic:claude-3-7-sonnet-latest`). No persistence of the model choice.

4. **Copilot sidebar pattern** (`copilot-sidebar.tsx`): Reads workspace from localStorage, passes to `postQuery()`. Does NOT pass model -- the backend resolves it from `XREAD_AGENT_MODEL` env var.

### 7. Summary of Gaps (for reference only)

- No settings page/route exists
- No centralized frontend settings storage (beyond theme + workspace path)
- No backend settings endpoint
- Model string is not persisted from the frontend (only env var or per-request)
- API keys are env-var only for ingest/query; translate accepts them in request body but the UI doesn't send them
- The `LLMGateway` + `LLMGatewayConfig` classes exist but are unused by the agent layer (LangChain is used instead)
- The sidebar Settings button is disabled with "Phase 2" label

### Related Specs

- `.trellis/spec/frontend/directory-structure.md` -- frontend directory conventions
- `.trellis/spec/frontend/component-guidelines.md` -- component patterns
- `.trellis/spec/frontend/hook-guidelines.md` -- hook patterns (relevant for settings context)
- `.trellis/spec/frontend/state-management.md` -- state management patterns
- `.trellis/spec/backend/directory-structure.md` -- backend directory conventions

## Caveats / Not Found

- The `LLMGateway` class in `llm/gateway.py` is a custom provider-agnostic abstraction, but the actual agents use LangChain's `init_chat_model()` instead. These are two parallel systems.
- The `AnthropicProvider` in `llm/providers/anthropic.py` is a stub (`NotImplementedError`). Only `OpenAICompatProvider` has a real implementation.
- The `.env.local` file contains a real API key and base URL for a proxy (`cch.xinr.de`). This is sensitive.
