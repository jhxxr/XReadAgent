# Electron Development Guidelines

> Best practices for XReadAgent's Electron desktop shell.

---

## Overview

XReadAgent's Electron shell (`electron/`) is the **native desktop wrapper** that:

- Manages the Python sidecar lifecycle (spawn, health-check, crash-restart, graceful shutdown).
- Provides native OS integrations (system tray, app menu, file associations, deep links, notifications).
- Bridges renderer ↔ main process via `contextBridge.exposeInMainWorld` (never `nodeIntegration`).
- Packages the React frontend + Python backend into a Windows NSIS installer via `electron-builder`.

The frontend runs in a `BrowserWindow` renderer and communicates with the Python sidecar over HTTP/WebSocket on `127.0.0.1:<port>`. The Electron main process only handles OS-level concerns — all business logic stays in the renderer (React) or the sidecar (Python).

`AGPL-3.0-or-later`. Every TypeScript source file in `electron/src/` starts with an SPDX header.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Electron main process (Node.js)                    │
│  - Spawns Python sidecar via SidecarManager         │
│  - Owns BrowserWindow, tray, menu, IPC handlers     │
│  - Exposes contextBridge API to renderer             │
│  - NO business logic — delegates to renderer/sidecar │
└──────────┬──────────────────────────┬───────────────┘
           │ child_process.spawn       │ ipcMain/ipcRenderer
           ▼                          ▼
┌──────────────────────┐   ┌──────────────────────────┐
│  Python sidecar      │   │  Renderer (React/Vite)    │
│  FastAPI + uvicorn   │   │  Uses platform.ts for    │
│  /api/*  /ws/*       │◄──│  dual-environment URLs    │
│  SIDECAR_READY port=N│   └──────────────────────────┘
└──────────────────────┘
```

---

## Directory Structure

```
electron/
├── package.json            # Dependencies: electron, electron-builder, esbuild, vitest
├── tsconfig.json           # Project references → app + test
├── tsconfig.app.json       # Strict TS config for main/preload
├── tsconfig.test.json      # TS config for tests
├── vitest.config.ts        # Test config (electron flag, coverage)
├── electron-builder.yml    # Windows NSIS packaging, extraResources, protocols
├── build/                  # App icons (icon.ico, icon.png, icon.svg)
├── scripts/
│   ├── build.mjs           # esbuild bundle: main.ts + preload.ts → dist/
│   ├── dev.mjs             # esbuild watch + electron . (dev mode)
│   ├── pack.mjs            # Full build pipeline (frontend → electron → pack)
│   ├── bundle-python.mjs   # Download python-build-standalone + create venv
│   └── generate-icons.mjs  # Generate placeholder icons from SVG
└── src/
    ├── main.ts             # App lifecycle, window management, tray, menu, IPC
    ├── preload.ts          # contextBridge.exposeInMainWorld("electronAPI", ...)
    ├── preload.d.ts         # Type declarations for window.electronAPI
    ├── sidecar.ts           # SidecarManager class (spawn, health, restart, shutdown)
    ├── splash.ts            # Inline HTML for loading/error splash window
    ├── deeplink.ts          # xread:// URL parser + .xread file handler
    └── menu.ts              # Application menu builder (File/Edit/View/Help)
```

---

## Key Contracts

### Sidecar Lifecycle Contract

```
1. Main process spawns: python -m xreadagent.api --port 0
2. Sidecar prints on stdout: SIDECAR_READY port=<N>
3. Main process polls: GET http://127.0.0.1:<N>/healthz → 200
4. Main process loads renderer URL:
   - Dev: http://localhost:5173 (Vite HMR)
   - Prod: http://127.0.0.1:<N>/ (FastAPI static files)
5. On sidecar crash: auto-restart up to 3 times with exponential backoff
6. On app quit: SIGTERM → 5s timeout → SIGKILL (Unix) / taskkill /F (Windows)
```

### Release Python Bundle Contract

`electron/scripts/bundle-python.mjs` is executed directly by Node in the Release workflow via
`cd electron && pnpm pack:python`.

- The script must be plain JavaScript ESM. Do not use TypeScript-only syntax in `.mjs` files.
- Python package metadata lives at the repository root `pyproject.toml`, not
  `backend/pyproject.toml`.
- Dependency installation must resolve from the repository root so Hatch can use
  `[tool.hatch.build.targets.wheel] packages = ["backend/src/xreadagent"]`.
- Runtime source is still copied from `backend/src/xreadagent` into
  `electron/resources/backend/xreadagent`; production sidecar startup relies on
  `PYTHONPATH=resources/backend`.
- When installing into the bundled venv with `uv pip install --python`, pass the venv's
  Python executable (`Scripts/python.exe` on Windows, `bin/python` on POSIX), not pip.
- python-build-standalone release assets use target-triple platform suffixes and tarballs:
  Windows x64 is `x86_64-pc-windows-msvc-install_only.tar.gz`, macOS x64 is
  `x86_64-apple-darwin-install_only.tar.gz`, and macOS arm64 is
  `aarch64-apple-darwin-install_only.tar.gz`. The install-only tarballs expose a top-level
  `python/` directory; extract to a temporary directory, locate `python/`, and move its
  contents into `resources/python/`. Do not assume an outer `cpython-.../python/` directory
  or use a fixed `--strip-components=2`.

### IPC Bridge Contract

The preload script exposes `window.electronAPI` with these methods:

| Method | Direction | Return Type | Description |
|--------|-----------|-------------|-------------|
| `platform` | renderer→main | `"win32"` etc. | OS platform |
| `isPackaged` | renderer→main | `boolean` | Whether app is packaged |
| `getSidecarPort()` | renderer→main | `Promise<number>` | Sidecar port number |
| `getSidecarStatus()` | renderer→main | `Promise<SidecarStatus>` | Status/PID/port/uptime |
| `getSidecarLogs()` | renderer→main | `Promise<string[]>` | Last 200 log lines |
| `restartSidecar()` | renderer→main | `Promise<void>` | Restart sidecar |
| `getSidecarRestartInfo()` | renderer→main | `Promise<SidecarRestartInfo>` | Current restart state |
| `showOpenFolderDialog()` | renderer→main | `Promise<string\|null>` | Native folder picker |
| `showNotification(opts)` | renderer→main | `Promise<void>` | System notification |
| `onSidecarReady(cb)` | main→renderer | `void` | Sidecar ready callback |
| `onSidecarStatus(cb)` | main→renderer | `void` | Status change callback |
| `onSidecarRestarting(cb)` | main→renderer | `void` | Restart event callback |
| `onSplashStatus(cb)` | main→renderer | `void` | Splash status callback |
| `onSplashError(cb)` | main→renderer | `void` | Splash error callback |
| `onDeepLink(cb)` | main→renderer | `void` | Deep link callback |
| `onOpenWorkspace(cb)` | main→renderer | `void` | Workspace open callback |
| `onMenuNavigate(cb)` | main→renderer | `void` | Menu navigation callback |

### Deep Link Routes

| URL Pattern | Navigation Target |
|-------------|-------------------|
| `xread://paper/{slug}` | `/paper/{slug}` |
| `xread://query/{id}` | `/queries/{id}` |
| `xread://workspace` | `/workspace` |
| `xread://settings` | `/settings` |

---

## Hard Rules

1. **`contextIsolation: true`, `nodeIntegration: false`** — Always. No exceptions. The preload bridge is the only way renderer code talks to Node.
2. **No business logic in main process** — Main handles OS concerns only (tray, menu, file dialogs, sidecar lifecycle). All app logic stays in renderer (React) or sidecar (Python).
3. **SPDX header on every `.ts` and `.mjs` file** — `// SPDX-License-Identifier: AGPL-3.0-or-later`.
4. **`SidecarManager` is the single source of truth** for sidecar state. Main process reads state from `sidecarManager.getStatus()`, never from ad-hoc variables.
5. **Graceful shutdown order**: SIGTERM → wait 5s → force kill. On Windows: `taskkill /PID` (graceful) → wait → `taskkill /F /PID` (force).
6. **Python path resolution**: dev mode uses `.venv/`, production uses `resources/python/`. Never hardcode paths — always use `resolveSidecarPaths()`.
7. **All renderer↔main communication goes through `ipcMain.handle` / `ipcRenderer.invoke`** (request-response) or `webContents.send` (push events). Never use `ipcMain.on` / `ipcRenderer.send` for request-response patterns.

---

## Common Mistakes

### Don't: Put business logic in the main process

```ts
// ✗ Wrong: Main process validating workspace paths
ipcMain.handle('validate-workspace', (_, path) => {
  return fs.existsSync(path) && fs.statSync(path).isDirectory();
});
```

```ts
// ✓ Correct: Main process only opens native dialogs; renderer validates via sidecar API
ipcMain.handle('show-open-folder-dialog', () => dialog.showOpenDialog({ properties: ['openDirectory'] }));
// Renderer calls /api/workspaces/validate on the sidecar
```

### Don't: Use `nodeIntegration: true` or `require()` in renderer

```ts
// ✗ Wrong: Renderer directly requiring Node modules
const fs = require('fs');
```

```ts
// ✓ Correct: Use the contextBridge API
const result = await window.electronAPI.showOpenFolderDialog();
```

### Don't: Hardcode sidecar port

```ts
// ✗ Wrong: Assuming a fixed port
fetch('http://127.0.0.1:8765/api/settings');
```

```ts
// ✓ Correct: Use platform.ts for dual-environment URLs
import { getApiBaseUrl } from '@/lib/platform';
fetch(`${getApiBaseUrl()}/settings`);
```

---

## Testing Conventions

- Test files live in `electron/tests/`.
- Test file naming mirrors source: `src/sidecar.ts` → `tests/sidecar.test.ts`.
- Use Vitest with `--electron` flag for main-process code that needs Electron APIs.
- For pure logic (URL parsing, path resolution), test without Electron.
- Mock `child_process` for SidecarManager tests — never spawn real Python in unit tests.
- All tests must pass before commit: `cd electron && pnpm test`.
