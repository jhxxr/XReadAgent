// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Cross-platform notification utility.
 *
 * In Electron, uses the `showNotification` IPC bridge which sends native
 * OS notifications via the main process (supports click-to-focus, etc.).
 * In browser dev mode, falls back to the Web Notification API.
 *
 * Usage:
 * ```ts
 * import { notifyOnCompletion } from "@/lib/notifications";
 * notifyOnCompletion("Translation complete", "Paper X has been translated to English.");
 * ```
 */
import { isElectron, getElectronAPI } from "@/lib/platform";

/**
 * Show a desktop notification for a long-running operation completion.
 *
 * - In Electron: sends the notification via the main process IPC bridge,
 *   which uses Electron's `Notification` class (supports click-to-focus).
 * - In browser: falls back to the Web Notification API. If the user hasn't
 *   granted permission, the notification is silently dropped.
 *
 * @param title - Notification title (e.g. "Translation complete").
 * @param body - Notification body text (e.g. "Paper X has been translated.").
 */
export function notifyOnCompletion(title: string, body: string): void {
  if (isElectron()) {
    const api = getElectronAPI();
    if (api) {
      api.showNotification(title, body);
      return;
    }
  }

  // Browser fallback: use the Web Notification API.
  if (typeof window !== "undefined" && "Notification" in window) {
    if (Notification.permission === "granted") {
      new Notification(title, { body });
    } else if (Notification.permission !== "denied") {
      // Request permission. If the user denies, the notification is dropped.
      void Notification.requestPermission().then((permission) => {
        if (permission === "granted") {
          new Notification(title, { body });
        }
      });
    }
  }
}
