// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Preload script — runs in a sandboxed context before the renderer loads.
 *
 * Exposes a minimal `window.electronAPI` surface via `contextBridge` for
 * secure IPC between the renderer and the main process.
 */
import { contextBridge, ipcRenderer } from "electron";

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
};

contextBridge.exposeInMainWorld("electronAPI", api);