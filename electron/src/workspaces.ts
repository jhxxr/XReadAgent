// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Managed workspace registry.
 *
 * XReadAgent stores all workspaces under a single app-managed data directory
 * (`<userData>/workspaces/<slug>/`) and tracks them in a JSON registry
 * (`<userData>/workspaces.json`). This replaces the old "point at any folder"
 * model so wiki/translation artifacts never leak into the OS Downloads dir.
 *
 * Path policy (slug allocation, collision handling, directory lifecycle) lives
 * here in the Electron main process — the backend `Workspace` stays the owner
 * of the *layout inside* a root, and seeds it via `POST /api/workspaces/create`
 * once the renderer has a path from `createWorkspace`.
 */
import { app, shell } from "electron";
import { promises as fs } from "node:fs";
import * as path from "node:path";

/** One registered workspace. Persisted as camelCase JSON. */
export interface WorkspaceEntry {
  /** Stable slug — also the directory name under the workspaces root. */
  id: string;
  /** Human-readable display name (editable without moving the directory). */
  name: string;
  /** Absolute path to the workspace root. */
  path: string;
  /** ISO timestamp of creation. */
  createdAt: string;
  /** ISO timestamp this workspace was last opened (drives switcher ordering). */
  lastOpenedAt: string;
}

interface RegistryFile {
  version: 1;
  workspaces: WorkspaceEntry[];
}

const REGISTRY_VERSION = 1 as const;

/** Absolute path to the workspaces root directory (`<userData>/workspaces`). */
export function workspacesRoot(): string {
  return path.join(app.getPath("userData"), "workspaces");
}

function registryPath(): string {
  return path.join(app.getPath("userData"), "workspaces.json");
}

/**
 * Turn a free-text display name into a filesystem-safe slug. Falls back to
 * "workspace" when the name has no usable characters (e.g. only punctuation
 * or CJK that strips to empty).
 */
export function slugify(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
  return slug || "workspace";
}

async function readRegistry(): Promise<RegistryFile> {
  try {
    const raw = await fs.readFile(registryPath(), "utf-8");
    const parsed = JSON.parse(raw) as Partial<RegistryFile>;
    if (!parsed || !Array.isArray(parsed.workspaces)) {
      return { version: REGISTRY_VERSION, workspaces: [] };
    }
    return { version: REGISTRY_VERSION, workspaces: parsed.workspaces };
  } catch {
    // Missing or corrupt registry → start fresh. We never throw here so a
    // single bad write can't brick the workspace switcher.
    return { version: REGISTRY_VERSION, workspaces: [] };
  }
}

async function writeRegistry(registry: RegistryFile): Promise<void> {
  const dir = path.dirname(registryPath());
  await fs.mkdir(dir, { recursive: true });
  // Atomic-ish replace: write a temp file then rename over the target.
  const tmp = `${registryPath()}.tmp`;
  await fs.writeFile(tmp, `${JSON.stringify(registry, null, 2)}\n`, "utf-8");
  await fs.rename(tmp, registryPath());
}

/** List registered workspaces, most-recently-opened first. */
export async function listWorkspaces(): Promise<WorkspaceEntry[]> {
  const { workspaces } = await readRegistry();
  return [...workspaces].sort((a, b) => b.lastOpenedAt.localeCompare(a.lastOpenedAt));
}

/**
 * Allocate a fresh workspace directory under the managed root and register it.
 *
 * Creates the (empty) directory and a registry entry, then returns the entry.
 * The renderer is responsible for seeding the canonical layout by calling the
 * backend `POST /api/workspaces/create` with the returned `path` — the backend
 * accepts an empty directory and refuses a non-empty one.
 *
 * @param nowIso - injected ISO timestamp (the caller owns the clock so this is
 *   testable without faking `Date`).
 */
export async function createWorkspace(name: string, nowIso: string): Promise<WorkspaceEntry> {
  const displayName = name.trim() || "Workspace";
  const registry = await readRegistry();
  const taken = new Set(registry.workspaces.map((w) => w.id));

  const base = slugify(displayName);
  let id = base;
  for (let n = 2; taken.has(id) || (await pathExists(path.join(workspacesRoot(), id))); n += 1) {
    id = `${base}-${n}`;
  }

  const dir = path.join(workspacesRoot(), id);
  await fs.mkdir(dir, { recursive: true });

  const entry: WorkspaceEntry = {
    id,
    name: displayName,
    path: dir,
    createdAt: nowIso,
    lastOpenedAt: nowIso,
  };
  registry.workspaces.push(entry);
  await writeRegistry(registry);
  return entry;
}

/** Update a workspace's display name (the directory is never moved). */
export async function renameWorkspace(id: string, name: string): Promise<WorkspaceEntry> {
  const registry = await readRegistry();
  const entry = registry.workspaces.find((w) => w.id === id);
  if (!entry) {
    throw new Error(`unknown workspace: ${id}`);
  }
  entry.name = name.trim() || entry.name;
  await writeRegistry(registry);
  return entry;
}

/** Remove a workspace from the registry AND delete its directory from disk. */
export async function deleteWorkspace(id: string): Promise<void> {
  const registry = await readRegistry();
  const entry = registry.workspaces.find((w) => w.id === id);
  registry.workspaces = registry.workspaces.filter((w) => w.id !== id);
  await writeRegistry(registry);
  if (entry) {
    // Contain the rm to the managed root so a tampered registry path can't
    // delete arbitrary directories.
    const resolved = path.resolve(entry.path);
    const root = path.resolve(workspacesRoot());
    if (resolved.startsWith(root + path.sep)) {
      await fs.rm(resolved, { recursive: true, force: true });
    }
  }
}

/** Bump `lastOpenedAt` so the switcher surfaces recent workspaces first. */
export async function touchWorkspace(id: string, nowIso: string): Promise<void> {
  const registry = await readRegistry();
  const entry = registry.workspaces.find((w) => w.id === id);
  if (!entry) return;
  entry.lastOpenedAt = nowIso;
  await writeRegistry(registry);
}

/** Open the workspace directory in the OS file manager. */
export async function revealWorkspace(id: string): Promise<void> {
  const registry = await readRegistry();
  const entry = registry.workspaces.find((w) => w.id === id);
  if (!entry) {
    throw new Error(`unknown workspace: ${id}`);
  }
  await shell.openPath(entry.path);
}

async function pathExists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}
