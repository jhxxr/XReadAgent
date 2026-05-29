#!/usr/bin/env node
// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Python bundling helper for XReadAgent desktop packaging.
 *
 * Downloads python-build-standalone CPython 3.12, creates a virtual
 * environment with the project dependencies, and copies the backend source.
 *
 * This script is NOT part of the default build pipeline. Run it manually:
 *   pnpm pack:python
 *
 * Prerequisites:
 *   - `uv` must be installed (https://docs.astral.sh/uv/)
 *   - Project pyproject.toml must exist at the repository root
 *   - Internet access for downloading python-build-standalone and pip packages
 *
 * Output:
 *   resources/python/  — relocatable CPython 3.12 installation
 *   resources/backend/ — xreadagent package source
 *
 * After running this script, run `pnpm dist` to build the installer.
 */
import { execSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..", "..");
const electronDir = path.resolve(__dirname, "..");
const backendDir = path.resolve(rootDir, "backend");
const projectPyprojectPath = path.join(rootDir, "pyproject.toml");
const resourcesDir = path.resolve(electronDir, "resources");
const pythonDir = path.join(resourcesDir, "python");
const backendOutDir = path.join(resourcesDir, "backend");

// python-build-standalone release info.
// See: https://github.com/astral-sh/python-build-standalone/releases
const PYTHON_VERSION = "3.12.8";
const PYTHON_RELEASE_TAG = "20241219";
const PLATFORM = os.platform();
const ARCH = os.arch();

/**
 * Determine the python-build-standalone archive URL for the current platform.
 */
function getPythonArchiveUrl() {
  // Map Node arch to python-build-standalone arch names.
  let psArch = ARCH;
  if (PLATFORM === "win32") {
    psArch = ARCH === "x64" ? "x86_64" : ARCH;
  } else if (PLATFORM === "darwin") {
    psArch = ARCH === "arm64" ? "aarch64" : "x86_64";
  } else {
    psArch = ARCH === "arm64" ? "aarch64" : "x86_64";
  }

  let ext = "tar.gz";
  let platformSuffix = "unknown";
  if (PLATFORM === "win32") {
    ext = "zip";
    platformSuffix = `windows-${psArch}`;
  } else if (PLATFORM === "darwin") {
    // python-build-standalone uses "{arch}-apple-darwin" for macOS,
    // NOT "macos-{arch}". See: https://github.com/astral-sh/python-build-standalone
    platformSuffix = `${psArch}-apple-darwin`;
  } else {
    platformSuffix = `linux-${psArch}`;
  }

  const filename = `cpython-${PYTHON_VERSION}+${PYTHON_RELEASE_TAG}-${platformSuffix}-install_only.${ext}`;
  const url = `https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_RELEASE_TAG}/${filename}`;
  return { url, filename };
}

function run(cmd, opts = {}) {
  console.log(`[bundle-python] > ${cmd}`);
  try {
    execSync(cmd, { stdio: "inherit", ...opts });
  } catch (err) {
    console.error(`[bundle-python] Command failed: ${cmd}`);
    process.exit(1);
  }
}

function checkCommand(cmd) {
  try {
    execSync(`${cmd} --version`, { stdio: "pipe" });
    return true;
  } catch {
    return false;
  }
}

async function main() {
  console.log("[bundle-python] XReadAgent Python bundler");
  console.log(`[bundle-python] Platform: ${PLATFORM} ${ARCH}`);
  console.log(`[bundle-python] Python version: ${PYTHON_VERSION}`);
  console.log();

  // Check prerequisites
  if (!checkCommand("uv")) {
    console.error("[bundle-python] `uv` is required but not found on PATH.");
    console.error("[bundle-python] Install it from https://docs.astral.sh/uv/");
    process.exit(1);
  }
  console.log("[bundle-python] Found `uv` on PATH.");

  if (!fs.existsSync(projectPyprojectPath)) {
    console.error(`[bundle-python] Project pyproject.toml not found at ${projectPyprojectPath}`);
    process.exit(1);
  }

  // Create resources directory if needed.
  fs.mkdirSync(resourcesDir, { recursive: true });

  // ---------------------------------------------------------------------------
  // Step 1: Download python-build-standalone
  // ---------------------------------------------------------------------------
  console.log("\n[bundle-python] Step 1/4: Downloading python-build-standalone...");

  const { url: archiveUrl, filename: archiveName } = getPythonArchiveUrl();
  const archivePath = path.join(resourcesDir, archiveName);

  if (fs.existsSync(pythonDir) && fs.readdirSync(pythonDir).length > 0) {
    console.log(`[bundle-python] Python directory already exists at ${pythonDir}`);
    console.log("[bundle-python] Delete it first if you want to re-download.");
  } else {
    console.log(`[bundle-python] Downloading: ${archiveUrl}`);

    if (!fs.existsSync(archivePath)) {
      // Use curl for download (available on Windows 10+, macOS, Linux).
      run(`curl -L -o "${archivePath}" "${archiveUrl}"`);
    } else {
      console.log(`[bundle-python] Archive already downloaded: ${archivePath}`);
    }

    // Extract the archive.
    // python-build-standalone install_only archives have this layout:
    //   cpython-3.12.8+20241219-<platform>-install_only/python/
    //     (Windows) python.exe, Lib/, ...
    //     (Linux/macOS) bin/python3, lib/python3.12/, ...
    // We need --strip-components=2 (or equivalent) to move the contents of
    // the inner "python/" directory directly into resources/python/.
    console.log("[bundle-python] Extracting...");
    fs.mkdirSync(pythonDir, { recursive: true });

    if (archiveName.endsWith(".zip")) {
      // Windows: use PowerShell to extract zip.
      const absPythonDir = path.resolve(pythonDir);
      // Extract to a temp dir first, then locate and move the inner python/ contents.
      const tmpDir = path.join(resourcesDir, "_python_extract_tmp");
      if (fs.existsSync(tmpDir)) {
        fs.rmSync(tmpDir, { recursive: true, force: true });
      }
      fs.mkdirSync(tmpDir, { recursive: true });

      run(`powershell -Command "Expand-Archive -Path '${archivePath}' -DestinationPath '${tmpDir}' -Force"`);

      // The zip extracts to: tmpDir/cpython-...-install_only/python/
      // We need to find the "python/" subdirectory and move its contents.
      const extracted = fs.readdirSync(tmpDir);
      let pythonSrcDir = null;

      for (const entry of extracted) {
        const entryPath = path.join(tmpDir, entry);
        if (fs.statSync(entryPath).isDirectory()) {
          // Look for the "python" subdirectory inside the release directory.
          const innerEntries = fs.readdirSync(entryPath);
          const pythonSub = innerEntries.find((e) =>
            e.toLowerCase() === "python" &&
            fs.statSync(path.join(entryPath, e)).isDirectory(),
          );
          if (pythonSub) {
            pythonSrcDir = path.join(entryPath, pythonSub);
            break;
          }
        }
      }

      if (pythonSrcDir) {
        // Move contents of python/ to resources/python/
        const entries = fs.readdirSync(pythonSrcDir);
        for (const entry of entries) {
          const src = path.join(pythonSrcDir, entry);
          const dest = path.join(absPythonDir, entry);
          fs.renameSync(src, dest);
        }
      } else {
        console.error("[bundle-python] Could not find 'python/' directory inside the archive.");
        console.error("[bundle-python] Archive structure may have changed. Please check and update this script.");
        process.exit(1);
      }

      // Clean up temp dir.
      fs.rmSync(tmpDir, { recursive: true, force: true });
    } else {
      // tar.gz on macOS/Linux.
      // --strip-components=2 removes: cpython-...-install_only/ and python/
      run(`tar -xzf "${archivePath}" -C "${pythonDir}" --strip-components=2`);
    }

    console.log("[bundle-python] Python extraction complete.");
  }

  // Verify python executable exists.
  // After --strip-components=2, the layout is:
  //   Windows: resources/python/python.exe
  //   Linux/macOS: resources/python/bin/python3
  const pythonExe = PLATFORM === "win32"
    ? path.join(pythonDir, "python.exe")
    : path.join(pythonDir, "bin", "python3");

  if (!fs.existsSync(pythonExe)) {
    console.error(`[bundle-python] Python executable not found at ${pythonExe}`);
    console.error("[bundle-python] The python-build-standalone archive structure may have changed.");
    console.error("[bundle-python] Please check the extraction and update this script if needed.");
    process.exit(1);
  }
  console.log(`[bundle-python] Python executable found at ${pythonExe}`);

  // ---------------------------------------------------------------------------
  // Step 2: Create venv and install backend dependencies
  // ---------------------------------------------------------------------------
  console.log("\n[bundle-python] Step 2/4: Creating virtual environment and installing dependencies...");

  const venvDir = path.join(resourcesDir, "python-venv");

  if (fs.existsSync(venvDir)) {
    console.log(`[bundle-python] Removing existing venv at ${venvDir}`);
    fs.rmSync(venvDir, { recursive: true, force: true });
  }

  // Use uv to create a venv with the bundled python.
  // The python executable path matches the layout after extraction:
  //   Windows: resources/python/python.exe
  //   Linux/macOS: resources/python/bin/python3
  const resolvedPythonExe = PLATFORM === "win32"
    ? path.join(pythonDir, "python.exe")
    : path.join(pythonDir, "bin", "python3");

  run(`uv venv "${venvDir}" --python "${resolvedPythonExe}"`);

  // Install backend dependencies into the venv.
  // Use a non-editable project install so uv resolves dependencies from the root
  // pyproject.toml. At runtime, resources/backend is placed on PYTHONPATH so the
  // packaged source copied below takes precedence over the wheel copy.
  const venvPythonExe = PLATFORM === "win32"
    ? path.join(venvDir, "Scripts", "python.exe")
    : path.join(venvDir, "bin", "python");

  // Install the backend package dependencies (non-editable) into the venv.
  // This resolves all transitive deps from pyproject.toml and installs them
  // into the venv's site-packages.
  run(`uv pip install --python "${venvPythonExe}" "${rootDir}"`);

  console.log("[bundle-python] Dependencies installed.");

  // ---------------------------------------------------------------------------
  // Step 3: Copy backend source
  // ---------------------------------------------------------------------------
  console.log("\n[bundle-python] Step 3/4: Copying backend source...");

  // Clean previous backend output.
  if (fs.existsSync(backendOutDir)) {
    fs.rmSync(backendOutDir, { recursive: true, force: true });
  }
  fs.mkdirSync(backendOutDir, { recursive: true });

  // Copy the xreadagent package source.
  const srcDir = path.join(backendDir, "src", "xreadagent");
  if (!fs.existsSync(srcDir)) {
    console.error(`[bundle-python] Backend source not found at ${srcDir}`);
    process.exit(1);
  }

  // Copy src/xreadagent/ -> resources/backend/xreadagent/
  const destXreadagent = path.join(backendOutDir, "xreadagent");
  fs.cpSync(srcDir, destXreadagent, { recursive: true });

  // Copy pyproject.toml for reference (version info, dependency metadata).
  fs.copyFileSync(
    projectPyprojectPath,
    path.join(backendOutDir, "pyproject.toml"),
  );

  console.log("[bundle-python] Backend source copied.");

  // ---------------------------------------------------------------------------
  // Step 4: Summary
  // ---------------------------------------------------------------------------
  console.log("\n[bundle-python] Step 4/4: Summary");
  console.log(`[bundle-python] Python interpreter: ${pythonDir}`);
  console.log(`[bundle-python] Virtual env:       ${venvDir}`);
  console.log(`[bundle-python] Backend source:    ${backendOutDir}`);

  // Calculate approximate sizes.
  function getDirSize(dirPath) {
    let size = 0;
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dirPath, entry.name);
      if (entry.isDirectory()) {
        size += getDirSize(fullPath);
      } else {
        try {
          size += fs.statSync(fullPath).size;
        } catch {
          // Skip files that can't be stat'd (e.g., locked files).
        }
      }
    }
    return size;
  }

  const pythonSize = getDirSize(pythonDir);
  const backendSize = getDirSize(backendOutDir);
  const venvSize = fs.existsSync(venvDir) ? getDirSize(venvDir) : 0;
  const totalMB = ((pythonSize + backendSize + venvSize) / 1024 / 1024).toFixed(1);

  console.log(`[bundle-python] Python size:      ${(pythonSize / 1024 / 1024).toFixed(1)} MB`);
  console.log(`[bundle-python] Backend size:      ${(backendSize / 1024 / 1024).toFixed(1)} MB`);
  console.log(`[bundle-python] Venv size:         ${(venvSize / 1024 / 1024).toFixed(1)} MB`);
  console.log(`[bundle-python] Total:             ${totalMB} MB`);
  console.log("\n[bundle-python] Done! Run `pnpm dist` to build the installer.");
}

main().catch((err) => {
  console.error("[bundle-python] Fatal error:", err);
  process.exit(1);
});
