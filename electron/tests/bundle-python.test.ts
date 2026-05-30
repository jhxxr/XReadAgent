// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Unit tests for Python bundle archive metadata.
 *
 * The bundler can download and install a full Python runtime, so these tests
 * exercise only the metadata mode that exits before network or filesystem work.
 */
import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import path from "node:path";

interface ArchiveInfo {
  filename: string;
  platformSuffix: string;
  pythonExecutableRelativePath: string;
  url: string;
}

function getArchiveInfo(platform: string, arch: string): ArchiveInfo {
  const scriptPath = path.resolve(__dirname, "..", "scripts", "bundle-python.mjs");
  const output = execFileSync(
    process.execPath,
    [scriptPath, "--print-python-archive", "--platform", platform, "--arch", arch],
    { encoding: "utf8" },
  );

  return JSON.parse(output) as ArchiveInfo;
}

describe("bundle-python archive metadata", () => {
  it("uses the real python-build-standalone Windows x64 asset name", () => {
    const info = getArchiveInfo("win32", "x64");

    expect(info.platformSuffix).toBe("x86_64-pc-windows-msvc");
    expect(info.filename).toBe(
      "cpython-3.12.8+20241219-x86_64-pc-windows-msvc-install_only.tar.gz",
    );
    expect(info.pythonExecutableRelativePath).toBe("python.exe");
    expect(info.url).toContain(info.filename);
  });

  it("uses the real python-build-standalone macOS x64 asset name", () => {
    const info = getArchiveInfo("darwin", "x64");

    expect(info.platformSuffix).toBe("x86_64-apple-darwin");
    expect(info.filename).toBe(
      "cpython-3.12.8+20241219-x86_64-apple-darwin-install_only.tar.gz",
    );
    expect(info.pythonExecutableRelativePath).toBe(path.join("bin", "python3"));
    expect(info.url).toContain(info.filename);
  });

  it("uses the real python-build-standalone macOS arm64 asset name", () => {
    const info = getArchiveInfo("darwin", "arm64");

    expect(info.platformSuffix).toBe("aarch64-apple-darwin");
    expect(info.filename).toBe(
      "cpython-3.12.8+20241219-aarch64-apple-darwin-install_only.tar.gz",
    );
    expect(info.pythonExecutableRelativePath).toBe(path.join("bin", "python3"));
    expect(info.url).toContain(info.filename);
  });
});
