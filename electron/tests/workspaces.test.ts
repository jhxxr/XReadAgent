// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Unit tests for the managed workspace registry.
 *
 * Electron's `app`/`shell` are mocked so the module runs without a real
 * Electron instance. `app.getPath("userData")` is pointed at a per-test temp
 * directory so registry + directory side effects are isolated and inspectable.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { promises as fs } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

let userDataDir = "";
const openPath = vi.fn(async () => "");

vi.mock("electron", () => ({
  app: { getPath: (_name: string) => userDataDir },
  shell: { openPath: (...args: unknown[]) => openPath(...(args as [])) },
}));

import {
  createWorkspace,
  deleteWorkspace,
  listWorkspaces,
  renameWorkspace,
  revealWorkspace,
  slugify,
  touchWorkspace,
  workspacesRoot,
} from "../src/workspaces";

beforeEach(async () => {
  userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), "xread-ws-"));
  openPath.mockClear();
});

afterEach(async () => {
  await fs.rm(userDataDir, { recursive: true, force: true });
});

describe("slugify", () => {
  it("lowercases and dashes non-alphanumerics", () => {
    expect(slugify("My Physics Papers!")).toBe("my-physics-papers");
  });

  it("falls back to 'workspace' for empty/unusable names", () => {
    expect(slugify("   ")).toBe("workspace");
    expect(slugify("中文")).toBe("workspace");
  });
});

describe("createWorkspace", () => {
  it("creates the directory under the managed root and registers it", async () => {
    const entry = await createWorkspace("My Vault", "2026-06-14T00:00:00Z");

    expect(entry.id).toBe("my-vault");
    expect(entry.name).toBe("My Vault");
    expect(entry.path).toBe(path.join(workspacesRoot(), "my-vault"));
    await expect(fs.access(entry.path)).resolves.toBeUndefined();

    const list = await listWorkspaces();
    expect(list).toHaveLength(1);
    expect(list[0]!.id).toBe("my-vault");
  });

  it("disambiguates colliding slugs", async () => {
    const a = await createWorkspace("Vault", "2026-06-14T00:00:00Z");
    const b = await createWorkspace("Vault", "2026-06-14T00:00:01Z");
    expect(a.id).toBe("vault");
    expect(b.id).toBe("vault-2");
  });
});

describe("listWorkspaces", () => {
  it("orders by most-recently-opened first", async () => {
    await createWorkspace("Old", "2026-06-14T00:00:00Z");
    await createWorkspace("New", "2026-06-14T09:00:00Z");
    const list = await listWorkspaces();
    expect(list.map((w) => w.name)).toEqual(["New", "Old"]);
  });
});

describe("renameWorkspace", () => {
  it("changes the display name without moving the directory", async () => {
    const entry = await createWorkspace("Before", "2026-06-14T00:00:00Z");
    const renamed = await renameWorkspace(entry.id, "After");
    expect(renamed.name).toBe("After");
    expect(renamed.path).toBe(entry.path);
    await expect(fs.access(entry.path)).resolves.toBeUndefined();
  });
});

describe("deleteWorkspace", () => {
  it("removes the registry entry and the directory", async () => {
    const entry = await createWorkspace("Doomed", "2026-06-14T00:00:00Z");
    await deleteWorkspace(entry.id);
    expect(await listWorkspaces()).toHaveLength(0);
    await expect(fs.access(entry.path)).rejects.toBeTruthy();
  });
});

describe("touchWorkspace", () => {
  it("updates lastOpenedAt", async () => {
    const entry = await createWorkspace("Vault", "2026-06-14T00:00:00Z");
    await touchWorkspace(entry.id, "2026-06-14T12:00:00Z");
    const [updated] = await listWorkspaces();
    expect(updated!.lastOpenedAt).toBe("2026-06-14T12:00:00Z");
  });
});

describe("revealWorkspace", () => {
  it("opens the workspace path via shell.openPath", async () => {
    const entry = await createWorkspace("Vault", "2026-06-14T00:00:00Z");
    await revealWorkspace(entry.id);
    expect(openPath).toHaveBeenCalledWith(entry.path);
  });
});
