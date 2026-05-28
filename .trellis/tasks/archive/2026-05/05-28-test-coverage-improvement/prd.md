# test-coverage-improvement

## Goal

Raise test coverage for the backend settings API, frontend route components, and shell components that currently have zero tests — closing the most impactful gaps without over-testing internals.

## What I already know

* **Backend**: 28 test files, ~310 tests passing. Settings module (`api/settings.py`) and its HTTP endpoints (`GET/PUT /api/settings`) have zero tests. Wiki router endpoints have no integration tests.
* **Frontend**: 9 test files, 38 tests passing. 5 of 8 routes have zero tests (concept, paper-index, paper, queries, query-detail). 4 of 5 shell components untested (app-shell, app-sidebar, health-banner, theme-toggle). Settings route test exists but only covers initial render.
* **Conventions**: Frontend uses Vitest + @testing-library/react + jsdom, with `vi.mock("@/lib/api")` pattern and `createMemoryHistory` router setup. Backend uses pytest + FastAPI `TestClient` with stub injection via `create_app(translation_service=stub)`.
* **No conftest.py** in backend — all test files create data/stubs inline.

## Assumptions

* Focus on route-level integration tests (render + data flow) rather than exhaustive unit tests of every helper.
* Shell component tests verify structural rendering (sidebar links, health banner states) rather than deep interaction.
* LLM provider tests are out of scope — they'd need real API keys or heavy mocking with low ROI.

## Requirements

### Backend — settings module + endpoint tests

* Add `backend/tests/test_settings.py` covering:
  - `AppSettings` model validation (valid data, defaults, extra fields rejected)
  - `UpdateSettingsRequest` model (partial update, null fields, extra fields rejected)
  - `load_settings` (missing file → defaults, valid file, corrupted JSON → defaults)
  - `save_settings` (atomic write, round-trip with load)
  - `merge_settings` (partial update overrides, null fields preserved, full update)
* Add endpoint tests in same file for `GET /api/settings` and `PUT /api/settings`:
  - GET returns defaults when no settings file exists
  - PUT creates settings file and returns updated settings
  - PUT partial update preserves existing fields
  - Strict model — extra fields in request body → 422

### Frontend — critical route tests

* `paper-index` route: verify renders paper list from API mock
* `queries` route: verify renders query list from API mock
* `concept` route: verify renders concept detail from API mock

### Frontend — shell component tests

* `app-sidebar`: verify sidebar links render, settings link navigates
* `health-banner`: verify renders health status from API mock

## Acceptance Criteria

- [ ] `backend/tests/test_settings.py` exists with tests for AppSettings model, load, save, merge, and HTTP endpoints
- [ ] `frontend/tests/routes/paper-index.test.tsx` exists and passes
- [ ] `frontend/tests/routes/queries.test.tsx` exists and passes
- [ ] `frontend/tests/routes/concept.test.tsx` exists and passes
- [ ] `frontend/tests/components/shell/app-sidebar.test.tsx` exists and passes
- [ ] `frontend/tests/components/shell/health-banner.test.tsx` exists and passes
- [ ] All backend tests pass: `cd backend && python -m pytest -x -q`
- [ ] All frontend tests pass: `cd frontend && npx vitest run`
- [ ] No regressions in existing tests

## Definition of Done

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* No dead code or TODO comments left behind

## Out of Scope

* LLM provider tests (anthropic, gemini, ollama, openai_compat) — requires real API keys
* CLI command tests (init_cmd, show_cmd, etc.) — low ROI for this sprint
* Wiki router endpoint integration tests — separate concern
* `api/wiki_router.py` `_resolve_model` tests (covered indirectly via settings test)
* Frontend routes `paper.tsx` and `query-detail.tsx` — lower priority, can be covered in a later task
* Frontend shell components `app-shell.tsx` and `theme-toggle.tsx` — thin wrappers, low ROI
* Extending existing `settings.test.tsx` with interaction tests — render test is sufficient for now

## Decision (ADR-lite)

**Context**: 5 untested routes, 4 untested shell components, and a completely untested backend settings module. Full coverage sweep would take too long for this sprint.
**Decision**: Option 2 — backend settings tests (full) + 3 highest-value frontend route tests + 2 shell component tests.
**Consequences**: Paper route, query-detail route, app-shell, and theme-toggle remain untested. Coverage goes from ~0% to meaningful on the most user-facing components. Can extend in a follow-up task.

## Technical Notes

* Frontend test pattern: `createMemoryHistory` + `RouterProvider` + `QueryClientProvider` + `ThemeProvider` wrapper; `vi.mock("@/lib/api")` for API calls
* Backend test pattern: `TestClient(create_app())` for endpoints; `tmp_path` fixture for file-based tests; `create_app(translation_service=stub)` for dependency injection
* Settings file: `~/.xreadagent/settings.json` — use `tmp_path` fixture to avoid touching real home directory