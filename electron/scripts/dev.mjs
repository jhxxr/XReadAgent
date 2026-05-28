#!/usr/bin/env node
// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Dev script — starts esbuild in watch mode, then launches Electron.
 *
 * Usage: `pnpm dev` from the `electron/` directory.
 *
 * This script:
 * 1. Watches and rebuilds main.ts + preload.ts on changes.
 * 2. Starts Electron pointing at the Vite dev server.
 * 3. Restarts Electron when main process files change.
 *
 * Prerequisites:
 * - The Vite dev server should be running (`cd frontend && pnpm dev`)
 * - The Python sidecar should be running (`cd backend && python -m xreadagent.api`)
 */
import { build, context } from "esbuild";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(__dirname, "..", "src");
const outDir = path.resolve(__dirname, "..", "dist");

let electronProcess = null;
let isRestarting = false;

/** Common esbuild options shared between main and preload. */
const commonOptions = {
  bundle: true,
  platform: "node",
  target: "node20",
  sourcemap: true,
  minify: false,
  external: ["electron"],
};

async function main() {
  console.log("[dev] Starting esbuild in watch mode...");

  const mainCtx = await context({
    ...commonOptions,
    entryPoints: [path.join(srcDir, "main.ts")],
    outfile: path.join(outDir, "main.js"),
    format: "cjs",
  });

  const preloadCtx = await context({
    ...commonOptions,
    entryPoints: [path.join(srcDir, "preload.ts")],
    outfile: path.join(outDir, "preload.js"),
    format: "cjs",
    external: ["electron"],
  });

  // Initial build.
  await mainCtx.rebuild();
  await preloadCtx.rebuild();

  // Start Electron for the first time.
  startElectron();

  // Watch for changes.
  const mainWatcher = mainCtx.watch();
  const preloadWatcher = preloadCtx.watch();

  console.log("[dev] Watching for changes. Press Ctrl+C to stop.");

  // Keep the process alive.
  process.on("SIGINT", async () => {
    console.log("[dev] Shutting down...");
    killElectron();
    await mainCtx.dispose();
    await preloadCtx.dispose();
    process.exit(0);
  });
}

function startElectron() {
  // `require("electron")` returns the path to the Electron binary.
  const electronPath = require("electron");
  console.log("[dev] Starting Electron...");

  const args = [path.join(outDir, "main.js")];
  // Pass --no-sandbox for Linux compatibility in dev.
  if (process.platform === "linux") {
    args.unshift("--no-sandbox");
  }

  electronProcess = spawn(electronPath, args, {
    stdio: "inherit",
    env: {
      ...process.env,
      NODE_ENV: "development",
    },
  });

  electronProcess.on("close", (code) => {
    if (!isRestarting) {
      console.log(`[dev] Electron exited with code ${code}`);
    }
  });
}

function killElectron() {
  if (electronProcess && !electronProcess.killed) {
    electronProcess.kill();
    electronProcess = null;
  }
}

main().catch((err) => {
  console.error("[dev] Failed:", err);
  process.exit(1);
});