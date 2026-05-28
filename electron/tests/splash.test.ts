// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Unit tests for splash module.
 *
 * Tests the SPLASH_HTML content for expected structure and error-handling
 * elements. Since the splash is an inline HTML string, we parse it and check
 * for the presence of key elements and scripts.
 */
import { describe, it, expect } from "vitest";

import { SPLASH_HTML, SPLASH_WIDTH, SPLASH_HEIGHT } from "../src/splash";

describe("SPLASH_HTML", () => {
  it("contains the loading screen element", () => {
    expect(SPLASH_HTML).toContain('id="loading"');
  });

  it("contains the error screen element", () => {
    expect(SPLASH_HTML).toContain('id="error"');
  });

  it("contains the error message element", () => {
    expect(SPLASH_HTML).toContain('id="error-message"');
  });

  it("contains the error detail element", () => {
    expect(SPLASH_HTML).toContain('id="error-detail"');
  });

  it("contains the retry button", () => {
    expect(SPLASH_HTML).toContain('id="retry-btn"');
  });

  it("contains the copy error button", () => {
    expect(SPLASH_HTML).toContain('id="copy-btn"');
  });

  it("contains the restarting screen element", () => {
    expect(SPLASH_HTML).toContain('id="restarting"');
  });

  it("contains the restarting label element", () => {
    expect(SPLASH_HTML).toContain('id="restarting-label"');
  });

  it("contains the restarting countdown element", () => {
    expect(SPLASH_HTML).toContain('id="restarting-countdown"');
  });

  it("contains the parseFriendlyError function", () => {
    expect(SPLASH_HTML).toContain("parseFriendlyError");
  });

  it("handles Python not found errors", () => {
    expect(SPLASH_HTML).toContain("ENOENT");
    expect(SPLASH_HTML).toContain("Python");
  });

  it("handles port in use errors", () => {
    expect(SPLASH_HTML).toContain("EADDRINUSE");
  });

  it("handles import errors", () => {
    expect(SPLASH_HTML).toContain("ImportError");
    expect(SPLASH_HTML).toContain("ModuleNotFoundError");
  });

  it("handles timeout errors", () => {
    expect(SPLASH_HTML).toContain("did not report ready");
  });

  it("references electronAPI for IPC", () => {
    expect(SPLASH_HTML).toContain("window.electronAPI");
    expect(SPLASH_HTML).toContain("onSplashStatus");
    expect(SPLASH_HTML).toContain("onSplashError");
    expect(SPLASH_HTML).toContain("sendSplashRetry");
  });

  it("includes clipboard copy functionality", () => {
    expect(SPLASH_HTML).toContain("navigator.clipboard");
  });
});

describe("SPLASH dimensions", () => {
  it("has reasonable width and height", () => {
    expect(SPLASH_WIDTH).toBe(480);
    expect(SPLASH_HEIGHT).toBeGreaterThanOrEqual(320);
  });
});