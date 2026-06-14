// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Unit tests for the menu module.
 *
 * Verifies that `buildApplicationMenu` constructs the expected menu structure
 * without requiring a running Electron instance.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock Electron's Menu.buildFromTemplate to capture the template.
let capturedTemplate: Electron.MenuItemConstructorOptions[] | undefined;

vi.mock("electron", () => ({
  Menu: {
    buildFromTemplate: (template: Electron.MenuItemConstructorOptions[]) => {
      capturedTemplate = template;
      return { type: "mock_menu" };
    },
    setApplicationMenu: vi.fn(),
  },
  BrowserWindow: class MockBrowserWindow {
    isDestroyed() { return false; }
    focus() {}
    show() {}
    webContents = { send: vi.fn() };
  },
  dialog: {
    showOpenDialog: vi.fn(),
  },
  app: {
    whenReady: vi.fn(),
    on: vi.fn(),
    quit: vi.fn(),
    isPackaged: false,
  },
  nativeImage: {
    createEmpty: () => ({ type: "mock_image" }),
  },
  Notification: class MockNotification {},
  Tray: class MockTray {
    setContextMenu() {}
    setToolTip() {}
    on() {}
  },
  ipcMain: {
    on: vi.fn(),
    handle: vi.fn(),
    removeAllListeners: vi.fn(),
  },
}));

import { buildApplicationMenu } from "../src/menu";

describe("buildApplicationMenu", () => {
  beforeEach(() => {
    capturedTemplate = undefined;
  });

  it("creates a menu with File, Edit, View, and Help menus", () => {
    buildApplicationMenu(null);

    expect(capturedTemplate).toBeDefined();
    const labels = capturedTemplate!.map((item) => item.label);
    expect(labels).toContain("File");
    expect(labels).toContain("Edit");
    expect(labels).toContain("View");
    expect(labels).toContain("Help");
  });

  it("File menu contains Preferences and Quit (no folder-picker entry)", () => {
    buildApplicationMenu(null);

    const fileMenu = capturedTemplate!.find((item) => item.label === "File");
    expect(fileMenu).toBeDefined();

    const submenu = fileMenu!.submenu as Electron.MenuItemConstructorOptions[];
    const itemLabels = submenu.map((item) => item.label);
    // "Open Workspace" was removed — workspaces are managed in-app under the
    // app data directory, never an arbitrary folder picked via native dialog.
    expect(itemLabels).not.toContain("Open Workspace");
    expect(itemLabels).toContain("Preferences");
    expect(itemLabels).toContain("Quit");
  });

  it("File menu Preferences has CmdOrCtrl+, accelerator", () => {
    buildApplicationMenu(null);

    const fileMenu = capturedTemplate!.find((item) => item.label === "File");
    const submenu = fileMenu!.submenu as Electron.MenuItemConstructorOptions[];
    const preferences = submenu.find((item) => item.label === "Preferences");
    expect(preferences).toBeDefined();
    expect(preferences!.accelerator).toBe("CmdOrCtrl+,");
  });

  it("Edit menu has standard items (undo, redo, cut, copy, paste, selectAll)", () => {
    buildApplicationMenu(null);

    const editMenu = capturedTemplate!.find((item) => item.label === "Edit");
    expect(editMenu).toBeDefined();

    const submenu = editMenu!.submenu as Electron.MenuItemConstructorOptions[];
    // Items with roles won't have explicit labels, but roles like "undo",
    // "redo", "cut", "copy", "paste", "selectAll" should be present.
    const roles = submenu.map((item) => item.role);
    expect(roles).toContain("undo");
    expect(roles).toContain("redo");
    expect(roles).toContain("cut");
    expect(roles).toContain("copy");
    expect(roles).toContain("paste");
    expect(roles).toContain("selectAll");
  });

  it("View menu has reload, forceReload, toggleDevTools, togglefullscreen", () => {
    buildApplicationMenu(null);

    const viewMenu = capturedTemplate!.find((item) => item.label === "View");
    expect(viewMenu).toBeDefined();

    const submenu = viewMenu!.submenu as Electron.MenuItemConstructorOptions[];
    const roles = submenu.map((item) => item.role);
    expect(roles).toContain("reload");
    expect(roles).toContain("forceReload");
    expect(roles).toContain("toggleDevTools");
    expect(roles).toContain("togglefullscreen");
  });

  it("Help menu has About and Check for Updates items", () => {
    buildApplicationMenu(null);

    const helpMenu = capturedTemplate!.find((item) => item.label === "Help");
    expect(helpMenu).toBeDefined();

    const submenu = helpMenu!.submenu as Electron.MenuItemConstructorOptions[];
    const itemLabels = submenu.map((item) => item.label);
    expect(itemLabels).toContain("About XReadAgent");
    expect(itemLabels).toContain("Check for Updates...");
  });

  it("Check for Updates is disabled", () => {
    buildApplicationMenu(null);

    const helpMenu = capturedTemplate!.find((item) => item.label === "Help");
    const submenu = helpMenu!.submenu as Electron.MenuItemConstructorOptions[];
    const checkUpdates = submenu.find((item) => item.label === "Check for Updates...");
    expect(checkUpdates).toBeDefined();
    expect(checkUpdates!.enabled).toBe(false);
  });
});
