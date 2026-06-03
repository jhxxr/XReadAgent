// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Workspace path persistence — Phase 2 placeholder for the future
 * workspace switcher.
 *
 * Until the UI grows a workspace picker (Phase 3+), the reader and the
 * translate dialog need *some* workspace path to talk to the sidecar.
 * We store it in `localStorage` under `xreadagent.workspacePath`. Tests
 * write to the same key — `lib/workspace` is the only place outside the
 * future workspace UI that reads/writes it.
 *
 * SSR-safe: returns `""` when `window` is undefined, mirroring the pattern
 * used by `lib/theme.tsx`.
 */
import { useEffect, useState } from "react";

const STORAGE_KEY = "xreadagent.workspacePath";
const WORKSPACE_PATH_EVENT = "xreadagent:workspace-path";

export function readWorkspacePath(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function writeWorkspacePath(value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, value);
    window.dispatchEvent(new CustomEvent(WORKSPACE_PATH_EVENT, { detail: value }));
  } catch {
    // localStorage may be disabled (private mode, file:// origins, …).
    // The reader will fall back to its "no workspace" empty state.
  }
}

export function useWorkspacePath(): string {
  const [workspacePath, setWorkspacePath] = useState(() => readWorkspacePath());

  useEffect(() => {
    const update = () => {
      setWorkspacePath(readWorkspacePath());
    };
    window.addEventListener(WORKSPACE_PATH_EVENT, update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener(WORKSPACE_PATH_EVENT, update);
      window.removeEventListener("storage", update);
    };
  }, []);

  return workspacePath;
}
