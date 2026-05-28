// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Type declarations for the Electron preload bridge API.
 *
 * When running in Electron, `window.electronAPI` is injected by the preload
 * script. In browser dev mode, these types exist only so that TypeScript
 * checks pass — the actual object is absent and `isElectron()` returns false.
 *
 * These types must stay in sync with `electron/src/preload.ts`.
 */

/** Structured sidecar status returned by the `sidecar:status` IPC handler. */
export interface SidecarStatus {
  status: "idle" | "starting" | "running" | "stopped" | "crashed";
  pid: number | null;
  port: number | null;
  startedAt: string | null;
}

/** The full Electron bridge API surface exposed via contextBridge. */
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
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
    /**
     * The port the Python sidecar is listening on.
     * Injected by the main process after the sidecar becomes ready.
     */
    __XREAD_SIDECAR_PORT__?: number;
  }
}

export {};
