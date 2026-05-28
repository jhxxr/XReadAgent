// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Unit tests for sidecar module.
 *
 * These tests verify the regex patterns, Python path resolution logic, and
 * log-buffer behavior without actually starting Python. Full integration
 * tests for SidecarManager require a running Python sidecar and are not
 * included here.
 */
import { describe, it, expect } from "vitest";
import path from "node:path";

import { SIDECAR_READY_RE, resolvePythonPath, resolveSidecarPaths, SidecarManager } from "../src/sidecar";
import type { SidecarRestartInfo } from "../src/sidecar";

// ---------------------------------------------------------------------------
// SIDECAR_READY_RE
// ---------------------------------------------------------------------------

describe("SIDECAR_READY_RE", () => {
  it("matches the standard SIDECAR_READY line", () => {
    const match = SIDECAR_READY_RE.exec("SIDECAR_READY port=8765");
    expect(match).not.toBeNull();
    expect(match![1]).toBe("8765");
  });

  it("matches with trailing whitespace", () => {
    const match = SIDECAR_READY_RE.exec("SIDECAR_READY port=12345  ");
    expect(match).not.toBeNull();
    expect(match![1]).toBe("12345");
  });

  it("does not match a partial line", () => {
    const match = SIDECAR_READY_RE.exec("Some log line SIDECAR_READY port=8765");
    expect(match).toBeNull();
  });

  it("does not match a line without the port number", () => {
    const match = SIDECAR_READY_RE.exec("SIDECAR_READY port=");
    expect(match).toBeNull();
  });

  it("does not match arbitrary text", () => {
    const match = SIDECAR_READY_RE.exec("Hello world");
    expect(match).toBeNull();
  });

  it("matches port 0 (auto-pick)", () => {
    const match = SIDECAR_READY_RE.exec("SIDECAR_READY port=0");
    expect(match).not.toBeNull();
    expect(match![1]).toBe("0");
  });
});

// ---------------------------------------------------------------------------
// resolvePythonPath
// ---------------------------------------------------------------------------

describe("resolvePythonPath", () => {
  it("returns venv python path in development mode", () => {
    const mockApp = {
      isPackaged: false,
      getAppPath: () => "/project/electron",
    };

    const result = resolvePythonPath(mockApp);

    // Should contain .venv path
    if (process.platform === "win32") {
      expect(result).toContain(".venv");
      expect(result).toContain("Scripts");
      expect(result).toContain("python.exe");
    } else {
      expect(result).toContain(".venv");
      expect(result).toContain("bin");
      expect(result).toContain("python");
    }
  });

  it("returns bundled python path in production mode", () => {
    const mockApp = {
      isPackaged: true,
      getAppPath: () => "/app/electron",
    };

    const result = resolvePythonPath(mockApp, "/app/resources");

    expect(result).toContain("resources");
    expect(result).toContain("python");
  });

  it("returns a path containing 'python' in production mode", () => {
    const mockApp = {
      isPackaged: true,
      getAppPath: () => "/app/electron",
    };

    const result = resolvePythonPath(mockApp, "/app/resources");
    expect(result).toMatch(/python/);
  });

  it("includes .exe suffix on Windows in production mode", () => {
    const mockApp = {
      isPackaged: true,
      getAppPath: () => "/app/electron",
    };

    const result = resolvePythonPath(mockApp, "/app/resources");
    if (process.platform === "win32") {
      expect(result).toContain("python.exe");
    } else {
      expect(result).toContain("python");
      expect(result).not.toContain(".exe");
    }
  });

  it("returns the correct bundled path for each platform", () => {
    const mockApp = {
      isPackaged: true,
      getAppPath: () => "/app/electron",
    };

    const result = resolvePythonPath(mockApp, "/app/resources");
    // python-build-standalone install_only layout after --strip-components=2:
    //   Windows: resources/python/python.exe
    //   Linux/macOS: resources/python/bin/python3
    // Note: path.join uses backslashes on Windows, forward slashes on others.
    const expected = process.platform === "win32"
      ? path.join("/app/resources", "python", "python.exe")
      : path.join("/app/resources", "python", "bin", "python3");
    expect(result).toBe(expected);
  });
});

// ---------------------------------------------------------------------------
// resolveSidecarPaths
// ---------------------------------------------------------------------------

describe("resolveSidecarPaths", () => {
  it("returns empty venvPath and backendPath in development mode", () => {
    const mockApp = {
      isPackaged: false,
      getAppPath: () => "/project/electron",
    };

    const paths = resolveSidecarPaths(mockApp);
    expect(paths.pythonPath).toContain(".venv");
    expect(paths.venvPath).toBe("");
    expect(paths.backendPath).toBe("");
  });

  it("returns all production paths in packaged mode", () => {
    const mockApp = {
      isPackaged: true,
      getAppPath: () => "/app/electron",
    };

    const paths = resolveSidecarPaths(mockApp, "/app/resources");
    expect(paths.pythonPath).toContain("python");
    expect(paths.venvPath).toBe(path.join("/app/resources", "python-venv"));
    expect(paths.backendPath).toBe(path.join("/app/resources", "backend"));
  });

  it("returns consistent paths when resourcesPath is provided explicitly", () => {
    const mockApp = {
      isPackaged: true,
      getAppPath: () => "/app/electron",
    };

    // In production, resourcesPath comes from process.resourcesPath (injected by
    // Electron). In tests we must pass it explicitly since process.resourcesPath
    // is not available outside Electron.
    const paths = resolveSidecarPaths(mockApp, "/custom/resources");
    expect(paths.venvPath).toBe(path.join("/custom/resources", "python-venv"));
    expect(paths.backendPath).toBe(path.join("/custom/resources", "backend"));
  });
});

// ---------------------------------------------------------------------------
// SidecarManager — log buffer
// ---------------------------------------------------------------------------

describe("SidecarManager log buffer", () => {
  it("starts with an empty log buffer", () => {
    const manager = new SidecarManager({ pythonPath: "python" });
    expect(manager.getLogs()).toEqual([]);
  });

  it("getLogs returns a copy of the buffer", () => {
    const manager = new SidecarManager({ pythonPath: "python" });
    const logs = manager.getLogs();
    logs.push("extra");
    // Original buffer is not modified.
    expect(manager.getLogs()).toEqual([]);
  });

  it("getStatus returns idle state when not started", () => {
    const manager = new SidecarManager({ pythonPath: "python" });
    const status = manager.getStatus();
    expect(status).toEqual({
      status: "idle",
      pid: null,
      port: null,
      startedAt: null,
      restartCount: 0,
    });
  });

  it("getRestartInfo returns null when no restart is in progress", () => {
    const manager = new SidecarManager({ pythonPath: "python" });
    expect(manager.getRestartInfo()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// SidecarManager — restart event emission
// ---------------------------------------------------------------------------

describe("SidecarManager restart events", () => {
  it("SidecarRestartInfo shape matches the interface", () => {
    const info: SidecarRestartInfo = {
      attempt: 1,
      maxAttempts: 3,
      delayMs: 1000,
    };

    // Verify all required fields are present and typed correctly.
    expect(typeof info.attempt).toBe("number");
    expect(typeof info.maxAttempts).toBe("number");
    expect(typeof info.delayMs).toBe("number");
  });

  it("getStatus includes restartCount field", () => {
    const manager = new SidecarManager({ pythonPath: "python" });
    const status = manager.getStatus();
    expect(status).toHaveProperty("restartCount");
    expect(typeof status.restartCount).toBe("number");
    expect(status.restartCount).toBe(0);
  });
});
