# Frontend Development Guidelines

> Best practices for XReadAgent's React renderer.

---

## Overview

The frontend (`frontend/`) is the desktop renderer for XReadAgent. It is:

- **React 19 + TypeScript (strict)** running on **Vite 6** with the `@vitejs/plugin-react` SWC pipeline.
- **TanStack Router** for client-side routes and **TanStack Query** for server state — the only "data fetching" target is the local Python sidecar (`/api/*` proxied to `127.0.0.1:8765` in dev, see `frontend/vite.config.ts:14`).
- **Tailwind CSS 4** (the CSS-first build, configured via `@tailwindcss/vite`) — design tokens live as CSS custom properties in `frontend/src/styles/globals.css`.
- **shadcn-style** UI primitives under `frontend/src/components/ui/` — local wrappers around Radix primitives with `class-variance-authority` (CVA) variants and a `data-slot="..."` styling hook.
- **Vitest + Testing Library + jsdom** for unit / component tests under `frontend/tests/`.

Phase 0+1 shipped the renderer skeleton: app shell (`AppShell` + `AppSidebar` + `HealthBanner` + `CopilotSidebar`), four routes (`/workspace`, `/paper`, `/paper/$slug`, `/queries`), a theme system, and a typed `apiBase` client with `ApiError`. Phase 2 wires real ingest/query/crystallize endpoints into the shell. Phase 3 wraps everything in Electron and adds dual-environment support via `platform.ts` (browser mode via Vite proxy, Electron mode via direct HTTP/WS to sidecar), native integrations (tray, menu, file associations, deep links, notifications), and a Sidecar status tab in Settings.

`AGPL-3.0-or-later`. Every TypeScript/TSX source file starts with an SPDX header — see `frontend/src/main.tsx:1`.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | `src/` layout, `@/*` alias, file naming, route ↔ component mirror | Filled (Phase 0+1) |
| [Component Guidelines](./component-guidelines.md) | Radix wrappers, CVA variants, `data-slot`, lucide icons, function vs `forwardRef` rules | Filled (Phase 0+1) |
| [Hook Guidelines](./hook-guidelines.md) | Context-provider pairs, TanStack Query queries, `react-refresh/only-export-components` carve-out | Filled (Phase 0+1) |
| [State Management](./state-management.md) | Server state in TanStack Query, theme in Context, ephemeral UI in `useState`; no global store | Filled (Phase 0+1) |
| [Type Safety](./type-safety.md) | Strict TS + `noUncheckedIndexedAccess`, `verbatimModuleSyntax`, `ApiError` discriminator, `types/api.ts` as schema mirror | Filled (Phase 0+1) |
| [Quality Guidelines](./quality-guidelines.md) | ESLint (`recommendedTypeChecked` + `stylisticTypeChecked`), Prettier 100-col, AGPL SPDX, Vitest setup invariants | Filled (Phase 0+1) |

---

## Stack Pinning (single source of truth: `frontend/package.json`)

| Layer | Choice |
|-------|--------|
| Runtime | React 19 + ReactDOM 19 |
| Build | Vite 6, `@vitejs/plugin-react` |
| Routing | `@tanstack/react-router` ≥ 1.114 |
| Server state | `@tanstack/react-query` ≥ 5.66 |
| UI primitives | `@radix-ui/*` (dialog, scroll-area, separator, slot, tabs, tooltip) |
| Styling | Tailwind 4 (`@tailwindcss/vite`), `tw-animate-css`, `class-variance-authority`, `tailwind-merge`, `clsx` |
| Icons | `lucide-react` (only) |
| PDF rendering | `pdfjs-dist` (pinned exact, e.g. `5.4.149`) — loaded only by `components/reader/*` and `lib/pdfjs.ts` (worker URL bootstrap via Vite `?url` suffix) |
| Toasts | `sonner` (wrapped in `components/ui/toaster.tsx`) |
| Tests | `vitest`, `jsdom`, `@testing-library/{react,user-event,jest-dom,dom}` |
| Lint / format | `typescript-eslint` (typed rules), `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `prettier` + `eslint-config-prettier` |
| Type check | `tsc -b --noEmit` |
| Node engine | ≥ 20 |

Don't add a new UI primitive, state library, or icon set without updating both `package.json` and this table.

---

## Quick Map

- Entrypoint: `frontend/src/main.tsx` → `<StrictMode>` → `<App />` (`frontend/src/app.tsx`).
- Providers wrap order (outer → inner): `ThemeProvider` → `QueryClientProvider` → `TooltipProvider` → `RouterProvider`, with a `<Toaster>` sibling. See `frontend/src/app.tsx`.
- Route tree: `frontend/src/router.tsx` — flat `addChildren` list under one `createRootRoute({ component: AppShell })`.
- API base: `getApiBaseUrl()` in `frontend/src/lib/api.ts` reads `import.meta.env.VITE_API_BASE` or falls back to `platform.ts` which detects Electron vs browser mode. In browser: `/api` (Vite proxy). In Electron: `http://127.0.0.1:{port}/api` (direct to sidecar). WebSocket base: `getWsBaseUrl()` follows the same pattern.
- Electron bridge: `frontend/src/types/electron.d.ts` mirrors `electron/src/preload.ts`. In browser mode, `window.electronAPI` is `undefined` — all calls gracefully degrade.
- Platform detection: `frontend/src/lib/platform.ts` provides `isElectron()`, `getApiBaseUrl()`, `getWsBaseUrl()`, `getSidecarPort()`, `onDeepLink()`, `onOpenWorkspace()`, `onMenuNavigate()`. Use these instead of accessing `window.electronAPI` directly.
- Notifications: `frontend/src/lib/notifications.ts` provides `notifyOnCompletion()` — uses Electron IPC in desktop mode, Web Notification API in browser mode.
- PDF reader: `frontend/src/components/reader/pdf-viewer.tsx` uses `pdfjs-dist 5.4.149` with `@tanstack/react-virtual` for viewport-only page rendering. `pdf-toolbar.tsx` provides zoom (50–300%, Ctrl+=/−/0) and page navigation (editable page input, PageUp/Down/Home/End). `use-page-renderer.ts` hook abstracts page render lifecycle (canvas + TextLayer). Single/dual mode for BabelDOC alternating-page layout.
