// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Electron main process — window management, sidecar lifecycle, system tray,
 * application menu, native integrations, and deep link / file association handling.
 *
 * Architecture:
 * - Spawns the Python sidecar on app start
 * - Shows a splash window while the sidecar starts
 * - Loads the React UI once the sidecar is healthy
 * - Hides to system tray on window close (doesn't kill the sidecar)
 * - Cleans up the sidecar on app quit
 * - Handles `xread://` deep links and `.xread` file associations
 * - Routes menu actions to the renderer via IPC
 */
import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, Notification, Tray } from "electron";
import * as path from "node:path";

import { parseDeepLink, parseXreadFile } from "./deeplink";
import { buildApplicationMenu } from "./menu";
import { SidecarManager, resolveSidecarPaths } from "./sidecar";
import { SPLASH_HTML, SPLASH_HEIGHT, SPLASH_WIDTH } from "./splash";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Vite dev server URL (used in development mode). */
const VITE_DEV_URL = "http://localhost:5173";

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------

let mainWindow: BrowserWindow | null = null;
let splashWindow: BrowserWindow | null = null;
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

/** Pending deep link URL or file path received before the main window is ready. */
let pendingDeepLink: string | null = null;
let pendingFileOpen: string | null = null;

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
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
  await showSplashAndStartSidecar();
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
  if (BrowserWindow.getAllWindows().length === 0 && sidecarPort > 0) {
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

function handleDeepLink(url: string): void {
  const action = parseDeepLink(url);
  if (!action) return;

  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
    mainWindow.focus();
    mainWindow.webContents.send("deep-link", action);
  } else {
    // Store for later; will be dispatched when the main window is ready.
    pendingDeepLink = url;
  }
}

function handleFileOpen(filePath: string): void {
  const action = parseXreadFile(filePath);

  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
    mainWindow.focus();
    mainWindow.webContents.send("deep-link", action);
  } else {
    // Store for later; will be dispatched when the main window is ready.
    pendingFileOpen = filePath;
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
// Splash window
// ---------------------------------------------------------------------------

async function showSplashAndStartSidecar(): Promise<void> {
  // Clean up any existing splash window.
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.close();
    splashWindow = null;
  }

  splashWindow = new BrowserWindow({
    width: SPLASH_WIDTH,
    height: SPLASH_HEIGHT,
    frame: false,
    resizable: false,
    center: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Load inline HTML for the splash.
  splashWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(SPLASH_HTML)}`);
  splashWindow.show();

  // Handle retry from splash error screen.
  // Remove any existing listener first to avoid stacking.
  ipcMain.removeAllListeners("splash-retry");
  ipcMain.on("splash-retry", async () => {
    // Attempt to restart the sidecar from the error screen.
    // This re-spawns the Python process rather than reloading the entire app.
    try {
      await sidecarManager.shutdown();
      sidecarPort = 0;
      const handle = await sidecarManager.start();
      sidecarPort = handle.port;

      // Close splash and open main window on success.
      if (splashWindow && !splashWindow.isDestroyed()) {
        splashWindow.close();
      }
      splashWindow = null;
      createMainWindow();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error starting sidecar";
      splashWindow?.webContents.send("splash-error", message);
    }
  });

  try {
    updateSplashStatus("Starting sidecar...");
    const handle = await sidecarManager.start();
    sidecarPort = handle.port;

    updateSplashStatus("Sidecar ready, loading app...");

    // Close splash and open main window.
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
    }
    splashWindow = null;

    createMainWindow();
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Unknown error starting sidecar";
    updateSplashStatus(`Error: ${message}`);

    // Tell the splash to show the error state.
    splashWindow?.webContents.send("splash-error", message);
  }
}

function updateSplashStatus(message: string): void {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send("splash-status", message);
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

  setApplicationMenu();

  // Load the appropriate URL.
  loadRenderer(mainWindow);

  // Show the window once the content is ready.
  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
    // Dispatch any pending deep links that arrived before the window was ready.
    dispatchPendingLinks();
  });

  return mainWindow;
}

function loadRenderer(win: BrowserWindow): void {
  if (app.isPackaged) {
    // Production: the sidecar serves the static files.
    win.loadURL(`http://127.0.0.1:${sidecarPort}/`);
  } else {
    // Development: use Vite HMR.
    win.loadURL(VITE_DEV_URL);
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
    { label: "Open Workspace", click: () => handleTrayOpenWorkspace() },
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
    // Re-inject the port in the current renderer.
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.executeJavaScript(`
        window.__XREAD_SIDECAR_PORT__ = ${sidecarPort};
      `);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error restarting sidecar";
    dialog.showErrorBox("Sidecar Error", message);
  }
}

// ---------------------------------------------------------------------------
// Tray menu action handlers
// ---------------------------------------------------------------------------

function handleTrayOpenWorkspace(): void {
  showMainWindow();
  if (mainWindow && !mainWindow.isDestroyed()) {
    dialog
      .showOpenDialog(mainWindow, {
        title: "Open Workspace",
        properties: ["openDirectory"],
      })
      .then((result) => {
        if (result.canceled || result.filePaths.length === 0) return;
        const workspacePath = result.filePaths[0]!;
        mainWindow?.webContents.send("open-workspace", workspacePath);
      })
      .catch(() => {
        // User cancelled or dialog error — silently ignore.
      });
  }
}

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

ipcMain.handle("show-open-folder-dialog", async (_event, title?: string) => {
  const result = await dialog.showOpenDialog({
    title: title ?? "Select Folder",
    properties: ["openDirectory"],
  });
  return result.filePaths;
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
  // Send to splash window.
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send("splash-status", `${status}${detail ? `: ${detail}` : ""}`);
  }
  // Send to main window.
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("sidecar-status", status, detail);
    if (restartInfo) {
      mainWindow.webContents.send("sidecar:restarting", restartInfo);
    }
  }
}
