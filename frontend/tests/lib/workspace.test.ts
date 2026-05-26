// SPDX-License-Identifier: AGPL-3.0-or-later
import { beforeEach, describe, expect, it } from "vitest";

import { readWorkspacePath, writeWorkspacePath } from "@/lib/workspace";

describe("workspace path persistence", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns an empty string when no path is set", () => {
    expect(readWorkspacePath()).toBe("");
  });

  it("round-trips through localStorage", () => {
    writeWorkspacePath("/tmp/ws");
    expect(readWorkspacePath()).toBe("/tmp/ws");
  });

  it("returns an empty string when localStorage holds an empty string", () => {
    writeWorkspacePath("");
    expect(readWorkspacePath()).toBe("");
  });
});
