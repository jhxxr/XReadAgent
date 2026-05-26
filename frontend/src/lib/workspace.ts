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
const STORAGE_KEY = "xreadagent.workspacePath";

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
  } catch {
    // localStorage may be disabled (private mode, file:// origins, …).
    // The reader will fall back to its "no workspace" empty state.
  }
}
