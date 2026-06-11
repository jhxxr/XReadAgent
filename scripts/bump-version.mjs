#!/usr/bin/env node
// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Version bump helper — single command for all five version locations.
 *
 * Updates:
 *   1. pyproject.toml                       [project] version
 *   2. frontend/package.json                "version"
 *   3. electron/package.json                "version"
 *   4. backend/src/xreadagent/__init__.py   __version__
 *   5. uv.lock                              via `uv lock` (xreadagent entry)
 *
 * Usage:
 *   node scripts/bump-version.mjs <new-version> [--dry-run]
 *
 * Example:
 *   node scripts/bump-version.mjs 0.0.8
 *
 * Release flow: bump -> commit -> tag v<version> -> push tag. The Release
 * workflow fails fast when the pushed tag does not match pyproject.toml.
 */
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");

const SEMVER_RE = /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/;

// Each pattern must match exactly once and capture (prefix, version, suffix).
const TARGETS = [
  {
    file: "pyproject.toml",
    pattern: /^(version = ")([^"]+)(")$/m,
  },
  {
    file: path.join("frontend", "package.json"),
    pattern: /("version":\s*")([^"]+)(")/,
  },
  {
    file: path.join("electron", "package.json"),
    pattern: /("version":\s*")([^"]+)(")/,
  },
  {
    file: path.join("backend", "src", "xreadagent", "__init__.py"),
    pattern: /^(__version__ = ")([^"]+)(")$/m,
  },
];

function usage() {
  console.error("Usage: node scripts/bump-version.mjs <new-version> [--dry-run]");
  console.error("Example: node scripts/bump-version.mjs 0.0.8");
}

function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes("--dry-run");
  const positional = args.filter((arg) => !arg.startsWith("--"));

  if (positional.length !== 1) {
    usage();
    process.exit(1);
  }

  const newVersion = positional[0];
  if (!SEMVER_RE.test(newVersion)) {
    console.error(`[bump-version] "${newVersion}" is not a valid semver version (X.Y.Z).`);
    process.exit(1);
  }

  // Read all targets first so a partial failure never leaves a half-bumped tree.
  const edits = [];
  for (const target of TARGETS) {
    const filePath = path.join(rootDir, target.file);
    const content = fs.readFileSync(filePath, "utf8");
    const match = content.match(target.pattern);
    if (!match) {
      console.error(`[bump-version] No version field found in ${target.file}.`);
      process.exit(1);
    }
    edits.push({ target, filePath, content, current: match[2] });
  }

  const currentVersions = new Set(edits.map((edit) => edit.current));
  if (currentVersions.size > 1) {
    console.warn(
      `[bump-version] WARNING: version drift detected before bump: ${[...currentVersions].join(", ")}`,
    );
  }

  for (const edit of edits) {
    console.log(
      `[bump-version] ${edit.target.file}: ${edit.current} -> ${newVersion}${dryRun ? " (dry-run)" : ""}`,
    );
    if (!dryRun) {
      const updated = edit.content.replace(edit.target.pattern, `$1${newVersion}$3`);
      fs.writeFileSync(edit.filePath, updated);
    }
  }

  if (dryRun) {
    console.log("[bump-version] uv.lock: would run `uv lock` (dry-run)");
  } else {
    console.log("[bump-version] uv.lock: running `uv lock`...");
    execSync("uv lock", { cwd: rootDir, stdio: "inherit" });
  }

  console.log(
    `\n[bump-version] ${dryRun ? "Dry-run complete — no files written." : `Done. All five locations now at ${newVersion}.`}`,
  );
  if (!dryRun) {
    console.log("[bump-version] Next: commit, then `git tag v" + newVersion + "` and push the tag.");
  }
}

main();
