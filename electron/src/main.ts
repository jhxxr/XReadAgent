// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Electron main process — window management, sidecar lifecycle, system tray,
 * application menu, native integrations, and deep link / file association handling.
 *
 * Architecture:
 * - Creates the main window immediately on app start (loading screen)
 * - Spawns the Python sidecar in parallel — window creation never blocks on it
 * - Loads the React UI into the main window once the sidecar is healthy
 * - Shows an in-window error state (with retry) if the sidecar fails to start
 * - Hides to system tray on window close (doesn't kill the sidecar)
 * - Cleans up the sidecar on app quit
 * - Handles `xread://` deep links and `.xread` file associations
 * - Routes menu actions to the renderer via IPC
 */
import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, Notification, Tray } from "electron";
import * as path from "node:path";

import { parseDeepLink, parseXreadFile } from "./deeplink";
import { installExternalLinkHandlers } from "./external-links";
import { buildApplicationMenu } from "./menu";
import { SidecarManager, resolveSidecarPaths } from "./sidecar";
import { SPLASH_HTML } from "./splash";
import { isRendererUrl, resolveRendererUrl } from "./startup";
import {
  createWorkspace,
  deleteWorkspace,
  listWorkspaces,
  renameWorkspace,
  revealWorkspace,
  touchWorkspace,
} from "./workspaces";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Vite dev server URL (used in development mode). */
const VITE_DEV_URL = "http://localhost:5173";

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;

/** Sidecar manager instance — initialized with placeholder pythonPath, updated on app ready. */
const sidecarManager = new SidecarManager(
  { pythonPath: "placeholder" },
  (status, detail, restartInfo) => {
    broadcastSidecarStatus(status, detail, restartInfo);
  },
);

let sidecarPort = 0;
let isQuitting = false;

/**
 * Most recent fatal sidecar startup error, or null. Kept so a freshly
 * (re-)created window that is still on the loading screen can show the error
 * state instead of spinning forever.
 */
let lastSidecarError: string | null = null;

/** Pending deep link URL or file path received before the main window is ready. */
let pendingDeepLink: string | null = null;
let pendingFileOpen: string | null = null;

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(() => {
  const paths = resolveSidecarPaths(app);
  sidecarManager.setPythonPath(paths.pythonPath);
  if (paths.venvPath || paths.backendPath || paths.frontendPath) {
    sidecarManager.setOptions({
      venvPath: paths.venvPath || undefined,
      backendPath: paths.backendPath || undefined,
      frontendPath: paths.frontendPath || undefined,
    });
  }

  createTray();
  setApplicationMenu();

  // Create + show the window immediately (loading screen) and start the
  // sidecar in parallel — window creation never blocks on Python startup.
  createMainWindow();
  void startSidecarAndLoadApp();
});

// Prevent the default "quit when all windows are closed" behavior.
// On Windows we want to hide to tray; on macOS the app stays in dock.
app.on("window-all-closed", () => {
  // Do nothing — the app keeps running in the tray.
});

app.on("before-quit", async () => {
  isQuitting = true;
  await sidecarManager.shutdown();
});

app.on("activate", () => {
  // macOS: re-create window when dock icon is clicked and no windows are open.
  // Safe even while the sidecar is still starting — the window shows the
  // loading screen until `startSidecarAndLoadApp` swaps in the renderer.
  if (BrowserWindow.getAllWindows().length === 0) {
    createMainWindow();
  }
});

// ---------------------------------------------------------------------------
// Deep links (xread:// protocol)
// ---------------------------------------------------------------------------

// macOS: handles `xread://` URLs from the system.
app.on("open-url", (event, url) => {
  event.preventDefault();
  handleDeepLink(url);
});

// ---------------------------------------------------------------------------
// File associations (.xread files)
// ---------------------------------------------------------------------------

// macOS: handles double-clicked files from Finder.
app.on("open-file", (event, filePath) => {
  event.preventDefault();
  handleFileOpen(filePath);
});

// Windows: process.argv may contain a file path or deep link URL when the
// app is launched via file association or protocol handler.
// We also check for second-instance deep link arguments.
app.on("second-instance", (_event, argv) => {
  // Find the first argument that looks like a deep link or .xread file.
  for (const arg of argv.slice(1)) {
    if (arg.startsWith("xread://")) {
      handleDeepLink(arg);
      return;
    }
    if (arg.endsWith(".xread")) {
      handleFileOpen(arg);
      return;
    }
  }
  // If no deep link found, just focus the window.
  showMainWindow();
});

// On Windows, check argv for file paths / deep links at startup.
// (Only relevant for the primary instance — second-instance is handled above.)
if (process.platform === "win32" && process.argv.length > 1) {
  for (const arg of process.argv.slice(1)) {
    if (arg.startsWith("xread://")) {
      pendingDeepLink = arg;
      break;
    }
    if (arg.endsWith(".xread")) {
      pendingFileOpen = arg;
      break;
    }
  }
}

// ---------------------------------------------------------------------------
// Deep link / file open handlers
// ---------------------------------------------------------------------------

/**
 * The main window when it currently hosts the React renderer (not the inline
 * loading screen, and not a window with nothing loaded yet), else null. Deep
 * links sent to the loading screen would be dropped — queue them as pending
 * instead.
 */
function getActiveRendererWindow(): BrowserWindow | null {
  if (
    mainWindow &&
    !mainWindow.isDestroyed() &&
    isRendererUrl(mainWindow.webContents.getURL())
  ) {
    return mainWindow;
  }
  return null;
}

function handleDeepLink(url: string): void {
  const action = parseDeepLink(url);
  if (!action) return;

  const win = getActiveRendererWindow();
  if (win) {
    win.show();
    win.focus();
    win.webContents.send("deep-link", action);
  } else {
    // Store for later; dispatched on the renderer's did-finish-load. Surface
    // an existing loading window so the user sees startup progress (a window
    // must not be created here — open-url can fire before app ready).
    pendingDeepLink = url;
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
    }
  }
}

function handleFileOpen(filePath: string): void {
  const action = parseXreadFile(filePath);

  const win = getActiveRendererWindow();
  if (win) {
    win.show();
    win.focus();
    win.webContents.send("deep-link", action);
  } else {
    // Store for later; dispatched on the renderer's did-finish-load. Surface
    // an existing loading window so the user sees startup progress (a window
    // must not be created here — open-file can fire before app ready).
    pendingFileOpen = filePath;
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
    }
  }
}

/**
 * Dispatch any pending deep link or file open that was received before
 * the main window finished loading.
 */
function dispatchPendingLinks(): void {
  if (pendingDeepLink) {
    const action = parseDeepLink(pendingDeepLink);
    if (action && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("deep-link", action);
    }
    pendingDeepLink = null;
  }
  if (pendingFileOpen) {
    const action = parseXreadFile(pendingFileOpen);
    if (action && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("deep-link", action);
    }
    pendingFileOpen = null;
  }
}

// ---------------------------------------------------------------------------
// Sidecar startup (parallel to window creation)
// ---------------------------------------------------------------------------

/**
 * Start the sidecar and, once it is healthy, swap the renderer into the main
 * window (which has been showing the loading screen since app start).
 *
 * On failure the loading screen flips to its error state — visible message,
 * raw detail, and a Retry button (wired to the `splash-retry` IPC below) —
 * instead of a white screen or a silent exit.
 */
async function startSidecarAndLoadApp(): Promise<void> {
  try {
    lastSidecarError = null;
    updateLoadingStatus("Starting sidecar...");
    const handle = await sidecarManager.start();
    sidecarPort = handle.port;

    updateLoadingStatus("Sidecar ready, loading app...");
    if (mainWindow && !mainWindow.isDestroyed()) {
      loadRenderer(mainWindow);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error starting sidecar";
    lastSidecarError = message;
    updateLoadingStatus(`Error: ${message}`);
    // Tell the loading screen to show the error state.
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("splash-error", message);
    }
  }
}

// Retry from the loading screen's error state: re-spawn the Python process
// rather than reloading the entire app.
ipcMain.on("splash-retry", () => {
  void (async () => {
    await sidecarManager.shutdown();
    sidecarPort = 0;
    await startSidecarAndLoadApp();
  })();
});

function updateLoadingStatus(message: string): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("splash-status", message);
  }
}

// ---------------------------------------------------------------------------
// Main window
// ---------------------------------------------------------------------------

function createMainWindow(): BrowserWindow {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    show: false,
    title: "XReadAgent",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Hide to tray instead of closing (unless the app is quitting).
  mainWindow.on("close", (e: Electron.Event) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow?.hide();
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  // External http(s) links open in the system browser; navigation away from
  // the local renderer origins is blocked. The origin list is a getter so a
  // sidecar restart (new port) is picked up without re-installing handlers.
  installExternalLinkHandlers(mainWindow.webContents, () => [
    new URL(VITE_DEV_URL).origin,
    `http://127.0.0.1:${sidecarPort}`,
  ]);

  setApplicationMenu();

  // Load the renderer when the sidecar is already running (window re-created
  // from tray / macOS dock); otherwise show the loading screen — the renderer
  // is swapped in by `startSidecarAndLoadApp` once the sidecar reports ready.
  if (resolveRendererUrl(app.isPackaged, sidecarPort, VITE_DEV_URL) !== null) {
    loadRenderer(mainWindow);
  } else {
    loadLoadingScreen(mainWindow);
  }

  // Show the window once the content is ready.
  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  return mainWindow;
}

/**
 * Load the inline loading/error screen (shared with the former splash window)
 * into `win`. If the sidecar already failed, flip straight to the error state
 * once the page is ready instead of spinning forever.
 */
function loadLoadingScreen(win: BrowserWindow): void {
  win.webContents.once("did-finish-load", () => {
    if (lastSidecarError && !win.isDestroyed()) {
      win.webContents.send("splash-error", lastSidecarError);
    }
  });
  void win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(SPLASH_HTML)}`);
}

function loadRenderer(win: BrowserWindow): void {
  const url = resolveRendererUrl(app.isPackaged, sidecarPort, VITE_DEV_URL);
  if (url === null) {
    // Defensive: callers only invoke this once the sidecar port is known.
    loadLoadingScreen(win);
    return;
  }

  // Dispatch any pending deep links once the renderer is up (they target the
  // React router, so sending them to the loading screen would drop them).
  win.webContents.once("did-finish-load", () => {
    dispatchPendingLinks();
  });

  void win.loadURL(url);
  if (!app.isPackaged) {
    // Open DevTools in dev mode.
    win.webContents.openDevTools({ mode: "detach" });
  }

  // Inject the sidecar port into the renderer so the frontend API client
  // can route requests to the correct port. The preload bridge exposes a
  // synchronous `getSidecarPort()` via contextBridge as the preferred API.
  // This `executeJavaScript` fallback sets `window.__XREAD_SIDECAR_PORT__`
  // at load time for codepaths that read it before the bridge is available.
  // The value is a trusted local port number (not user input), so the
  // injection risk is minimal.
  win.webContents.on("did-finish-load", () => {
    win.webContents.executeJavaScript(`
      window.__XREAD_SIDECAR_PORT__ = ${sidecarPort};
    `);
  });
}

// ---------------------------------------------------------------------------
// Application menu
// ---------------------------------------------------------------------------

function setApplicationMenu(): void {
  const menu = buildApplicationMenu(mainWindow);
  Menu.setApplicationMenu(menu);
}

// ---------------------------------------------------------------------------
// System tray
// ---------------------------------------------------------------------------

function createTray(): void {
  // On macOS, use a template icon (monochrome, adapts to light/dark mode).
  // On Windows/Linux, use the programmatically generated colored icon.
  let icon: Electron.NativeImage;
  if (process.platform === "darwin") {
    // macOS: generate a monochrome template icon programmatically.
    // Template icons must be black + alpha only; macOS auto-inverts
    // them to match light/dark menu bar appearance.
    icon = createTrayTemplateIcon();
    icon.setTemplateImage(true);
  } else {
    icon = createTrayIcon();
  }
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    { label: "Show XReadAgent", click: () => showMainWindow() },
    { type: "separator" },
    { label: "Preferences", click: () => handleTrayPreferences() },
    { type: "separator" },
    { label: "Restart Sidecar", click: () => restartSidecar() },
    { type: "separator" },
    { label: "Quit", click: () => { isQuitting = true; app.quit(); } },
  ]);

  tray.setContextMenu(contextMenu);
  tray.setToolTip("XReadAgent");
  tray.on("double-click", () => showMainWindow());
}

/**
 * Create a simple 16x16 tray icon as a DataURL placeholder.
 * The icon is a simple blue square with rounded corners — enough to be
 * visible in the system tray until a proper icon is designed.
 */
function createTrayIcon(): Electron.NativeImage {
  // 16x16 minimal PNG: blue square with rounded appearance.
  // This is a temporary placeholder; replace with a proper icon asset.
  const size = 16;
  const canvas = Buffer.alloc(size * size * 4);

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const idx = (y * size + x) * 4;
      // Create a simple "X" pattern in blue (#3b82f6).
      const isCenter = (x >= 3 && x <= 12 && y >= 3 && y <= 12);
      const isEdge = x === 0 || x === 15 || y === 0 || y === 15;

      if (isCenter && !isEdge) {
        // Blue fill with slight alpha fade at edges.
        const alpha = (x >= 2 && x <= 13 && y >= 2 && y <= 13) ? 255 : 200;
        canvas[idx] = 59;     // R
        canvas[idx + 1] = 130; // G
        canvas[idx + 2] = 246; // B
        canvas[idx + 3] = alpha; // A
      } else {
        canvas[idx] = 0;
        canvas[idx + 1] = 0;
        canvas[idx + 2] = 0;
        canvas[idx + 3] = 0;
      }
    }
  }

  return nativeImage.createFromBuffer(canvas, {
    width: size,
    height: size,
    scaleFactor: 1.0,
  });
}

/**
 * Create a 22x22 monochrome template icon for the macOS system tray.
 *
 * macOS template icons should be black + alpha only (no color). The OS
 * automatically adapts them for light/dark mode appearance. The icon is
 * a simplified book/reader shape matching the app icon.
 */
function createTrayTemplateIcon(): Electron.NativeImage {
  const size = 22;
  const rgba = Buffer.alloc(size * size * 4);

  // Draw a simplified book shape: two pages with a spine gap.
  const margin = 2;
  const bookLeft = margin;
  const bookRight = size - margin;
  const bookTop = margin;
  const bookBottom = size - margin;
  const spineX = Math.round(size / 2);

  for (let y = bookTop; y < bookBottom; y++) {
    for (let x = bookLeft; x < bookRight; x++) {
      const idx = (y * size + x) * 4;
      const isLeftPage = x < spineX - 1;
      const isRightPage = x > spineX + 1;
      const isSpine = x >= spineX - 1 && x <= spineX + 1;

      if (isLeftPage || isRightPage || isSpine) {
        // Black fill with full opacity for template icon.
        rgba[idx] = 0;      // R
        rgba[idx + 1] = 0;  // G
        rgba[idx + 2] = 0;  // B
        rgba[idx + 3] = 255; // A
      }
      // Else: remains transparent (0,0,0,0).
    }
  }

  return nativeImage.createFromBuffer(rgba, {
    width: size,
    height: size,
    scaleFactor: 1.0,
  });
}

function showMainWindow(): void {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createMainWindow();
  }
  mainWindow?.show();
  mainWindow?.focus();
}

async function restartSidecar(): Promise<void> {
  await sidecarManager.shutdown();
  sidecarPort = 0;
  try {
    const handle = await sidecarManager.start();
    sidecarPort = handle.port;
    lastSidecarError = null;
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (!isRendererUrl(mainWindow.webContents.getURL())) {
        // The window is still on the loading/error screen (the sidecar never
        // became ready before) — load the real renderer now.
        loadRenderer(mainWindow);
      } else {
        // Re-inject the port in the current renderer.
        mainWindow.webContents.executeJavaScript(`
          window.__XREAD_SIDECAR_PORT__ = ${sidecarPort};
        `);
      }
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error restarting sidecar";
    dialog.showErrorBox("Sidecar Error", message);
  }
}

// ---------------------------------------------------------------------------
// Tray menu action handlers
// ---------------------------------------------------------------------------

function handleTrayPreferences(): void {
  showMainWindow();
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("menu:navigate", "/settings");
  }
}

// ---------------------------------------------------------------------------
// IPC handlers
// ---------------------------------------------------------------------------

ipcMain.on("is-packaged", (e) => {
  e.returnValue = app.isPackaged;
});

ipcMain.on("get-sidecar-port", (e) => {
  e.returnValue = sidecarPort;
});

ipcMain.on("show-notification", (_event, title: string, body: string) => {
  if (Notification.isSupported()) {
    const notification = new Notification({ title, body });
    notification.on("click", () => {
      // Bring the window to the foreground when the notification is clicked.
      showMainWindow();
    });
    notification.show();
  }
});

ipcMain.handle("show-open-file-dialog", async (_event, title?: string) => {
  const result = await dialog.showOpenDialog({
    title: title ?? "Select Document",
    properties: ["openFile"],
    filters: [
      { name: "Documents", extensions: ["pdf", "docx", "html", "htm", "md", "txt"] },
      { name: "All Files", extensions: ["*"] },
    ],
  });
  return result.filePaths;
});

// ---------------------------------------------------------------------------
// Managed workspace registry IPC handlers
// ---------------------------------------------------------------------------

ipcMain.handle("workspace:list", () => listWorkspaces());

ipcMain.handle("workspace:create", (_event, name: string) =>
  createWorkspace(name, new Date().toISOString()),
);

ipcMain.handle("workspace:rename", (_event, id: string, name: string) =>
  renameWorkspace(id, name),
);

ipcMain.handle("workspace:delete", (_event, id: string) => deleteWorkspace(id));

ipcMain.handle("workspace:touch", (_event, id: string) =>
  touchWorkspace(id, new Date().toISOString()),
);

ipcMain.handle("workspace:reveal", (_event, id: string) => revealWorkspace(id));


// ---------------------------------------------------------------------------
// Sidecar management IPC handlers
// ---------------------------------------------------------------------------

ipcMain.handle("sidecar:status", () => {
  return sidecarManager.getStatus();
});

ipcMain.handle("sidecar:logs", () => {
  return sidecarManager.getLogs();
});

ipcMain.handle("sidecar:restart", async () => {
  await restartSidecar();
});

ipcMain.handle("sidecar:restart-info", () => {
  return sidecarManager.getRestartInfo();
});

// ---------------------------------------------------------------------------
// Broadcast helpers
// ---------------------------------------------------------------------------

function broadcastSidecarStatus(status: string, detail?: string, restartInfo?: import("./sidecar").SidecarRestartInfo): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    // The loading screen listens for `splash-status`; the React renderer
    // listens for `sidecar-status`. The window hosts one or the other, and
    // each page ignores the channel it doesn't subscribe to.
    mainWindow.webContents.send("splash-status", `${status}${detail ? `: ${detail}` : ""}`);
    mainWindow.webContents.send("sidecar-status", status, detail);
    if (restartInfo) {
      mainWindow.webContents.send("sidecar:restarting", restartInfo);
    }
  }
}
