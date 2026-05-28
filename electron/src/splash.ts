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
      padding: 0 24px;
    }
    .splash-error.visible {
      display: flex;
    }
    .splash-error-message {
      font-size: 14px;
      color: #f87171;
      text-align: center;
      max-width: 400px;
      line-height: 1.5;
    }
    .splash-error-detail {
      font-size: 12px;
      color: #94a3b8;
      text-align: left;
      max-width: 400px;
      max-height: 100px;
      overflow-y: auto;
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 6px;
      padding: 8px 12px;
      font-family: "Cascadia Code", "Fira Code", "Consolas", monospace;
      line-height: 1.4;
      white-space: pre-wrap;
      word-break: break-all;
    }
    .splash-btn-row {
      display: flex;
      gap: 8px;
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
    .splash-retry-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .splash-copy-btn {
      padding: 8px 16px;
      border: 1px solid #475569;
      border-radius: 6px;
      background: transparent;
      color: #94a3b8;
      font-size: 12px;
      cursor: pointer;
      transition: background 0.15s;
    }
    .splash-copy-btn:hover {
      background: #334155;
      color: #e2e8f0;
    }
    .splash-restarting {
      display: none;
      flex-direction: column;
      align-items: center;
      gap: 12px;
    }
    .splash-restarting.visible {
      display: flex;
    }
    .splash-restarting-label {
      font-size: 14px;
      color: #fbbf24;
    }
    .splash-restarting-countdown {
      font-size: 12px;
      color: #94a3b8;
    }
  </style>
</head>
<body>
  <div class="splash-container" id="loading">
    <div class="splash-logo">XReadAgent</div>
    <div class="splash-spinner"></div>
    <div class="splash-status" id="status">Starting sidecar...</div>
  </div>
  <div class="splash-container splash-restarting" id="restarting">
    <div class="splash-logo">XReadAgent</div>
    <div class="splash-spinner"></div>
    <div class="splash-restarting-label" id="restarting-label">Restarting sidecar...</div>
    <div class="splash-restarting-countdown" id="restarting-countdown"></div>
  </div>
  <div class="splash-container splash-error" id="error">
    <div class="splash-logo">XReadAgent</div>
    <div class="splash-error-message" id="error-message">Failed to start the sidecar.</div>
    <div class="splash-error-detail" id="error-detail"></div>
    <div class="splash-btn-row">
      <button class="splash-retry-btn" id="retry-btn">Retry</button>
      <button class="splash-copy-btn" id="copy-btn">Copy Error Details</button>
    </div>
  </div>
  <script>
    // Use the contextBridge API exposed by the preload script.
    var electronAPI = window.electronAPI;
    var lastErrorMessage = "";

    function showLoading() {
      document.getElementById("loading").style.display = "flex";
      document.getElementById("restarting").classList.remove("visible");
      document.getElementById("error").classList.remove("visible");
    }

    function showRestarting(info) {
      document.getElementById("loading").style.display = "none";
      document.getElementById("restarting").classList.add("visible");
      document.getElementById("error").classList.remove("visible");

      var label = document.getElementById("restarting-label");
      if (label) {
        label.textContent = "Restarting sidecar (attempt " + info.attempt + " of " + info.maxAttempts + ")...";
      }
      var countdown = document.getElementById("restarting-countdown");
      if (countdown && info.delayMs > 0) {
        var remaining = Math.ceil(info.delayMs / 1000);
        countdown.textContent = "Starting in " + remaining + "s...";
        var interval = setInterval(function() {
          remaining--;
          if (remaining <= 0) {
            clearInterval(interval);
            countdown.textContent = "";
          } else {
            countdown.textContent = "Starting in " + remaining + "s...";
          }
        }, 1000);
      }
    }

    function showError(message) {
      lastErrorMessage = message || "Unknown error";
      document.getElementById("loading").style.display = "none";
      document.getElementById("restarting").classList.remove("visible");
      var errorEl = document.getElementById("error");
      errorEl.classList.add("visible");

      // Parse known error patterns into friendly messages.
      var friendlyMessage = parseFriendlyError(lastErrorMessage);
      document.getElementById("error-message").textContent = friendlyMessage;

      // Show raw error in the detail box.
      var detailEl = document.getElementById("error-detail");
      if (detailEl) {
        detailEl.textContent = lastErrorMessage;
        detailEl.style.display = lastErrorMessage ? "block" : "none";
      }
    }

    function parseFriendlyError(message) {
      if (!message) return "Failed to start the sidecar.";

      // Python not found.
      if (message.includes("ENOENT") || message.includes("spawn") && message.includes("python")) {
        return "XReadAgent needs Python to run. Please install Python 3.11+ or reinstall XReadAgent.";
      }
      // Port binding failure.
      if (message.includes("EADDRINUSE") || message.includes("port") && message.includes("in use")) {
        return "The sidecar port is already in use. Please close other instances and try again.";
      }
      // Import error.
      if (message.includes("ImportError") || message.includes("ModuleNotFoundError")) {
        return "Python dependencies are missing. Please reinstall XReadAgent.";
      }
      // Timeout.
      if (message.includes("did not report ready") || message.includes("timeout")) {
        return "The sidecar is taking too long to start. Check your installation and try again.";
      }
      // Generic error - show as-is if short enough.
      if (message.length > 120) {
        return "The sidecar failed to start. Click 'Copy Error Details' for more information.";
      }
      return message;
    }

    if (electronAPI) {
      electronAPI.onSplashStatus(function(message) {
        var statusEl = document.getElementById("status");
        if (statusEl) statusEl.textContent = message;
        // If we receive a status update, we're still loading — hide error/restarting.
        if (message && !message.startsWith("Error")) {
          showLoading();
        }
      });

      electronAPI.onSplashError(function(message) {
        showError(message);
      });

      electronAPI.onSidecarStatus(function(status, detail) {
        // When sidecar starts restarting, show the restarting screen.
        if (status === "restarting") {
          showLoading();
          var statusEl = document.getElementById("status");
          if (statusEl) statusEl.textContent = detail || "Restarting...";
        }
      });
    }

    document.getElementById("retry-btn").addEventListener("click", function() {
      if (electronAPI) {
        // Disable the retry button while retrying.
        var btn = document.getElementById("retry-btn");
        btn.disabled = true;
        btn.textContent = "Retrying...";
        showLoading();
        var statusEl = document.getElementById("status");
        if (statusEl) statusEl.textContent = "Restarting sidecar...";
        electronAPI.sendSplashRetry();
        // Re-enable after a timeout in case the retry doesn't trigger an error.
        setTimeout(function() {
          btn.disabled = false;
          btn.textContent = "Retry";
        }, 5000);
      }
    });

    document.getElementById("copy-btn").addEventListener("click", function() {
      if (navigator.clipboard && lastErrorMessage) {
        navigator.clipboard.writeText(lastErrorMessage).then(function() {
          var btn = document.getElementById("copy-btn");
          btn.textContent = "Copied!";
          setTimeout(function() {
            btn.textContent = "Copy Error Details";
          }, 2000);
        });
      }
    });
  </script>
</body>
</html>` as const;

/** Splash window dimensions. */
export const SPLASH_WIDTH = 480;
export const SPLASH_HEIGHT = 360;
