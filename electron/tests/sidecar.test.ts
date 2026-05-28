// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Unit tests for sidecar module.
 *
 * These tests verify the regex patterns and Python path resolution logic
 * without actually starting Python. Full integration tests for SidecarManager
 * require a running Python sidecar and are not included here.
 */
import { describe, it, expect } from "vitest";

import { SIDECAR_READY_RE, resolvePythonPath } from "../src/sidecar";

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
});