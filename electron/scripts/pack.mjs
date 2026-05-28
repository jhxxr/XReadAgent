#!/usr/bin/env node
// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Pack script — orchestrates the full Electron build pipeline.
 *
 * Steps:
 *   1. Build frontend (`cd frontend && pnpm build`)
 *   2. Build Electron main + preload scripts (`node scripts/build.mjs`)
 *   3. Check for `resources/python/` and `resources/backend/` (warn if missing)
 *   4. Run electron-builder
 *
 * Usage:
 *   pnpm pack           — directory-only build (for testing)
 *   pnpm dist           — full NSIS installer build
 *
 * Python bundling is separate: run `pnpm pack:python` before `pnpm dist`
 * to populate `resources/python/` and `resources/backend/`.
 */
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..", "..");
const electronDir = path.resolve(__dirname, "..");
const frontendDir = path.resolve(rootDir, "frontend");
const resourcesDir = path.resolve(electronDir, "resources");

function run(cmd, opts = {}) {
  console.log(`[pack] > ${cmd}`);
  try {
    execSync(cmd, { stdio: "inherit", ...opts });
  } catch (err) {
    console.error(`[pack] Command failed: ${cmd}`);
    process.exit(1);
  }
}

function checkDir(label, dirPath) {
  if (!fs.existsSync(dirPath)) {
    console.warn(`[pack] WARNING: ${label} not found at ${dirPath}`);
    console.warn(`[pack] Run \`pnpm pack:python\` to populate it before building a distributable.`);
    return false;
  }
  const entries = fs.readdirSync(dirPath);
  if (entries.length === 0) {
    console.warn(`[pack] WARNING: ${label} at ${dirPath} is empty.`);
    console.warn(`[pack] Run \`pnpm pack:python\` to populate it before building a distributable.`);
    return false;
  }
  console.log(`[pack] Found ${label} at ${dirPath} (${entries.length} entries)`);
  return true;
}

async function main() {
  const target = process.argv.includes("--dir") ? "dir" : "dist";
  console.log(`[pack] Starting Electron build pipeline (target: ${target})...\n`);

  // Step 1: Build frontend
  console.log("[pack] Step 1/4: Building frontend...");
  if (!fs.existsSync(path.join(frontendDir, "node_modules"))) {
    console.error("[pack] Frontend node_modules not found. Run `cd frontend && pnpm install` first.");
    process.exit(1);
  }
  run("pnpm build", { cwd: frontendDir });
  console.log("[pack] Frontend build complete.\n");

  // Step 2: Build Electron main + preload
  console.log("[pack] Step 2/4: Building Electron main process + preload...");
  run(`node ${path.resolve(electronDir, "scripts", "build.mjs")}`);
  console.log("[pack] Electron build complete.\n");

  // Step 3: Check for Python resources
  console.log("[pack] Step 3/4: Checking Python resources...");
  const pythonOk = checkDir("Python interpreter", path.join(resourcesDir, "python"));
  const backendOk = checkDir("Backend source", path.join(resourcesDir, "backend"));

  if (!pythonOk || !backendOk) {
    if (target === "dir") {
      console.warn("[pack] Python resources missing — directory build will continue without them.");
      console.warn("[pack] The app will fall back to the system Python / project .venv in dev mode.\n");
    } else {
      console.error("[pack] Python resources are required for a distributable build.");
      console.error("[pack] Run `pnpm pack:python` to populate resources/python/ and resources/backend/.");
      process.exit(1);
    }
  } else {
    console.log("[pack] Python resources found.\n");
  }

  // Step 4: Run electron-builder
  console.log(`[pack] Step 4/4: Running electron-builder (${target})...`);
  const builderArgs = target === "dir" ? "--dir" : "--win";
  run(`npx electron-builder ${builderArgs}`, { cwd: electronDir });

  console.log("\n[pack] Build complete!");
  if (target === "dir") {
    console.log(`[pack] Output: ${path.resolve(electronDir, "release", "win-unpacked")}`);
  } else {
    console.log(`[pack] Output: ${path.resolve(electronDir, "release")}`);
  }
}

main().catch((err) => {
  console.error("[pack] Fatal error:", err);
  process.exit(1);
});