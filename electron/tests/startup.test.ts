// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Unit tests for the startup renderer-load decision logic.
 *
 * The main window is created in parallel with the Python sidecar; this module
 * decides what it should display for a given (isPackaged, sidecarPort) state.
 */
import { describe, it, expect } from "vitest";

import { isRendererUrl, resolveRendererUrl } from "../src/startup";

const DEV_URL = "http://localhost:5173";

describe("resolveRendererUrl", () => {
  it("returns null while the sidecar is not ready (dev)", () => {
    expect(resolveRendererUrl(false, 0, DEV_URL)).toBeNull();
  });

  it("returns null while the sidecar is not ready (packaged)", () => {
    expect(resolveRendererUrl(true, 0, DEV_URL)).toBeNull();
  });

  it("returns the Vite dev URL once the sidecar is ready in dev", () => {
    expect(resolveRendererUrl(false, 59979, DEV_URL)).toBe(DEV_URL);
  });

  it("returns the sidecar-served SPA URL once ready in packaged mode", () => {
    expect(resolveRendererUrl(true, 59979, DEV_URL)).toBe("http://127.0.0.1:59979/");
  });

  it("treats negative and non-integer ports as not ready", () => {
    expect(resolveRendererUrl(true, -1, DEV_URL)).toBeNull();
    expect(resolveRendererUrl(false, Number.NaN, DEV_URL)).toBeNull();
    expect(resolveRendererUrl(false, 8765.5, DEV_URL)).toBeNull();
  });
});

describe("isRendererUrl", () => {
  it("rejects the inline data: loading screen", () => {
    expect(isRendererUrl("data:text/html;charset=utf-8,%3C!DOCTYPE%20html%3E")).toBe(false);
  });

  it("rejects a window with nothing loaded yet", () => {
    expect(isRendererUrl("")).toBe(false);
    expect(isRendererUrl("about:blank")).toBe(false);
  });

  it("accepts the Vite dev server and the sidecar-served SPA", () => {
    expect(isRendererUrl(DEV_URL)).toBe(true);
    expect(isRendererUrl("http://127.0.0.1:59979/")).toBe(true);
    expect(isRendererUrl("http://127.0.0.1:59979/paper/foo/read")).toBe(true);
  });
});
