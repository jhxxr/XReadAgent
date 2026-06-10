# Settings and Language Architecture Research

## Existing Settings Flow

Backend settings live in `backend/src/xreadagent/api/settings.py` and persist as
`~/.xreadagent/settings.json`. The schema currently stores `model` and
`workspacePath`; `PUT /api/settings` accepts a partial update and merges non-null
fields before atomically saving JSON through `wiki/atomic.py`.

The FastAPI endpoints are defined inline in `backend/src/xreadagent/api/main.py`:
`GET /api/settings` returns `AppSettings`, and `PUT /api/settings` returns the
merged/saved settings.

The renderer mirrors that contract in `frontend/src/types/api.ts` and uses
`getSettings` / `putSettings` from `frontend/src/lib/api.ts`. The current settings
route (`frontend/src/routes/settings.tsx`) fetches settings with TanStack Query,
copies fields into local form state, and saves model/workspace with a mutation.

## Existing Language/I18n Surface

No existing UI i18n system, locale files, translation helper, or persisted UI
language preference exists. The word "translation" in the repo refers to
layout-preserving PDF translation, not renderer localization.

The closest app-wide UI state is `frontend/src/lib/theme.tsx`, which provides a
Context + Provider pair, safe localStorage persistence, and a hook. That is the
right local pattern for language because it is app-wide, rare-changing UI state.

## Recommended MVP

Add `language: "en" | "zh"` to the existing settings schema with default `"zh"`.
Old settings files continue to validate because the new field has a default.

Add a renderer `LanguageProvider` under `QueryClientProvider` so it can read the
existing `["settings"]` TanStack Query. It should seed from localStorage for fast
startup, then reconcile to the backend setting when `GET /settings` resolves.
Language changes should update local state immediately, write the
`xreadagent.language` localStorage cache, persist through `putSettings`, and update
the `["settings"]` query cache with the saved settings.

Use a typed local dictionary in `frontend/src/lib/i18n.tsx` for the MVP instead of
adding a new dependency. This keeps bundle/dependency churn low and matches the
small current renderer surface.

## Files Likely To Change

- `backend/src/xreadagent/api/settings.py`
- `backend/tests/test_settings.py`
- `frontend/src/types/api.ts`
- `frontend/src/lib/api.ts` only if helper behavior changes
- `frontend/src/lib/i18n.tsx`
- `frontend/src/app.tsx`
- `frontend/src/routes/settings.tsx`
- `frontend/src/components/shell/app-sidebar.tsx`
- `frontend/src/components/settings/sidecar-tab.tsx`
- frontend tests for settings/i18n/sidebar wrappers
