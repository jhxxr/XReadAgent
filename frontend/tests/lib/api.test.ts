// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, getHealthz } from "@/lib/api";

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
});
