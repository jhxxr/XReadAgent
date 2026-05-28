// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Preload script — runs in a sandboxed context before the renderer loads.
 *
 * Exposes a minimal `window.electronAPI` surface via `contextBridge` for
 * secure IPC between the renderer and the main process.
 */
import { contextBridge, ipcRenderer } from "electron";

export interface SidecarStatus {
  status: "idle" | "starting" | "running" | "stopped" | "crashed";
  pid: number | null;
  port: number | null;
  startedAt: string | null;
  restartCount: number;
}

export interface SidecarRestartInfo {
  /** Which restart attempt this is (1-based). */
  attempt: number;
  /** Maximum number of restart attempts before giving up. */
  maxAttempts: number;
  /** Delay in ms before the next restart attempt. */
  delayMs: number;
}

export type DeepLinkAction =
  | { type: "navigate"; path: string }
  | { type: "open-workspace"; path: string };

export interface ElectronAPI {
  /** The current platform: "win32" | "darwin" | "linux". */
  platform: NodeJS.Platform;
  /** Whether the app is running in packaged (production) mode. */
  isPackaged: boolean;
  /** Get the sidecar port. Returns 0 if the sidecar is not ready yet. */
  getSidecarPort: () => number;
  /** Register a callback for when the sidecar becomes ready. */
  onSidecarReady: (callback: (port: number) => void) => void;
  /** Register a callback for sidecar status updates. */
  onSidecarStatus: (callback: (status: string, detail?: string) => void) => void;
  /** Register a callback for splash status updates. */
  onSplashStatus: (callback: (message: string) => void) => void;
  /** Register a callback for splash error display. */
  onSplashError: (callback: (message: string) => void) => void;
  /** Send a retry request from the splash screen. */
  sendSplashRetry: () => void;
  /** Show an open-folder dialog and return the selected path(s). */
  showOpenFolderDialog: (title?: string) => Promise<string[]>;
  /** Show a native notification. */
  showNotification: (title: string, body: string) => void;
  /** Query the current sidecar status (running/stopped/pid/port). */
  getSidecarStatus: () => Promise<SidecarStatus>;
  /** Fetch recent sidecar log lines (stdout + stderr). */
  getSidecarLogs: () => Promise<string[]>;
  /** Request a sidecar restart from the renderer. */
  restartSidecar: () => Promise<void>;
  /** Register a callback for sidecar restarting events (crash auto-restart). */
  onSidecarRestarting: (callback: (info: SidecarRestartInfo) => void) => void;
  /** Get the current restart info, or null if no restart is in progress. */
  getSidecarRestartInfo: () => Promise<SidecarRestartInfo | null>;
  /** Register a callback for deep link navigation. */
  onDeepLink: (callback: (action: DeepLinkAction) => void) => void;
  /** Register a callback for workspace open requests (from menu or file association). */
  onOpenWorkspace: (callback: (workspacePath: string) => void) => void;
  /** Register a callback for menu-driven navigation. */
  onMenuNavigate: (callback: (path: string) => void) => void;
}

const api: ElectronAPI = {
  platform: process.platform,
  isPackaged: ipcRenderer.sendSync("is-packaged") as boolean,

  getSidecarPort: () => {
    return ipcRenderer.sendSync("get-sidecar-port") as number;
  },

  onSidecarReady: (callback: (port: number) => void) => {
    ipcRenderer.on("sidecar-ready", (_event, port: number) => callback(port));
  },

  onSidecarStatus: (callback: (status: string, detail?: string) => void) => {
    ipcRenderer.on("sidecar-status", (_event, status: string, detail: string | undefined) =>
      callback(status, detail),
    );
  },

  onSplashStatus: (callback: (message: string) => void) => {
    ipcRenderer.on("splash-status", (_event, message: string) => callback(message));
  },

  onSplashError: (callback: (message: string) => void) => {
    ipcRenderer.on("splash-error", (_event, message: string) => callback(message));
  },

  sendSplashRetry: () => {
    ipcRenderer.send("splash-retry");
  },

  showOpenFolderDialog: async (title?: string) => {
    return ipcRenderer.invoke("show-open-folder-dialog", title) as Promise<string[]>;
  },

  showNotification: (title: string, body: string) => {
    ipcRenderer.send("show-notification", title, body);
  },

  getSidecarStatus: () => {
    return ipcRenderer.invoke("sidecar:status") as Promise<SidecarStatus>;
  },

  getSidecarLogs: () => {
    return ipcRenderer.invoke("sidecar:logs") as Promise<string[]>;
  },

  restartSidecar: () => {
    return ipcRenderer.invoke("sidecar:restart") as Promise<void>;
  },

  onSidecarRestarting: (callback: (info: SidecarRestartInfo) => void) => {
    ipcRenderer.on("sidecar:restarting", (_event, info: SidecarRestartInfo) => callback(info));
  },

  getSidecarRestartInfo: () => {
    return ipcRenderer.invoke("sidecar:restart-info") as Promise<SidecarRestartInfo | null>;
  },

  onDeepLink: (callback: (action: DeepLinkAction) => void) => {
    ipcRenderer.on("deep-link", (_event, action: DeepLinkAction) => callback(action));
  },

  onOpenWorkspace: (callback: (workspacePath: string) => void) => {
    ipcRenderer.on("open-workspace", (_event, workspacePath: string) => callback(workspacePath));
  },

  onMenuNavigate: (callback: (path: string) => void) => {
    ipcRenderer.on("menu:navigate", (_event, path: string) => callback(path));
  },
};

contextBridge.exposeInMainWorld("electronAPI", api);
