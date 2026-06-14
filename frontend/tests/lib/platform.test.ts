// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getApiBaseUrl,
  getSidecarBaseUrl,
  getSidecarPort,
  getSidecarRestartInfo,
  getWsBaseUrl,
  isElectron,
  onSidecarRestarting,
} from "@/lib/platform";

// Save original window properties so we can restore them.
const originalWindow = globalThis.window;
const originalElectronAPI = globalThis.window?.electronAPI;

function installMockElectronAPI(overrides: { getSidecarPort: () => number }): void {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-member-access
  (globalThis.window as any).electronAPI = {
    platform: "win32",
    isPackaged: true,
    getSidecarPort: overrides.getSidecarPort,
    onSidecarReady: vi.fn(),
    onSidecarStatus: vi.fn(),
    onSidecarRestarting: vi.fn(),
    onSplashStatus: vi.fn(),
    onSplashError: vi.fn(),
    sendSplashRetry: vi.fn(),
    showOpenFileDialog: vi.fn().mockResolvedValue([]),
    showNotification: vi.fn(),
    getSidecarStatus: vi.fn().mockResolvedValue({}),
    getSidecarLogs: vi.fn().mockResolvedValue([]),
    getSidecarRestartInfo: vi.fn().mockResolvedValue(null),
    restartSidecar: vi.fn().mockResolvedValue(undefined),
  };
}

describe("platform", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    // Restore electronAPI to its original value.
    if (originalWindow) {
      globalThis.window = originalWindow;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-member-access
      (globalThis.window as any).electronAPI = originalElectronAPI;
    }
  });

  describe("isElectron", () => {
    it("returns false when window.electronAPI is undefined", () => {
      expect(isElectron()).toBe(false);
    });

    it("returns true when window.electronAPI is present", () => {
      installMockElectronAPI({ getSidecarPort: () => 8765 });
      expect(isElectron()).toBe(true);
    });
  });

  describe("getSidecarPort", () => {
    it("returns null in browser mode (no electronAPI)", () => {
      expect(getSidecarPort()).toBeNull();
    });

    it("returns null when electronAPI returns port 0 (sidecar not ready)", () => {
      installMockElectronAPI({ getSidecarPort: () => 0 });
      expect(getSidecarPort()).toBeNull();
    });

    it("returns the port when electronAPI provides a valid port", () => {
      installMockElectronAPI({ getSidecarPort: () => 8765 });
      expect(getSidecarPort()).toBe(8765);
    });
  });

  describe("getApiBaseUrl", () => {
    it("returns '/api' in browser mode (Vite proxy)", () => {
      expect(getApiBaseUrl()).toBe("/api");
    });

    it("returns http://127.0.0.1:{port}/api in Electron mode", () => {
      installMockElectronAPI({ getSidecarPort: () => 12345 });
      expect(getApiBaseUrl()).toBe("http://127.0.0.1:12345/api");
    });

    it("falls back to '/api' when Electron port is 0", () => {
      installMockElectronAPI({ getSidecarPort: () => 0 });
      expect(getApiBaseUrl()).toBe("/api");
    });
  });

  describe("getSidecarBaseUrl", () => {
    it("returns '' in browser mode (origin-relative)", () => {
      expect(getSidecarBaseUrl()).toBe("");
    });

    it("returns http://127.0.0.1:{port} in Electron mode", () => {
      installMockElectronAPI({ getSidecarPort: () => 12345 });
      expect(getSidecarBaseUrl()).toBe("http://127.0.0.1:12345");
    });

    it("falls back to '' when Electron port is 0", () => {
      installMockElectronAPI({ getSidecarPort: () => 0 });
      expect(getSidecarBaseUrl()).toBe("");
    });
  });

  describe("getWsBaseUrl", () => {
    it("returns ws:// based on window.location in browser mode", () => {
      const result = getWsBaseUrl();
      expect(result).toMatch(/^wss?:\/\//);
    });

    it("returns ws://127.0.0.1:{port} in Electron mode", () => {
      installMockElectronAPI({ getSidecarPort: () => 12345 });
      expect(getWsBaseUrl()).toBe("ws://127.0.0.1:12345");
    });

    it("falls back to browser-mode URL when Electron port is 0", () => {
      installMockElectronAPI({ getSidecarPort: () => 0 });
      const result = getWsBaseUrl();
      expect(result).toMatch(/^wss?:\/\//);
    });
  });

  describe("onSidecarRestarting", () => {
    it("returns a no-op cleanup function in browser mode", () => {
      // eslint-disable-next-line @typescript-eslint/no-empty-function
      const cleanup = onSidecarRestarting(() => {});
      expect(typeof cleanup).toBe("function");
      // Should not throw.
      cleanup();
    });

    it("registers a callback via electronAPI in Electron mode", () => {
      installMockElectronAPI({ getSidecarPort: () => 12345 });
      const callback = vi.fn();
      const cleanup = onSidecarRestarting(callback);
      expect(typeof cleanup).toBe("function");

      // Verify that onSidecarRestarting was called on the API.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
      const api = (globalThis.window as any).electronAPI;
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      expect(api.onSidecarRestarting).toHaveBeenCalledWith(callback);
    });
  });

  describe("getSidecarRestartInfo", () => {
    it("returns null in browser mode", async () => {
      const result = await getSidecarRestartInfo();
      expect(result).toBeNull();
    });

    it("delegates to electronAPI in Electron mode", async () => {
      installMockElectronAPI({ getSidecarPort: () => 12345 });
      const result = await getSidecarRestartInfo();
      expect(result).toBeNull();

      // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
      const api = (globalThis.window as any).electronAPI;
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      expect(api.getSidecarRestartInfo).toHaveBeenCalled();
    });
  });
});
