// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Unit tests for the external link policy.
 *
 * `main.ts` itself is not unit-testable (it drives the app lifecycle on
 * import), so the policy lives in `external-links.ts` and is tested against
 * a fake webContents.
 */
import { describe, expect, it, vi } from "vitest";

vi.mock("electron", () => ({
  shell: {
    openExternal: vi.fn().mockResolvedValue(undefined),
  },
}));

import { decideNavigation, installExternalLinkHandlers } from "../src/external-links";

const ALLOWED = ["http://localhost:5173", "http://127.0.0.1:50123"] as const;

describe("decideNavigation", () => {
  it("allows http(s) URLs on an allowed origin", () => {
    expect(decideNavigation("http://localhost:5173/workspace", ALLOWED)).toBe("allow");
    expect(decideNavigation("http://127.0.0.1:50123/paper/x/read", ALLOWED)).toBe("allow");
  });

  it("opens external http(s) URLs in the system browser", () => {
    expect(decideNavigation("https://arxiv.org/abs/2406.01234", ALLOWED)).toBe("open-external");
    expect(decideNavigation("http://example.com/", ALLOWED)).toBe("open-external");
    // Same host but different port is a different origin.
    expect(decideNavigation("http://127.0.0.1:9999/", ALLOWED)).toBe("open-external");
  });

  it("denies non-http schemes and malformed URLs", () => {
    expect(decideNavigation("file:///C:/Windows/system32", ALLOWED)).toBe("deny");
    expect(decideNavigation("data:text/html,<script>alert(1)</script>", ALLOWED)).toBe("deny");
    expect(decideNavigation("xread://paper/slug", ALLOWED)).toBe("deny");
    expect(decideNavigation("not a url", ALLOWED)).toBe("deny");
  });
});

interface FakeWebContents {
  windowOpenHandler: ((details: { url: string }) => { action: string }) | null;
  willNavigateListener: ((event: { preventDefault: () => void }, url: string) => void) | null;
  setWindowOpenHandler(handler: (details: { url: string }) => { action: string }): void;
  on(event: string, listener: (event: { preventDefault: () => void }, url: string) => void): void;
}

function createFakeWebContents(): FakeWebContents {
  return {
    windowOpenHandler: null,
    willNavigateListener: null,
    setWindowOpenHandler(handler) {
      this.windowOpenHandler = handler;
    },
    on(event, listener) {
      if (event === "will-navigate") {
        this.willNavigateListener = listener;
      }
    },
  };
}

function install(fake: FakeWebContents, openExternal: (url: string) => Promise<void>): void {
  installExternalLinkHandlers(
    fake as unknown as Electron.WebContents,
    () => ALLOWED,
    openExternal,
  );
}

describe("installExternalLinkHandlers", () => {
  it("denies window.open for external URLs and opens them externally", () => {
    const fake = createFakeWebContents();
    const openExternal = vi.fn().mockResolvedValue(undefined);
    install(fake, openExternal);

    const result = fake.windowOpenHandler?.({ url: "https://arxiv.org/abs/2406.01234" });
    expect(result).toEqual({ action: "deny" });
    expect(openExternal).toHaveBeenCalledWith("https://arxiv.org/abs/2406.01234");
  });

  it("denies window.open for allowed origins without opening a browser", () => {
    const fake = createFakeWebContents();
    const openExternal = vi.fn().mockResolvedValue(undefined);
    install(fake, openExternal);

    const result = fake.windowOpenHandler?.({ url: "http://localhost:5173/workspace" });
    expect(result).toEqual({ action: "deny" });
    expect(openExternal).not.toHaveBeenCalled();
  });

  it("denies window.open for non-http schemes without opening a browser", () => {
    const fake = createFakeWebContents();
    const openExternal = vi.fn().mockResolvedValue(undefined);
    install(fake, openExternal);

    const result = fake.windowOpenHandler?.({ url: "file:///etc/passwd" });
    expect(result).toEqual({ action: "deny" });
    expect(openExternal).not.toHaveBeenCalled();
  });

  it("blocks will-navigate to external URLs and opens the system browser", () => {
    const fake = createFakeWebContents();
    const openExternal = vi.fn().mockResolvedValue(undefined);
    install(fake, openExternal);

    const preventDefault = vi.fn();
    fake.willNavigateListener?.({ preventDefault }, "https://doi.org/10.1000/xyz");
    expect(preventDefault).toHaveBeenCalled();
    expect(openExternal).toHaveBeenCalledWith("https://doi.org/10.1000/xyz");
  });

  it("lets will-navigate proceed for allowed origins", () => {
    const fake = createFakeWebContents();
    const openExternal = vi.fn().mockResolvedValue(undefined);
    install(fake, openExternal);

    const preventDefault = vi.fn();
    fake.willNavigateListener?.({ preventDefault }, "http://127.0.0.1:50123/settings");
    expect(preventDefault).not.toHaveBeenCalled();
    expect(openExternal).not.toHaveBeenCalled();
  });

  it("blocks will-navigate to non-http schemes without opening anything", () => {
    const fake = createFakeWebContents();
    const openExternal = vi.fn().mockResolvedValue(undefined);
    install(fake, openExternal);

    const preventDefault = vi.fn();
    fake.willNavigateListener?.({ preventDefault }, "file:///C:/secret.txt");
    expect(preventDefault).toHaveBeenCalled();
    expect(openExternal).not.toHaveBeenCalled();
  });
});
