// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Platform detection and URL resolution for dual-browser/Electron environments.
 *
 * In browser dev mode, the Vite proxy forwards `/api/*` to `localhost:8765`
 * and `/ws/*` to `ws://localhost:8765`. In Electron production mode, the
 * renderer talks directly to the sidecar on a random port injected by the
 * main process via `window.electronAPI`.
 *
 * All frontend code should use `getApiBaseUrl()` and `getWsBaseUrl()` instead
 * of hardcoding `/api` or `ws://localhost:8765`.
 */
import type { DeepLinkAction, SidecarRestartInfo } from "@/types/electron";

/**
 * Returns `true` when running inside an Electron BrowserWindow with the
 * preload bridge available.
 *
 * The check is intentionally simple: if `window.electronAPI` exists (injected
 * by the preload script via `contextBridge`), we know we're in Electron.
 */
export function isElectron(): boolean {
  return typeof window !== "undefined" && window.electronAPI != null;
}

/**
 * Get the Electron API bridge. Returns `undefined` in browser mode.
 * This is a convenience accessor for components that need direct IPC access.
 */
export function getElectronAPI(): Window["electronAPI"] | undefined {
  return window.electronAPI;
}

/**
 * Returns the sidecar port that the Electron main process assigned, or `null`
 * if we're not in Electron (browser dev mode).
 *
 * The port is available synchronously because the main process injects it
 * via `window.__XREAD_SIDECAR_PORT__` on `did-finish-load`, and the preload
 * bridge exposes `getSidecarPort()`.
 */
export function getSidecarPort(): number | null {
  if (!isElectron()) return null;

  // Prefer the synchronous preload bridge. The value is 0 if the sidecar
  // hasn't started yet — callers should wait for the healthz poll instead.
  const port = window.electronAPI?.getSidecarPort() ?? 0;
  return port > 0 ? port : null;
}

/**
 * Returns the base URL for HTTP API calls (routes under `/api/*`).
 *
 * - Electron: `http://127.0.0.1:{port}/api`
 * - Browser:  `/api` (resolved relative to origin, proxied by Vite)
 */
export function getApiBaseUrl(): string {
  if (isElectron()) {
    const port = getSidecarPort();
    if (port != null) {
      return `http://127.0.0.1:${port}/api`;
    }
  }
  return "/api";
}

/**
 * Returns the base URL for sidecar root routes (e.g. `/healthz`).
 *
 * In browser dev mode the Vite proxy strips the `/api` prefix, so root-level
 * sidecar routes like `/healthz` need a different base. In Electron mode the
 * sidecar port is known, so we talk directly to it.
 *
 * - Electron: `http://127.0.0.1:{port}`
 * - Browser:  `` (empty string — origin-relative, Vite proxies the path)
 */
export function getSidecarBaseUrl(): string {
  if (isElectron()) {
    const port = getSidecarPort();
    if (port != null) {
      return `http://127.0.0.1:${port}`;
    }
  }
  return "";
}

/**
 * Returns the base URL for WebSocket connections.
 *
 * - Electron: `ws://127.0.0.1:{port}` — callers append the full path
 *   (e.g. `/ws/jobs/{id}`).
 * - Browser:  `ws://{host}` — Vite proxy forwards `/ws` upgrades to the
 *   sidecar; callers append the path (e.g. `/ws/jobs/{id}`).
 *
 * Note: the sidecar's WS routes are rooted at `/ws/*`. The Electron path
 * must NOT include an extra `/ws` prefix because `buildJobEventsWsUrl`
 * already adds `/ws/jobs/{id}`.
 */
export function getWsBaseUrl(): string {
  if (isElectron()) {
    const port = getSidecarPort();
    if (port != null) {
      return `ws://127.0.0.1:${port}`;
    }
  }
  // Browser dev mode: use the current origin (Vite proxies /ws).
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}`;
  }
  return "ws://localhost:8765";
}

// ---------------------------------------------------------------------------
// Deep link and workspace open listeners
// ---------------------------------------------------------------------------

/**
 * Register a callback for deep link navigation from the Electron main process.
 *
 * In browser dev mode, this is a no-op (deep links only work in the
 * packaged Electron app).
 *
 * @param callback - Called with the parsed `DeepLinkAction` when a deep link
 *   or file-open event arrives. The renderer should use TanStack Router to
 *   navigate to the specified path or open the specified workspace.
 * @returns A cleanup function that removes the listener.
 */
export function onDeepLink(callback: (action: DeepLinkAction) => void): () => void {
  if (!isElectron()) return () => undefined;
  const api = getElectronAPI();
  if (!api) return () => undefined;

  api.onDeepLink(callback);
  // Return a no-op cleanup — Electron's ipcRenderer.on doesn't support
  // removing specific listeners from the preload bridge in v1.
  // If finer-grained cleanup is needed, we can add an `offDeepLink` method
  // to the bridge later.
  return () => undefined;
}

/**
 * Register a callback for workspace open requests from the Electron main process.
 *
 * Triggered when the user selects "Open Workspace" from the menu or double-clicks
 * a `.xread` file. The callback receives the workspace directory path.
 *
 * In browser dev mode, this is a no-op.
 *
 * @param callback - Called with the workspace path string.
 * @returns A cleanup function that removes the listener.
 */
export function onOpenWorkspace(callback: (workspacePath: string) => void): () => void {
  if (!isElectron()) return () => undefined;
  const api = getElectronAPI();
  if (!api) return () => undefined;

  api.onOpenWorkspace(callback);
  return () => undefined;
}

/**
 * Register a callback for menu-driven navigation from the Electron main process.
 *
 * Triggered when the user selects "Preferences" from the menu, etc.
 * The callback receives the route path to navigate to (e.g. "/settings").
 *
 * In browser dev mode, this is a no-op.
 *
 * @param callback - Called with the route path string.
 * @returns A cleanup function that removes the listener.
 */
export function onMenuNavigate(callback: (path: string) => void): () => void {
  if (!isElectron()) return () => undefined;
  const api = getElectronAPI();
  if (!api) return () => undefined;

  api.onMenuNavigate(callback);
  return () => undefined;
}

// ---------------------------------------------------------------------------
// Sidecar restart monitoring
// ---------------------------------------------------------------------------

/**
 * Register a callback for sidecar restart events (triggered when the sidecar
 * crashes and the manager is auto-restarting it).
 *
 * In browser dev mode, this is a no-op.
 *
 * @param callback - Called with `SidecarRestartInfo` when a restart is attempted.
 * @returns A cleanup function that removes the listener.
 */
export function onSidecarRestarting(callback: (info: SidecarRestartInfo) => void): () => void {
  if (!isElectron()) return () => undefined;
  const api = getElectronAPI();
  if (!api) return () => undefined;

  api.onSidecarRestarting(callback);
  return () => undefined;
}

/**
 * Get the current sidecar restart info, or null if no restart is in progress.
 *
 * In browser dev mode, returns null.
 */
export async function getSidecarRestartInfo(): Promise<SidecarRestartInfo | null> {
  if (!isElectron()) return null;
  const api = getElectronAPI();
  if (!api) return null;
  return api.getSidecarRestartInfo();
}
