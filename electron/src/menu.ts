// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Application menu builder for XReadAgent.
 *
 * Constructs the menu bar (File / Edit / View / Help) and wires menu items
 * to IPC events that the renderer can listen for.
 */
import { app, dialog, Menu } from "electron";
import type { BrowserWindow, MenuItemConstructorOptions } from "electron";

// ---------------------------------------------------------------------------
// Menu construction
// ---------------------------------------------------------------------------

/**
 * Build the application menu.
 *
 * @param mainWindow - The main BrowserWindow, used to send IPC events.
 *   May be `null` if the window hasn't been created yet; menu items that
 *   require the renderer will silently no-op in that case.
 */
export function buildApplicationMenu(
  mainWindow: BrowserWindow | null,
): ReturnType<typeof Menu.buildFromTemplate> {
  const template: MenuItemConstructorOptions[] = [
    {
      label: "File",
      submenu: [
        {
          label: "Open Workspace",
          accelerator: "CmdOrCtrl+O",
          click: () => handleOpenWorkspace(mainWindow),
        },
        { type: "separator" },
        {
          label: "Preferences",
          accelerator: "CmdOrCtrl+,",
          click: () => handlePreferences(mainWindow),
        },
        { type: "separator" },
        {
          label: "Quit",
          accelerator: "CmdOrCtrl+Q",
          click: () => {
            app.quit();
          },
        },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "selectAll" },
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    {
      label: "Help",
      submenu: [
        {
          label: "About XReadAgent",
          click: () => handleAbout(mainWindow),
        },
        {
          label: "Check for Updates...",
          enabled: false, // v1: disabled, will be enabled in v1.1/v2
          click: () => {
            // Placeholder for future auto-update check.
          },
        },
      ],
    },
  ];

  return Menu.buildFromTemplate(template);
}

// ---------------------------------------------------------------------------
// Menu action handlers
// ---------------------------------------------------------------------------

/**
 * Open Workspace: shows a native folder dialog and sends the selected path
 * to the renderer via IPC.
 */
function handleOpenWorkspace(mainWindow: BrowserWindow | null): void {
  if (!mainWindow || mainWindow.isDestroyed()) return;

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

/**
 * Preferences: navigates the renderer to the Settings page.
 */
function handlePreferences(mainWindow: BrowserWindow | null): void {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("menu:navigate", "/settings");
}

/**
 * About: shows a simple about dialog.
 */
function handleAbout(mainWindow: BrowserWindow | null): void {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("menu:navigate", "/settings");
}
