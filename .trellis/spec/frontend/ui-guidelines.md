# UI Guidelines

## Product Feel

XReadAgent is a desktop research workspace. UI should feel dense, calm, and task-focused: navigation, reading, importing, querying, settings, and sidecar diagnostics matter more than marketing-style presentation.

Reference files: `frontend/src/components/shell/app-shell.tsx`, `frontend/src/routes/workspace.tsx`, `frontend/src/routes/settings.tsx`.

## Component System

Use the existing shadcn/Radix-style primitives under `frontend/src/components/ui` before adding new primitives:

- `Button`
- `Card`
- `Dialog`
- `Input`
- `ScrollArea`
- `Separator`
- `Tabs`
- `Tooltip`
- `Badge`
- `Skeleton`

Icons come from `lucide-react`. Follow existing patterns such as `SaveIcon`, `ServerIcon`, `RefreshCwIcon`, and status icons in `SidecarTab`.

## Layout

- Prefer full-height work surfaces with stable headers and scrollable content areas.
- Cards are appropriate for settings panels and repeated content, but avoid nesting cards inside cards.
- Keep border radius modest (`rounded-md` is common).
- Preserve responsive constraints for route layouts and reader surfaces.
- Avoid hero/landing-page treatment for app screens.

## Internationalization

Use `useI18n()` and translation keys for user-facing UI text where the existing route/component already uses i18n. Do not hardcode new persistent UI copy inside translated surfaces unless the surrounding file is currently English-only and no translation structure exists.

Reference files: `frontend/src/lib/i18n.tsx`, `frontend/src/routes/settings.tsx`.

## Electron-Aware UI

Electron-only controls need browser-mode fallbacks. `SidecarTab` shows a browser-mode notice instead of trying to call native sidecar IPC.

When a control depends on `window.electronAPI`, gate it with `isElectron()` / `getElectronAPI()` and provide a clear disabled or fallback state.

## Anti-Patterns

- Do not add visible instructional text that explains implementation mechanics unless the user needs it to complete a task.
- Do not make app pages look like landing pages.
- Do not create one-off visual primitives when an existing UI component fits.
- Do not let long status/log lines overflow without wrapping or scroll containment.
