// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Unit tests for deep link parsing and file association handling.
 */
import { describe, it, expect } from "vitest";

import { parseDeepLink, parseXreadFile } from "../src/deeplink";

// ---------------------------------------------------------------------------
// parseDeepLink
// ---------------------------------------------------------------------------

describe("parseDeepLink", () => {
  it("parses xread://paper/{slug} into a navigate action", () => {
    const result = parseDeepLink("xread://paper/attention-is-all-you-need");
    expect(result).toEqual({
      type: "navigate",
      path: "/paper/attention-is-all-you-need",
    });
  });

  it("parses xread://paper/{slug} with trailing slash", () => {
    const result = parseDeepLink("xread://paper/my-paper/");
    expect(result).toEqual({
      type: "navigate",
      path: "/paper/my-paper",
    });
  });

  it("parses xread://query/{topic}/{slug}", () => {
    const result = parseDeepLink("xread://query/rl/what-is-rlhf");
    expect(result).toEqual({
      type: "navigate",
      path: "/query/rl/what-is-rlhf",
    });
  });

  it("parses xread://query/{id} with single segment", () => {
    const result = parseDeepLink("xread://query/some-id");
    expect(result).toEqual({
      type: "navigate",
      path: "/query/some-id",
    });
  });

  it("parses xread://workspace", () => {
    const result = parseDeepLink("xread://workspace");
    expect(result).toEqual({
      type: "navigate",
      path: "/workspace",
    });
  });

  it("parses xread://workspace/", () => {
    const result = parseDeepLink("xread://workspace/");
    expect(result).toEqual({
      type: "navigate",
      path: "/workspace",
    });
  });

  it("parses xread://settings", () => {
    const result = parseDeepLink("xread://settings");
    expect(result).toEqual({
      type: "navigate",
      path: "/settings",
    });
  });

  it("parses xread://settings/", () => {
    const result = parseDeepLink("xread://settings/");
    expect(result).toEqual({
      type: "navigate",
      path: "/settings",
    });
  });

  it("returns null for non-xread URLs", () => {
    expect(parseDeepLink("https://example.com")).toBeNull();
  });

  it("returns null for xread://paper/ (empty slug)", () => {
    expect(parseDeepLink("xread://paper/")).toBeNull();
  });

  it("returns null for xread://paper (no slash)", () => {
    expect(parseDeepLink("xread://paper")).toBeNull();
  });

  it("returns null for xread://query/ (empty rest)", () => {
    expect(parseDeepLink("xread://query/")).toBeNull();
  });

  it("returns null for unknown routes", () => {
    expect(parseDeepLink("xread://unknown/route")).toBeNull();
  });

  it("handles URL-encoded slugs", () => {
    const result = parseDeepLink("xread://paper/my%20paper");
    expect(result).toEqual({
      type: "navigate",
      path: "/paper/my%20paper",
    });
  });

  it("rejects path traversal in paper URL", () => {
    expect(parseDeepLink("xread://paper/../../etc/passwd")).toBeNull();
  });

  it("rejects path traversal in query URL", () => {
    expect(parseDeepLink("xread://query/../etc/passwd")).toBeNull();
  });

  it("rejects path traversal with encoded dots", () => {
    // Even though we don't URL-decode, the literal `..` segment is caught.
    expect(parseDeepLink("xread://paper/..")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// parseXreadFile
// ---------------------------------------------------------------------------

describe("parseXreadFile", () => {
  it("returns an open-workspace action with the file path", () => {
    const result = parseXreadFile("C:\\Users\\me\\workspace\\project.xread");
    expect(result).toEqual({
      type: "open-workspace",
      path: "C:\\Users\\me\\workspace\\project.xread",
    });
  });

  it("works with POSIX paths", () => {
    const result = parseXreadFile("/home/me/workspace/project.xread");
    expect(result).toEqual({
      type: "open-workspace",
      path: "/home/me/workspace/project.xread",
    });
  });
});
