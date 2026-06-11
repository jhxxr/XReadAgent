// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Startup / renderer-load decision logic for the main window.
 *
 * The main window is created immediately on app start (parallel to the Python
 * sidecar spawn) and shows a loading screen until the sidecar is ready. This
 * module owns the pure decision of *what* the window should display for a
 * given (isPackaged, sidecarPort) state, so it can be unit-tested without
 * Electron.
 *
 * - Dev: the renderer comes from the Vite dev server, but the frontend still
 *   needs the live sidecar port injected at load time — so in both modes we
 *   defer loading the renderer until the sidecar reports ready.
 * - Packaged: the sidecar itself serves the SPA at `http://127.0.0.1:<port>/`,
 *   so the renderer URL is unknowable until the port is known.
 */

/**
 * Resolve the URL the main window's renderer should load, or `null` when the
 * sidecar is not ready yet (the window should show/keep the loading screen).
 */
export function resolveRendererUrl(
  isPackaged: boolean,
  sidecarPort: number,
  devUrl: string,
): string | null {
  if (!Number.isInteger(sidecarPort) || sidecarPort <= 0) {
    return null;
  }
  return isPackaged ? `http://127.0.0.1:${sidecarPort}/` : devUrl;
}

/**
 * Whether `currentUrl` (from `webContents.getURL()`) is the React renderer —
 * as opposed to the inline `data:` loading screen or a not-yet-loaded window
 * (`""` / `about:blank`).
 *
 * Deep links and `.xread` file opens target the React router; sending them to
 * the loading screen would drop them silently. Callers queue the link as
 * pending instead and dispatch it on the renderer's `did-finish-load`.
 */
export function isRendererUrl(currentUrl: string): boolean {
  return currentUrl !== "" && currentUrl !== "about:blank" && !currentUrl.startsWith("data:");
}
