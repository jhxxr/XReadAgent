// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Build script — bundles the Electron main process and preload scripts
 * using esbuild.
 *
 * Output goes to `electron/dist/`. The preload script must be a separate
 * entry point because it runs in a different context with different
 * sandboxing rules.
 */
import { build } from "esbuild";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(__dirname, "..", "src");
const outDir = path.resolve(__dirname, "..", "dist");

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
  console.log("[build] Bundling Electron main process...");

  await build({
    ...commonOptions,
    entryPoints: [path.join(srcDir, "main.ts")],
    outfile: path.join(outDir, "main.js"),
    format: "cjs",
  });

  console.log("[build] Bundling Electron preload script...");

  await build({
    ...commonOptions,
    entryPoints: [path.join(srcDir, "preload.ts")],
    outfile: path.join(outDir, "preload.js"),
    format: "cjs",
    // Preload scripts must not bundle electron internals — they receive them
    // from the sandbox context. But we still need to bundle our own deps.
    external: ["electron"],
  });

  console.log("[build] Done.");
}

main().catch((err) => {
  console.error("[build] Failed:", err);
  process.exit(1);
});