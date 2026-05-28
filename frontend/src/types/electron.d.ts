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
  restartCount: number;
}

/** Information about a sidecar crash-restart cycle. */
export interface SidecarRestartInfo {
  /** Which restart attempt this is (1-based). */
  attempt: number;
  /** Maximum number of restart attempts before giving up. */
  maxAttempts: number;
  /** Delay in ms before the next restart attempt. */
  delayMs: number;
}

/** A deep link or file-open action dispatched by the main process. */
export type DeepLinkAction =
  | { type: "navigate"; path: string }
  | { type: "open-workspace"; path: string };

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
