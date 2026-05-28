// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Python sidecar lifecycle management.
 *
 * Spawns `python -m xreadagent.api --port 0`, reads the
 * `SIDECAR_READY port=<N>` marker from stdout, and polls `/healthz`
 * until the sidecar is ready. Handles graceful shutdown with
 * platform-appropriate force-kill fallback.
 */
import { spawn, type ChildProcess } from "node:child_process";
import * as http from "node:http";
import path from "node:path";

/** Maximum seconds to wait for the sidecar to become ready. */
const SIDECAR_STARTUP_TIMEOUT_MS = 30_000;

/** Maximum seconds to wait for graceful shutdown before force-killing. */
const GRACEFUL_SHUTDOWN_TIMEOUT_MS = 5_000;

/** Regex matching the `SIDECAR_READY port=<N>` marker the sidecar prints. */
export const SIDECAR_READY_RE = /^SIDECAR_READY port=(\d+)\s*$/;

/** Maximum number of times the sidecar will be auto-restarted after a crash. */
const MAX_RESTART_ATTEMPTS = 3;

/** Exponential backoff base delay in ms between restart attempts. */
const RESTART_BACKOFF_MS = 1_000;

/** Maximum number of log lines to retain in the circular buffer. */
const MAX_LOG_LINES = 200;

/** Information about a sidecar crash-restart cycle, sent to the renderer. */
export interface SidecarRestartInfo {
  /** Which restart attempt this is (1-based). */
  attempt: number;
  /** Maximum number of restart attempts before giving up. */
  maxAttempts: number;
  /** Delay in ms before the next restart attempt. */
  delayMs: number;
}

export interface SidecarOptions {
  /** Absolute path to the Python interpreter. */
  pythonPath: string;
  /** Arguments passed to the Python process (after `-m xreadagent.api`). */
  pythonArgs?: string[];
  /** Environment variables merged over `process.env`. */
  env?: Record<string, string>;
  /** Working directory for the Python process. Defaults to `process.cwd()`. */
  cwd?: string;
  /**
   * Path to the bundled venv directory (production only).
   * When set, VIRTUAL_ENV and PATH are adjusted so the sidecar uses
   * the venv's site-packages instead of the base Python's.
   */
  venvPath?: string;
  /**
   * Path to the bundled backend source directory (production only).
   * When set, PYTHONPATH includes this directory so Python can find
   * the xreadagent package.
   */
  backendPath?: string;
}

export interface SidecarHandle {
  /** The OS-assigned port the sidecar is listening on. */
  readonly port: number;
  /** The process ID of the sidecar. */
  readonly pid: number;
  /** Kill the sidecar process (graceful then forced). */
  kill(): Promise<void>;
}

type SidecarState =
  | { status: "idle" }
  | { status: "starting"; proc: ChildProcess }
  | { status: "running"; handle: SidecarHandle; proc: ChildProcess }
  | { status: "stopped" };

/**
 * Manages the Python sidecar lifecycle: spawn, health-check, auto-restart,
 * and shutdown.
 */
export class SidecarManager {
  private state: SidecarState = { status: "idle" };
  private restartCount = 0;
  private options: SidecarOptions;
  private onStatusChange?: (status: string, detail?: string, restartInfo?: SidecarRestartInfo) => void;
  /** Circular buffer of recent stdout + stderr lines. */
  private logBuffer: string[] = [];
  /** ISO timestamp when the sidecar last entered the "running" state. */
  private startedAt: string | null = null;
  /** Most recent restart info (null if no restart is in progress). */
  private currentRestartInfo: SidecarRestartInfo | null = null;

  constructor(
    options: SidecarOptions,
    onStatusChange?: (status: string, detail?: string, restartInfo?: SidecarRestartInfo) => void,
  ) {
    this.options = options;
    this.onStatusChange = onStatusChange;
  }

  /** Update the Python interpreter path (called after app is packaged-aware). */
  setPythonPath(pythonPath: string): void {
    this.options = { ...this.options, pythonPath };
  }

  /** Update sidecar options (venvPath, backendPath, etc.) for production mode. */
  setOptions(opts: Partial<SidecarOptions>): void {
    this.options = { ...this.options, ...opts };
  }

  /** Current status string for UI display. */
  get status(): string {
    switch (this.state.status) {
      case "idle":
        return "idle";
      case "starting":
        return "starting";
      case "running":
        return `running (pid=${this.state.handle.pid}, port=${this.state.handle.port})`;
      case "stopped":
        return "stopped";
    }
  }

  /** Return a structured status object for the IPC handler. */
  getStatus(): { status: SidecarState["status"] | "crashed"; pid: number | null; port: number | null; startedAt: string | null; restartCount: number } {
    if (this.state.status === "running") {
      return {
        status: "running",
        pid: this.state.handle.pid,
        port: this.state.handle.port,
        startedAt: this.startedAt,
        restartCount: this.restartCount,
      };
    }
    return {
      status: this.state.status,
      pid: null,
      port: null,
      startedAt: null,
      restartCount: this.restartCount,
    };
  }

  /** Return the current restart info, or null if no restart is in progress. */
  getRestartInfo(): SidecarRestartInfo | null {
    return this.currentRestartInfo;
  }

  /** Return the last MAX_LOG_LINES lines of sidecar output. */
  getLogs(): string[] {
    return [...this.logBuffer];
  }

  /** Start the sidecar and wait until `/healthz` returns 200. */
  async start(): Promise<SidecarHandle> {
    if (this.state.status === "running") {
      return this.state.handle;
    }

    this.emit("starting");
    const proc = this.spawnProcess();
    this.state = { status: "starting", proc };

    try {
      const port = await this.waitForReady(proc);
      await this.pollHealthz(port);
      const handle: SidecarHandle = {
        port,
        pid: proc.pid!,
        kill: () => this.killProcess(proc),
      };
      this.state = { status: "running", handle, proc };

      // Record when the sidecar became ready.
      this.startedAt = new Date().toISOString();

      // Auto-restart on unexpected exit.
      proc.on("exit", (code, signal) => {
        if (this.state.status === "running") {
          this.state = { status: "stopped" };
          this.startedAt = null;
          this.emit("crashed", `Sidecar exited with code=${code}, signal=${signal}`);
          this.attemptRestart();
        }
      });

      this.restartCount = 0;
      this.emit("ready", `port=${port}`);
      return handle;
    } catch (err) {
      this.state = { status: "stopped" };
      this.emit("error", String(err));
      throw err;
    }
  }

  /** Gracefully shut down the sidecar, waiting for the process to exit. */
  async shutdown(): Promise<void> {
    if (this.state.status === "idle" || this.state.status === "stopped") {
      return;
    }

    const proc =
      this.state.status === "starting"
        ? this.state.proc
        : this.state.status === "running"
          ? this.state.proc
          : null;

    if (proc) {
      await this.killProcess(proc);
    }

    this.state = { status: "stopped" };
    this.emit("stopped");
  }

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  private spawnProcess(): ChildProcess {
    const args = ["-m", "xreadagent.api", "--port", "0", ...(this.options.pythonArgs ?? [])];

    // Build environment: start from process.env, then layer on production overrides.
    const env: Record<string, string> = {
      ...process.env as Record<string, string>,
      PYTHONUNBUFFERED: "1",
    };

    // In production, the bundled Python needs to find:
    // 1. The venv's site-packages (for installed dependencies like fastapi, etc.)
    // 2. The backend source directory (for the xreadagent package itself)
    if (this.options.venvPath) {
      env.VIRTUAL_ENV = this.options.venvPath;
      // Prepend the venv's Scripts/ or bin/ directory to PATH so the Python
      // process can find venv-installed binaries if needed.
      const venvBin = process.platform === "win32"
        ? path.join(this.options.venvPath, "Scripts")
        : path.join(this.options.venvPath, "bin");
      env.PATH = `${venvBin}${path.delimiter}${env.PATH ?? ""}`;
    }

    if (this.options.backendPath) {
      // PYTHONPATH ensures Python can import xreadagent from the bundled source.
      env.PYTHONPATH = this.options.backendPath;
    }

    // Merge any caller-provided env overrides last (highest priority).
    Object.assign(env, this.options.env ?? {});

    const proc = spawn(this.options.pythonPath, args, {
      cwd: this.options.cwd,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    proc.stdout?.on("data", (chunk: Buffer) => {
      for (const line of chunk.toString().split("\n")) {
        if (line.trim()) {
          this.emit("stdout", line.trimEnd());
          this.appendLog(`[out] ${line.trimEnd()}`);
        }
      }
    });

    proc.stderr?.on("data", (chunk: Buffer) => {
      for (const line of chunk.toString().split("\n")) {
        if (line.trim()) {
          this.emit("stderr", line.trimEnd());
          this.appendLog(`[err] ${line.trimEnd()}`);
        }
      }
    });

    return proc;
  }

  private waitForReady(proc: ChildProcess): Promise<number> {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Sidecar did not report ready within ${SIDECAR_STARTUP_TIMEOUT_MS / 1000}s`));
      }, SIDECAR_STARTUP_TIMEOUT_MS);

      let accumulated = "";

      const onStdout = (chunk: Buffer) => {
        accumulated += chunk.toString();
        const lines = accumulated.split("\n");
        // Keep the last (possibly incomplete) line in the buffer.
        accumulated = lines.pop() ?? "";

        for (const line of lines) {
          const match = SIDECAR_READY_RE.exec(line.trim());
          if (match) {
            clearTimeout(timeout);
            proc.stdout?.removeListener("data", onStdout);
            resolve(Number(match[1]));
          }
        }
      };

      proc.stdout?.on("data", onStdout);

      proc.on("error", (err) => {
        clearTimeout(timeout);
        reject(new Error(`Sidecar process error: ${err.message}`));
      });

      proc.on("exit", (code) => {
        clearTimeout(timeout);
        reject(new Error(`Sidecar exited before becoming ready (code=${code})`));
      });
    });
  }

  private pollHealthz(port: number): Promise<void> {
    const start = Date.now();
    const interval = 200;

    return new Promise((resolve, reject) => {
      const tryCheck = () => {
        const req = http.get(`http://127.0.0.1:${port}/healthz`, (res) => {
          res.resume(); // drain the response body
          if (res.statusCode === 200) {
            resolve();
          } else if (Date.now() - start > SIDECAR_STARTUP_TIMEOUT_MS) {
            reject(new Error(`/healthz did not return 200 within timeout`));
          } else {
            setTimeout(tryCheck, interval);
          }
        });
        req.on("error", () => {
          if (Date.now() - start > SIDECAR_STARTUP_TIMEOUT_MS) {
            reject(new Error(`/healthz not reachable within timeout`));
          } else {
            setTimeout(tryCheck, interval);
          }
        });
        req.end();
      };
      tryCheck();
    });
  }

  /**
   * Kill the sidecar process with a graceful-then-force pattern.
   *
   * On POSIX: sends SIGTERM, waits GRACEFUL_SHUTDOWN_TIMEOUT_MS, then SIGKILL.
   * On Windows: sends `taskkill /PID` (graceful), waits, then `taskkill /F /PID` (force).
   */
  private killProcess(proc: ChildProcess): Promise<void> {
    return new Promise((resolve) => {
      let settled = false;

      const done = () => {
        if (!settled) {
          settled = true;
          resolve();
        }
      };

      // Resolve as soon as the process exits, regardless of how.
      proc.on("exit", () => done());

      if (process.platform === "win32") {
        // First attempt: graceful shutdown via taskkill (no /F flag).
        spawn("taskkill", ["/PID", String(proc.pid)], {
          stdio: "ignore",
          windowsHide: true,
        });
      } else {
        proc.kill("SIGTERM");
      }

      // After the grace period, force-kill.
      setTimeout(() => {
        if (!settled) {
          if (process.platform === "win32") {
            spawn("taskkill", ["/F", "/PID", String(proc.pid)], {
              stdio: "ignore",
              windowsHide: true,
            });
          } else {
            try {
              proc.kill("SIGKILL");
            } catch {
              // Already dead — that's fine.
            }
          }
          // Give the OS a moment to reap, then resolve regardless.
          setTimeout(done, 500);
        }
      }, GRACEFUL_SHUTDOWN_TIMEOUT_MS);
    });
  }

  private async attemptRestart(): Promise<void> {
    if (this.restartCount >= MAX_RESTART_ATTEMPTS) {
      this.currentRestartInfo = null;
      this.emit("fatal", `Sidecar crashed ${MAX_RESTART_ATTEMPTS} times; giving up.`);
      return;
    }

    this.restartCount++;
    const delay = RESTART_BACKOFF_MS * Math.pow(2, this.restartCount - 1);
    const info: SidecarRestartInfo = {
      attempt: this.restartCount,
      maxAttempts: MAX_RESTART_ATTEMPTS,
      delayMs: delay,
    };
    this.currentRestartInfo = info;
    this.emit("restarting", `Attempt ${this.restartCount}/${MAX_RESTART_ATTEMPTS} in ${delay}ms`, info);

    await new Promise((resolve) => setTimeout(resolve, delay));

    try {
      await this.start();
      // Successfully restarted — clear restart info.
      this.currentRestartInfo = null;
    } catch {
      // `start()` already emitted an error; `attemptRestart` will be called
      // again if the process crashes again. Keep restartInfo for UI display.
    }
  }

  private emit(status: string, detail?: string, restartInfo?: SidecarRestartInfo): void {
    this.onStatusChange?.(status, detail, restartInfo);
  }

  /** Append a line to the circular log buffer. */
  private appendLog(line: string): void {
    this.logBuffer.push(line);
    if (this.logBuffer.length > MAX_LOG_LINES) {
      this.logBuffer.splice(0, this.logBuffer.length - MAX_LOG_LINES);
    }
  }
}

// ---------------------------------------------------------------------------
// Python path resolution
// ---------------------------------------------------------------------------

/**
 * Resolve the Python interpreter path.
 *
 * In development: use the project venv.
 * In production: use the bundled `python-build-standalone` in `resources/python/`.
 *
 * `resourcesPath` defaults to `process.resourcesPath` (Electron injects this)
 * but can be overridden for testing.
 */
export function resolvePythonPath(
  app: { isPackaged: boolean; getAppPath(): string },
  resourcesPath?: string,
): string {
  if (app.isPackaged) {
    // Packaged build — use bundled Python (python-build-standalone install_only layout).
    // After extraction with --strip-components=2 (tar) or equivalent (zip),
    // the layout is:
    //   Windows: resources/python/python.exe
    //   Linux/macOS: resources/python/bin/python3
    const resPath = resourcesPath ?? process.resourcesPath;
    if (process.platform === "win32") {
      return path.join(resPath, "python", "python.exe");
    }
    return path.join(resPath, "python", "bin", "python3");
  }

  // Development — use the project's .venv.
  const projectRoot = path.resolve(app.getAppPath(), "..");
  const venvPython =
    process.platform === "win32"
      ? path.join(projectRoot, ".venv", "Scripts", "python.exe")
      : path.join(projectRoot, ".venv", "bin", "python");

  return venvPython;
}

/** Resolved paths for the sidecar's production environment. */
export interface ResolvedSidecarPaths {
  pythonPath: string;
  venvPath: string;
  backendPath: string;
}

/**
 * Resolve all production paths needed by the sidecar.
 *
 * In production, the sidecar needs to know where to find:
 * - The Python interpreter (resources/python/)
 * - The venv with dependencies (resources/python-venv/)
 * - The xreadagent package source (resources/backend/)
 *
 * In development, only pythonPath is needed (the project .venv has everything).
 */
export function resolveSidecarPaths(
  app: { isPackaged: boolean; getAppPath(): string },
  resourcesPath?: string,
): ResolvedSidecarPaths {
  const pythonPath = resolvePythonPath(app, resourcesPath);

  if (!app.isPackaged) {
    // Development: no venvPath/backendPath needed — the project .venv has everything.
    return { pythonPath, venvPath: "", backendPath: "" };
  }

  const resPath = resourcesPath ?? process.resourcesPath;
  return {
    pythonPath,
    venvPath: path.join(resPath, "python-venv"),
    backendPath: path.join(resPath, "backend"),
  };
}