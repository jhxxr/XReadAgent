// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  buildJobEventsWsUrl,
  buildWorkspaceFileUrl,
  getHealthz,
  getTranslationsManifest,
  postTranslate,
} from "@/lib/api";

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("parses a healthz response", async () => {
    const mockFetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok", version: "0.0.1" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    const result = await getHealthz();

    expect(result).toEqual({ status: "ok", version: "0.0.1" });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const call = mockFetch.mock.calls[0];
    expect(call).toBeDefined();
    const [url, init] = call!;
    const urlText = typeof url === "string" ? url : url instanceof URL ? url.toString() : "";
    expect(urlText).toMatch(/\/healthz$/);
    expect(init?.headers).toEqual(expect.objectContaining({ Accept: "application/json" }));
  });

  it("throws an ApiError on non-2xx responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("nope", { status: 503 }),
    );

    await expect(getHealthz()).rejects.toBeInstanceOf(ApiError);
  });

  it("wraps network errors as ApiError with status 0", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("fetch failed"));

    await expect(getHealthz()).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
    });
  });

  it("fetches the translations manifest", async () => {
    const manifest = {
      version: 1,
      entries: [
        {
          sourceSlug: "alpha-aaaaaaaaaaaa",
          sourceHash: "h1",
          targetLang: "zh",
          model: "anthropic:claude-3-7-sonnet-latest",
          monoPath: "translations/alpha-aaaaaaaaaaaa.mono.pdf",
          dualPath: "translations/alpha-aaaaaaaaaaaa.dual.pdf",
          translatedAt: "2026-05-25T10:00:00Z",
          durationS: 12.5,
          babeldocVersion: "0.6.2",
        },
      ],
    };
    const mockFetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify(manifest), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    const result = await getTranslationsManifest("/tmp/ws");
    expect(result).toEqual(manifest);
    const call = mockFetch.mock.calls[0];
    expect(call).toBeDefined();
    const [url] = call!;
    const urlText = typeof url === "string" ? url : url instanceof URL ? url.toString() : "";
    expect(urlText).toMatch(/\/translations\/manifest\?workspacePath=/);
  });

  it("returns an empty manifest on 404", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("missing", { status: 404 }),
    );

    const result = await getTranslationsManifest("/tmp/ws");
    expect(result).toEqual({ version: 1, entries: [] });
  });

  it("posts /translate and returns the jobId", async () => {
    const mockFetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ jobId: "job-1" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    const result = await postTranslate({
      workspacePath: "/tmp/ws",
      sourcePath: "/tmp/ws/raw/alpha.pdf",
      model: "anthropic:claude-3-7-sonnet-latest",
    });
    expect(result).toEqual({ jobId: "job-1" });
    const call = mockFetch.mock.calls[0];
    expect(call).toBeDefined();
    const [url, init] = call!;
    const urlText = typeof url === "string" ? url : url instanceof URL ? url.toString() : "";
    expect(urlText).toMatch(/\/translate$/);
    expect(init?.method).toBe("POST");
  });

  it("builds workspace file URLs that encode the path", () => {
    const url = buildWorkspaceFileUrl("/tmp/ws", "translations/alpha.dual.pdf");
    expect(url).toContain("/workspaces/file?");
    expect(url).toContain("workspacePath=%2Ftmp%2Fws");
    expect(url).toContain("path=translations%2Falpha.dual.pdf");
  });

  it("builds a job-events WS URL keyed on the job id", () => {
    const url = buildJobEventsWsUrl("job-1");
    expect(url).toMatch(/\/ws\/jobs\/job-1$/);
  });
});
