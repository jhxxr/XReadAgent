// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * External link policy for renderer web contents.
 *
 * Wiki pages contain regular http(s) links (arXiv, DOI, ...). Without a
 * window-open handler, Electron opens `target="_blank"` anchors in a bare
 * chromeless child window; without a `will-navigate` guard, an in-page
 * anchor navigation can replace the app entirely.
 *
 * Policy:
 * - http(s) URLs on an allowed local origin (Vite dev server, sidecar) may
 *   navigate in place, but never spawn a child window.
 * - any other http(s) URL opens in the system default browser.
 * - everything else (file:, data:, custom schemes, malformed) is denied.
 */
import { shell } from "electron";

export type NavigationDecision = "allow" | "open-external" | "deny";

/** Decide how a navigation/window-open request for `url` should be handled. */
export function decideNavigation(
  url: string,
  allowedOrigins: readonly string[],
): NavigationDecision {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return "deny";
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return "deny";
  }
  return allowedOrigins.includes(parsed.origin) ? "allow" : "open-external";
}

/**
 * Wire the window-open and will-navigate policy onto a window's webContents.
 *
 * `getAllowedOrigins` is a getter (not a snapshot) because the sidecar origin
 * changes when the sidecar restarts on a new port. `openExternal` is
 * injectable for tests; production uses `shell.openExternal`.
 */
export function installExternalLinkHandlers(
  webContents: Electron.WebContents,
  getAllowedOrigins: () => readonly string[],
  openExternal: (url: string) => Promise<void> = (url) => shell.openExternal(url),
): void {
  webContents.setWindowOpenHandler(({ url }) => {
    // Child windows are never allowed — external http(s) goes to the system
    // browser, everything else (including allowed origins) is simply denied.
    if (decideNavigation(url, getAllowedOrigins()) === "open-external") {
      void openExternal(url);
    }
    return { action: "deny" };
  });

  webContents.on("will-navigate", (event, url) => {
    const decision = decideNavigation(url, getAllowedOrigins());
    if (decision === "allow") return;
    event.preventDefault();
    if (decision === "open-external") {
      void openExternal(url);
    }
  });
}
