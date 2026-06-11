// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Unit tests for sidecar module.
 *
 * These tests verify the regex patterns, Python path resolution logic, and
 * log-buffer behavior without actually starting Python. Full integration
 * tests for SidecarManager require a running Python sidecar and are not
 * included here.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { EventEmitter } from "node:events";
import * as fs from "node:fs";
import * as os from "node:os";
import path from "node:path";

import {
  SIDECAR_READY_RE,
  SIDECAR_BOOT_TIMEOUT_MS,
  SIDECAR_READY_TIMEOUT_MS,
  resolvePythonPath,
  resolveSidecarPaths,
  SidecarManager,
  buildSidecarEnv,
  venvSitePackages,
} from "../src/sidecar";
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
    expect(paths.frontendPath).toBe("");
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
    expect(paths.frontendPath).toBe(path.join("/app/resources", "frontend"));
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
// venvSitePackages
// ---------------------------------------------------------------------------

describe("venvSitePackages", () => {
  it("returns Lib/site-packages on Windows", () => {
    const result = venvSitePackages("/app/resources/python-venv", "win32");
    expect(result).toBe(path.join("/app/resources/python-venv", "Lib", "site-packages"));
  });

  it("resolves the versioned lib dir on POSIX", () => {
    const venv = fs.mkdtempSync(path.join(os.tmpdir(), "xread-venv-"));
    try {
      fs.mkdirSync(path.join(venv, "lib", "python3.12", "site-packages"), { recursive: true });
      const result = venvSitePackages(venv, "linux");
      expect(result).toBe(path.join(venv, "lib", "python3.12", "site-packages"));
    } finally {
      fs.rmSync(venv, { recursive: true, force: true });
    }
  });

  it("returns null on POSIX when the lib dir is missing", () => {
    const result = venvSitePackages(path.join(os.tmpdir(), "xread-nonexistent-venv-xyz"), "linux");
    expect(result).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// buildSidecarEnv
// ---------------------------------------------------------------------------

describe("buildSidecarEnv", () => {
  it("puts backend AND venv site-packages on PYTHONPATH in production (Windows)", () => {
    const venvPath = "/app/resources/python-venv";
    const backendPath = "/app/resources/backend";
    const env = buildSidecarEnv(
      { pythonPath: "py.exe", venvPath, backendPath },
      "win32",
      {}, // empty base env → deterministic
    );

    const sitePackages = path.join(venvPath, "Lib", "site-packages");
    // Regression guard: site-packages MUST be on PYTHONPATH (the original
    // ModuleNotFoundError: No module named 'pydantic' bug).
    expect(env.PYTHONPATH).toContain(sitePackages);
    expect(env.PYTHONPATH).toBe([backendPath, sitePackages].join(path.delimiter));
    expect(env.VIRTUAL_ENV).toBe(venvPath);
    expect(env.PYTHONUNBUFFERED).toBe("1");
    expect(env.PATH).toContain(path.join(venvPath, "Scripts"));
  });

  it("does not inject PYTHONPATH or VIRTUAL_ENV in development mode", () => {
    const env = buildSidecarEnv(
      { pythonPath: "/proj/.venv/Scripts/python.exe" }, // no venvPath/backendPath
      "win32",
      {},
    );
    expect(env.PYTHONPATH).toBeUndefined();
    expect(env.VIRTUAL_ENV).toBeUndefined();
    expect(env.PYTHONUNBUFFERED).toBe("1");
  });

  it("preserves an inherited PYTHONPATH after the injected entries", () => {
    const venvPath = "/app/resources/python-venv";
    const backendPath = "/app/resources/backend";
    const env = buildSidecarEnv(
      { pythonPath: "py.exe", venvPath, backendPath },
      "win32",
      { PYTHONPATH: "/pre/existing" },
    );
    const parts = (env.PYTHONPATH ?? "").split(path.delimiter);
    expect(parts[0]).toBe(backendPath);
    expect(parts).toContain(path.join(venvPath, "Lib", "site-packages"));
    expect(parts[parts.length - 1]).toBe("/pre/existing");
  });

  it("lets caller-provided env overrides take precedence", () => {
    const env = buildSidecarEnv(
      { pythonPath: "py.exe", venvPath: "/v", backendPath: "/b", env: { PYTHONPATH: "override" } },
      "win32",
      {},
    );
    expect(env.PYTHONPATH).toBe("override");
  });

  it("sets XREAD_FRONTEND_DIR when frontendPath is provided", () => {
    const env = buildSidecarEnv(
      { pythonPath: "py", frontendPath: "/res/frontend" },
      "win32",
      {},
    );
    expect(env.XREAD_FRONTEND_DIR).toBe("/res/frontend");
  });

  it("leaves XREAD_FRONTEND_DIR unset when frontendPath is absent", () => {
    const env = buildSidecarEnv(
      { pythonPath: "py" },
      "win32",
      {},
    );
    expect(env.XREAD_FRONTEND_DIR).toBeUndefined();
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
// SidecarManager — waitForReady tiered timeouts
// ---------------------------------------------------------------------------

/** Minimal stand-in for a spawned ChildProcess (spec: never spawn real Python). */
interface FakeProc extends EventEmitter {
  stdout: EventEmitter;
  stderr: EventEmitter;
}

function makeFakeProc(): FakeProc {
  const proc = new EventEmitter() as FakeProc;
  proc.stdout = new EventEmitter();
  proc.stderr = new EventEmitter();
  return proc;
}

function callWaitForReady(manager: SidecarManager, proc: FakeProc): Promise<number> {
  return (manager as unknown as { waitForReady(p: FakeProc): Promise<number> }).waitForReady(proc);
}

describe("SidecarManager waitForReady", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps the boot budget meaningfully smaller than the ready budget", () => {
    expect(SIDECAR_BOOT_TIMEOUT_MS).toBeLessThan(SIDECAR_READY_TIMEOUT_MS);
  });

  it("resolves with the port when the ready marker arrives", async () => {
    const manager = new SidecarManager({ pythonPath: "python" });
    const proc = makeFakeProc();
    const promise = callWaitForReady(manager, proc);
    proc.stdout.emit("data", Buffer.from("SIDECAR_BOOT\nSIDECAR_READY port=4321\n"));
    await expect(promise).resolves.toBe(4321);
  });

  it("handles a ready marker split across chunks", async () => {
    const manager = new SidecarManager({ pythonPath: "python" });
    const proc = makeFakeProc();
    const promise = callWaitForReady(manager, proc);
    proc.stdout.emit("data", Buffer.from("SIDECAR_READY po"));
    proc.stdout.emit("data", Buffer.from("rt=9876\n"));
    await expect(promise).resolves.toBe(9876);
  });

  it("fails fast when the process stays completely silent past the boot budget", async () => {
    vi.useFakeTimers();
    const manager = new SidecarManager({ pythonPath: "python" });
    const proc = makeFakeProc();
    const promise = callWaitForReady(manager, proc);
    const assertion = expect(promise).rejects.toThrow(/produced no output/);
    await vi.advanceTimersByTimeAsync(SIDECAR_BOOT_TIMEOUT_MS + 1);
    await assertion;
  });

  it("keeps waiting past the boot budget once any output is seen (cold AV scan)", async () => {
    vi.useFakeTimers();
    const statuses: string[] = [];
    const manager = new SidecarManager({ pythonPath: "python" }, (status) => {
      statuses.push(status);
    });
    const proc = makeFakeProc();
    const promise = callWaitForReady(manager, proc);

    // stderr noise inside the boot budget proves the process is alive.
    proc.stderr.emit("data", Buffer.from("some warning\n"));
    expect(statuses).toContain("booting");

    // Well past the old 30s budget — must still be waiting, not rejected.
    await vi.advanceTimersByTimeAsync(SIDECAR_BOOT_TIMEOUT_MS + 90_000);
    proc.stdout.emit("data", Buffer.from("SIDECAR_READY port=1234\n"));
    await expect(promise).resolves.toBe(1234);
  });

  it("rejects when the ready marker never arrives within the ready budget", async () => {
    vi.useFakeTimers();
    const manager = new SidecarManager({ pythonPath: "python" });
    const proc = makeFakeProc();
    const promise = callWaitForReady(manager, proc);
    proc.stdout.emit("data", Buffer.from("SIDECAR_BOOT\n"));
    const assertion = expect(promise).rejects.toThrow(/did not report ready within 240s/);
    await vi.advanceTimersByTimeAsync(SIDECAR_READY_TIMEOUT_MS + 1);
    await assertion;
  });

  it("rejects immediately when the process exits before becoming ready", async () => {
    const manager = new SidecarManager({ pythonPath: "python" });
    const proc = makeFakeProc();
    const promise = callWaitForReady(manager, proc);
    proc.emit("exit", 1);
    await expect(promise).rejects.toThrow(/exited before becoming ready/);
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
