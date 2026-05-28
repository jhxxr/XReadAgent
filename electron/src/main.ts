// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Electron main process — window management, sidecar lifecycle, system tray,
 * and native integrations.
 *
 * Architecture:
 * - Spawns the Python sidecar on app start
 * - Shows a splash window while the sidecar starts
 * - Loads the React UI once the sidecar is healthy
 * - Hides to system tray on window close (doesn't kill the sidecar)
 * - Cleans up the sidecar on app quit
 */
import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, Notification, Tray } from "electron";
import * as path from "node:path";

import { SidecarManager, resolvePythonPath } from "./sidecar";
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
  (status, detail) => {
    broadcastSidecarStatus(status, detail);
  },
);

let sidecarPort = 0;
let isQuitting = false;

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  const pythonPath = resolvePythonPath(app);
  sidecarManager.setPythonPath(pythonPath);

  createTray();
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
  ipcMain.on("splash-retry", () => {
    showSplashAndStartSidecar();
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

  // Load the appropriate URL.
  loadRenderer(mainWindow);

  // Show the window once the content is ready.
  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
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
// System tray
// ---------------------------------------------------------------------------

function createTray(): void {
  // Use a simple 1x1 pixel transparent PNG as a placeholder tray icon.
  // A real icon should be added to resources/ later.
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    { label: "Show XReadAgent", click: () => showMainWindow() },
    { type: "separator" },
    { label: "Restart Sidecar", click: () => restartSidecar() },
    { type: "separator" },
    { label: "Quit", click: () => { isQuitting = true; app.quit(); } },
  ]);

  tray.setContextMenu(contextMenu);
  tray.setToolTip("XReadAgent");
  tray.on("double-click", () => showMainWindow());
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
    new Notification({ title, body }).show();
  }
});

ipcMain.handle("show-open-folder-dialog", async (_event, title?: string) => {
  const result = await dialog.showOpenDialog({
    title: title ?? "Select Folder",
    properties: ["openDirectory"],
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

// ---------------------------------------------------------------------------
// Broadcast helpers
// ---------------------------------------------------------------------------

function broadcastSidecarStatus(status: string, detail?: string): void {
  // Send to splash window.
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send("splash-status", `${status}${detail ? `: ${detail}` : ""}`);
  }
  // Send to main window.
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("sidecar-status", status, detail);
  }
}