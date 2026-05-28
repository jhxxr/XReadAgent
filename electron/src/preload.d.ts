// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Type declarations for the Electron preload bridge API.
 *
 * These types are available in the renderer process via `window.electronAPI`.
 * The main process and preload script share this interface contract.
 */
import type { ElectronAPI } from "./preload";

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
