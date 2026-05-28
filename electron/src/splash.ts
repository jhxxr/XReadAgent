// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Splash window HTML and configuration.
 *
 * The splash window is shown while the Python sidecar is starting up.
 * It displays a simple "Starting XReadAgent..." message with status updates.
 * Uses the `window.electronAPI` bridge exposed by the preload script.
 */

/** HTML content for the splash window. */
export const SPLASH_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>XReadAgent</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      width: 100%;
      height: 100%;
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
    }
    .splash-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100%;
      gap: 24px;
    }
    .splash-logo {
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -0.5px;
      color: #f8fafc;
    }
    .splash-status {
      font-size: 14px;
      color: #94a3b8;
      text-align: center;
      min-height: 20px;
    }
    .splash-spinner {
      width: 32px;
      height: 32px;
      border: 3px solid #334155;
      border-top-color: #3b82f6;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    .splash-error {
      display: none;
      flex-direction: column;
      align-items: center;
      gap: 16px;
    }
    .splash-error.visible {
      display: flex;
    }
    .splash-error-message {
      font-size: 14px;
      color: #f87171;
      text-align: center;
      max-width: 360px;
      line-height: 1.5;
    }
    .splash-retry-btn {
      padding: 8px 24px;
      border: 1px solid #475569;
      border-radius: 6px;
      background: #1e293b;
      color: #e2e8f0;
      font-size: 14px;
      cursor: pointer;
      transition: background 0.15s;
    }
    .splash-retry-btn:hover {
      background: #334155;
    }
  </style>
</head>
<body>
  <div class="splash-container" id="loading">
    <div class="splash-logo">XReadAgent</div>
    <div class="splash-spinner"></div>
    <div class="splash-status" id="status">Starting sidecar...</div>
  </div>
  <div class="splash-container splash-error" id="error">
    <div class="splash-logo">XReadAgent</div>
    <div class="splash-error-message" id="error-message">Failed to start the sidecar.</div>
    <button class="splash-retry-btn" id="retry-btn">Retry</button>
  </div>
  <script>
    // Use the contextBridge API exposed by the preload script.
    var electronAPI = window.electronAPI;

    if (electronAPI) {
      electronAPI.onSplashStatus(function(message) {
        var statusEl = document.getElementById("status");
        if (statusEl) statusEl.textContent = message;
      });

      electronAPI.onSplashError(function(message) {
        document.getElementById("loading").style.display = "none";
        var errorEl = document.getElementById("error");
        errorEl.classList.add("visible");
        document.getElementById("error-message").textContent = message;
      });
    }

    document.getElementById("retry-btn").addEventListener("click", function() {
      if (electronAPI) {
        electronAPI.sendSplashRetry();
      }
    });
  </script>
</body>
</html>` as const;

/** Splash window dimensions. */
export const SPLASH_WIDTH = 480;
export const SPLASH_HEIGHT = 320;