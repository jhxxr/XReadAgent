# Fix PDF Import 422

## Goal

Fix the desktop import failure experience where importing a PDF shows only
`Sidecar returned 422 on /ingest`, hiding the FastAPI error detail that explains
why the backend rejected the request.

## What I Already Know

* The user reported a PDF import failure and provided a screenshot showing the
  toast: `Import failed` / `Sidecar returned 422 on /ingest`.
* `POST /api/ingest` accepts `workspacePath`, `filePath`, optional `title`, and
  optional `model`.
* The backend intentionally returns 422 for missing model, missing file, and
  ingest/conversion `ValueError`s.
* The frontend `request()` helper currently throws a generic `ApiError` for all
  non-2xx responses and does not parse the JSON error body.
* Settings can provide the default model, so the import request does not need to
  duplicate that value from the frontend.

## Requirements

* Preserve the strict backend ingest contract.
* Surface backend error detail in frontend API errors when the response body has
  a FastAPI-style `detail` payload.
* Keep a sensible fallback for non-JSON or malformed error responses.
* Cover the behavior with frontend API client tests.

## Acceptance Criteria

* [x] A 422 JSON response like `{"detail":"No model specified..."}` produces an
  `ApiError.message` containing that detail.
* [x] Existing generic handling still works for non-JSON error responses.
* [x] Import failures show a useful toast description because
  `useWorkspaceActions` already displays `error.message`.
* [x] Targeted frontend tests pass.

## Definition of Done

* Tests added or updated for the API client error detail behavior.
* Relevant frontend checks pass.
* No unrelated refactors or UI layout changes.

## Technical Approach

Add a small shared parser in `frontend/src/lib/api.ts` that reads the response
body on non-2xx responses and extracts a human-readable `detail` string. Use it
from the generic `request()` helper and the specialized helpers that perform
their own fetch/error handling.

## Out of Scope

* Changing the backend's 422 status semantics.
* Adding model setup UI or storing API keys.
* Bypassing the requirement that ingest needs a configured model.

## Technical Notes

* Backend route: `backend/src/xreadagent/api/wiki_router.py`.
* Frontend API client: `frontend/src/lib/api.ts`.
* Import mutation/toast: `frontend/src/lib/use-workspace-actions.ts`.
* Existing frontend tests: `frontend/tests/lib/api.test.ts`.
