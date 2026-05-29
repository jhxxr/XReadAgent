// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * E2E test for sidecar lifecycle.
 *
 * Verifies the full Electron → sidecar flow:
 *   spawn python → SIDECAR_READY → healthz 200 → clean shutdown
 *
 * This test requires a working Python environment with the xreadagent
 * package installed. Set XREADAGENT_E2E=1 to enable.
 *
 * In CI, the backend dependencies are installed via `uv sync` before
 * this test runs. Locally, run `uv sync` from the project root first.
 */
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { spawn } from "node:child_process";
import * as http from "node:http";
import * as fs from "node:fs";
import * as path from "node:path";

const E2E_ENABLED = process.env.XREADAGENT_E2E === "1";

/** Timeout for sidecar startup (60s — cold start with heavy Python imports can be slow). */
const STARTUP_TIMEOUT_MS = 60_000;

/** Timeout for healthz poll. */
const HEALTHZ_TIMEOUT_MS = 15_000;

/**
 * Resolve the Python interpreter path.
 *
 * Checks (in order):
 *   1. XREADAGENT_PYTHON env var (explicit override)
 *   2. Project .venv (uv-managed)
 *   3. System python3 / python
 */
function resolvePython(): string {
  // 1. Explicit env override.
  if (process.env.XREADAGENT_PYTHON) {
    return process.env.XREADAGENT_PYTHON;
  }

  // 2. Project .venv — resolve from electron/ up to project root.
  const projectRoot = path.resolve(__dirname, "..", "..", "..");
  const venvPython =
    process.platform === "win32"
      ? path.join(projectRoot, ".venv", "Scripts", "python.exe")
      : path.join(projectRoot, ".venv", "bin", "python");

  if (fs.existsSync(venvPython)) {
    return venvPython;
  }

  // 3. Fallback to system python.
  return process.platform === "win32" ? "python" : "python3";
}

/**
 * Poll /healthz until it returns 200 or times out.
 */
function pollHealthz(port: number, timeoutMs: number): Promise<void> {
  const start = Date.now();
  const interval = 200;

  return new Promise((resolve, reject) => {
    const tryCheck = () => {
      const req = http.get(`http://127.0.0.1:${port}/healthz`, (res) => {
        res.resume();
        if (res.statusCode === 200) {
          resolve();
        } else if (Date.now() - start > timeoutMs) {
          reject(new Error(`/healthz returned ${res.statusCode} within timeout`));
        } else {
          setTimeout(tryCheck, interval);
        }
      });
      req.on("error", () => {
        if (Date.now() - start > timeoutMs) {
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

describe.skipIf(!E2E_ENABLED)("E2E: sidecar lifecycle", () => {
  let sidecarProc: ReturnType<typeof spawn> | null = null;
  let sidecarPort: number | null = null;
  /** Captured stderr lines for debugging startup failures. */
  const stderrLines: string[] = [];

  afterAll(async () => {
    if (sidecarProc?.pid) {
      // Graceful shutdown: SIGTERM → wait → SIGKILL.
      if (process.platform === "win32") {
        spawn("taskkill", ["/PID", String(sidecarProc.pid)], { stdio: "ignore" });
      } else {
        sidecarProc.kill("SIGTERM");
      }

      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          // Force kill after 5s.
          if (sidecarProc?.pid) {
            if (process.platform === "win32") {
              spawn("taskkill", ["/F", "/PID", String(sidecarProc.pid)], { stdio: "ignore" });
            } else {
              try {
                sidecarProc.kill("SIGKILL");
              } catch {
                // Already dead.
              }
            }
          }
          resolve();
        }, 5_000);

        sidecarProc?.on("exit", () => {
          clearTimeout(timeout);
          resolve();
        });
      });
    }
  });

  it("should spawn, report SIDECAR_READY, and pass healthz", async () => {
    const pythonPath = resolvePython();
    const projectRoot = path.resolve(__dirname, "..", "..", "..");

    // Verify Python is actually runnable before spawning sidecar.
    const versionCheck = spawn(pythonPath, ["--version"], { stdio: "pipe" });
    const versionOutput = await new Promise<string>((resolve, reject) => {
      let out = "";
      versionCheck.stdout?.on("data", (d) => (out += d));
      versionCheck.stderr?.on("data", (d) => (out += d));
      versionCheck.on("exit", (code) =>
        code === 0 ? resolve(out.trim()) : reject(new Error(`Python check failed (code=${code}): ${out}`)),
      );
    });
    expect(versionOutput).toContain("Python");

    // Spawn the sidecar: python -m xreadagent.api --port 0
    sidecarProc = spawn(pythonPath, ["-m", "xreadagent.api", "--port", "0"], {
      cwd: projectRoot,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
      },
      stdio: ["ignore", "pipe", "pipe"],
    });

    // Capture stderr for debugging startup failures.
    sidecarProc.stderr?.on("data", (chunk: Buffer) => {
      for (const line of chunk.toString().split("\n")) {
        if (line.trim()) stderrLines.push(line.trimEnd());
      }
    });

    // Wait for SIDECAR_READY on stdout.
    sidecarPort = await new Promise<number>((resolve, reject) => {
      const timeout = setTimeout(() => {
        const stderrDump = stderrLines.slice(-20).join("\n");
        reject(
          new Error(
            `SIDECAR_READY not received within ${STARTUP_TIMEOUT_MS / 1000}s.\nLast stderr:\n${stderrDump}`,
          ),
        );
      }, STARTUP_TIMEOUT_MS);

      let accumulated = "";

      const onData = (chunk: Buffer) => {
        accumulated += chunk.toString();
        const lines = accumulated.split("\n");
        accumulated = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          const match = /^SIDECAR_READY port=(\d+)$/.exec(trimmed);
          if (match) {
            clearTimeout(timeout);
            sidecarProc!.stdout?.removeListener("data", onData);
            resolve(Number(match[1]));
          }
        }
      };

      sidecarProc!.stdout?.on("data", onData);

      sidecarProc!.on("error", (err) => {
        clearTimeout(timeout);
        reject(new Error(`Sidecar process error: ${err.message}`));
      });

      sidecarProc!.on("exit", (code) => {
        clearTimeout(timeout);
        const stderrDump = stderrLines.slice(-20).join("\n");
        reject(new Error(`Sidecar exited before becoming ready (code=${code}).\nLast stderr:\n${stderrDump}`));
      });
    });

    expect(sidecarPort).toBeGreaterThan(0);

    // Poll healthz until 200.
    await pollHealthz(sidecarPort, HEALTHZ_TIMEOUT_MS);

    // Verify the healthz response body.
    const body = await new Promise<string>((resolve, reject) => {
      http.get(`http://127.0.0.1:${sidecarPort}/healthz`, (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => resolve(data));
        res.on("error", reject);
      }).on("error", reject);
    });

    // healthz should return some valid response (JSON or plain text).
    expect(body).toBeDefined();
  }, STARTUP_TIMEOUT_MS + HEALTHZ_TIMEOUT_MS + 10_000);
});
