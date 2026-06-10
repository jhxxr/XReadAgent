# Redesign Settings UX and Language Switching

## Goal

Make Settings easier to scan and add a persistent UI language switch so users can
choose English or Simplified Chinese from the desktop renderer.

## Requirements

- Add a persisted `language` setting with supported values `en` and `zh`; default
  to `zh`.
- Preserve compatibility with existing settings files that only contain `model`
  and `workspacePath`.
- Add an app-wide renderer language provider/hook with a typed local dictionary.
- Persist language changes through the existing `/api/settings` flow and apply
  them immediately in the UI.
- Redesign the Settings route into clearer sections for General, Language, and
  Sidecar without adding new runtime dependencies.
- Localize the settings screen, settings sidecar panel, and primary app sidebar
  labels for the MVP.
- Keep model/workspace editing behavior intact, including syncing saved workspace
  paths to the existing workspace localStorage helper.

## Acceptance Criteria

- [ ] `GET /api/settings` returns `language` along with existing fields.
- [ ] `PUT /api/settings` accepts a partial `language` update and rejects invalid
      language values.
- [ ] Existing two-field settings JSON loads successfully and returns
      `language: "zh"`.
- [ ] Settings shows a language selector with English and Simplified Chinese.
- [ ] Changing language updates visible settings/sidebar labels immediately and
      persists the choice.
- [ ] Existing settings route tests still pass, with added coverage for language.
- [ ] Backend settings tests cover defaults, merge, persistence, and API roundtrip.

## Definition of Done

- Frontend lint, typecheck, and relevant tests pass.
- Backend ruff, mypy, and relevant settings tests pass.
- No new UI or i18n runtime dependency is introduced.
- Spec update considered after implementation.

## Technical Approach

Extend the existing settings schema instead of creating a separate preference
store. In the renderer, add `frontend/src/lib/i18n.tsx` following the existing
ThemeProvider pattern: Context + Provider + hook, SSR-safe localStorage cache,
TanStack Query reconciliation, and a `t(key)` translator.

Use a small typed dictionary for the UI strings touched by this task. The
Settings page uses vertical tabs on desktop and compact tabs on small screens,
with separate panels for General, Language, and Sidecar.

## Decision (ADR-lite)

Context: The app needs a UI language preference, but the renderer currently has
no localization infrastructure and a modest string surface.

Decision: Use a typed local dictionary and the existing settings API for the MVP.

Consequences: This avoids dependency and build churn, but future broad
localization may need extraction into locale files or a dedicated i18n library.

## Out of Scope

- Translating generated wiki/content data, PDF translation outputs, backend logs,
  or native Electron application menus.
- Adding languages beyond English and Simplified Chinese.
- Browser/OS automatic language detection.
- Refactoring every renderer string in the app; MVP covers settings and primary
  navigation chrome.

## Technical Notes

- Research: `research/settings-language-architecture.md`
- Relevant specs: `.trellis/spec/frontend/*`, `.trellis/spec/backend/*`, and
  `.trellis/spec/guides/cross-layer-thinking-guide.md`.
- Settings persistence is file-based and atomic through `wiki/atomic.py`.
- App-wide UI state should use Context only for rare-changing, app-wide concerns;
  language matches that rule.
