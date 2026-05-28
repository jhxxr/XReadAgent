// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Unit tests for the notifications utility module.
 *
 * Tests the dual Electron / Web Notification path without hitting the real
 * Notification API or Electron IPC.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock platform detection so we can toggle Electron mode.
vi.mock("@/lib/platform", () => ({
  isElectron: vi.fn(),
  getElectronAPI: vi.fn(),
}));

import { isElectron, getElectronAPI } from "@/lib/platform";
import { notifyOnCompletion } from "@/lib/notifications";

const mockIsElectron = vi.mocked(isElectron);
const mockGetElectronAPI = vi.mocked(getElectronAPI);

/**
 * Remove the Notification mock from globalThis.
 *
 * We use Reflect.deleteProperty because `delete globalThis.Notification`
 * is a TypeScript error in strict mode (the `delete` operator requires an
 * optional property, and `Notification` is not declared on `globalThis`
 * in the jsdom type definitions).
 */
function removeNotificationMock(): void {
  Reflect.deleteProperty(globalThis, "Notification");
}

describe("notifyOnCompletion", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses Electron IPC when running in Electron", () => {
    mockIsElectron.mockReturnValue(true);
    const mockShowNotification = vi.fn();
    mockGetElectronAPI.mockReturnValue({
      showNotification: mockShowNotification,
    } as unknown as Window["electronAPI"]);

    notifyOnCompletion("Test Title", "Test Body");

    expect(mockShowNotification).toHaveBeenCalledWith("Test Title", "Test Body");
  });

  it("falls back to Web Notification API when not in Electron", () => {
    mockIsElectron.mockReturnValue(false);
    mockGetElectronAPI.mockReturnValue(undefined);

    // Mock the Web Notification API.
    const mockConstructor = vi.fn().mockImplementation(() => ({}));
    const originalDescriptor = Object.getOwnPropertyDescriptor(globalThis, "Notification");

    // Define a mock Notification constructor.
    Object.defineProperty(globalThis, "Notification", {
      value: mockConstructor,
      writable: true,
      configurable: true,
    });
    Object.defineProperty(globalThis.Notification, "permission", {
      value: "granted",
      configurable: true,
    });
    Object.defineProperty(globalThis.Notification, "requestPermission", {
      value: vi.fn(),
      configurable: true,
    });

    notifyOnCompletion("Web Title", "Web Body");

    expect(mockConstructor).toHaveBeenCalledWith("Web Title", { body: "Web Body" });

    // Restore.
    if (originalDescriptor) {
      Object.defineProperty(globalThis, "Notification", originalDescriptor);
    } else {
      removeNotificationMock();
    }
  });

  it("does not call Electron IPC when not in Electron mode", () => {
    mockIsElectron.mockReturnValue(false);

    const mockConstructor = vi.fn().mockImplementation(() => ({}));
    Object.defineProperty(globalThis, "Notification", {
      value: mockConstructor,
      writable: true,
      configurable: true,
    });
    Object.defineProperty(globalThis.Notification, "permission", {
      value: "granted",
      configurable: true,
    });
    Object.defineProperty(globalThis.Notification, "requestPermission", {
      value: vi.fn(),
      configurable: true,
    });

    notifyOnCompletion("Title", "Body");

    // getElectronAPI should not have been called since isElectron returned false.
    expect(mockGetElectronAPI).not.toHaveBeenCalled();

    removeNotificationMock();
  });

  it("silently drops notification when Electron API is unavailable and Web Notification is not supported", () => {
    // Simulate Electron mode where the API bridge isn't available yet, and
    // the Web Notification API doesn't exist (e.g. jsdom).
    mockIsElectron.mockReturnValue(true);
    mockGetElectronAPI.mockReturnValue(undefined);

    // Ensure globalThis.Notification doesn't exist (jsdom doesn't have it).
    const originalDescriptor = Object.getOwnPropertyDescriptor(globalThis, "Notification");
    removeNotificationMock();

    // Should not throw.
    expect(() => notifyOnCompletion("Title", "Body")).not.toThrow();

    // Restore.
    if (originalDescriptor) {
      Object.defineProperty(globalThis, "Notification", originalDescriptor);
    }
  });

  it("does not crash when not in Electron and Web Notification is denied", () => {
    mockIsElectron.mockReturnValue(false);
    mockGetElectronAPI.mockReturnValue(undefined);

    const mockConstructor = vi.fn();
    Object.defineProperty(globalThis, "Notification", {
      value: mockConstructor,
      writable: true,
      configurable: true,
    });
    Object.defineProperty(globalThis.Notification, "permission", {
      value: "denied",
      configurable: true,
    });
    Object.defineProperty(globalThis.Notification, "requestPermission", {
      value: vi.fn(),
      configurable: true,
    });

    notifyOnCompletion("Denied Title", "Denied Body");

    // Should not create a notification.
    expect(mockConstructor).not.toHaveBeenCalled();

    removeNotificationMock();
  });

  it("requests permission when not in Electron and permission is default", () => {
    mockIsElectron.mockReturnValue(false);
    mockGetElectronAPI.mockReturnValue(undefined);

    const mockConstructor = vi.fn().mockImplementation(() => ({}));
    // Return a pending promise that never resolves, so the .then() callback
    // (which would call `new Notification(...)`) doesn't fire after cleanup.
    const neverResolve = (): Promise<string> => new Promise(() => undefined);
    const mockRequestPermission = vi.fn().mockImplementation(neverResolve);
    Object.defineProperty(globalThis, "Notification", {
      value: mockConstructor,
      writable: true,
      configurable: true,
    });
    Object.defineProperty(globalThis.Notification, "permission", {
      value: "default",
      configurable: true,
    });
    Object.defineProperty(globalThis.Notification, "requestPermission", {
      value: mockRequestPermission,
      configurable: true,
    });

    notifyOnCompletion("Default Title", "Default Body");

    // Should have requested permission.
    expect(mockRequestPermission).toHaveBeenCalled();
    // The mock constructor should NOT have been called yet (pending permission).
    expect(mockConstructor).not.toHaveBeenCalled();

    removeNotificationMock();
  });
});
