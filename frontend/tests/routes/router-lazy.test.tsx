// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Guards the lazy route-loading setup in `src/router.tsx`: the home route
 * renders eagerly, and navigating to a lazily-loaded route resolves its
 * dynamically-imported component.
 */
import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppProviders } from "@/app";
import { RouterProvider } from "@tanstack/react-router";

const api = vi.hoisted(() => ({
  getConcepts: vi.fn(),
  getHealthz: vi.fn(),
  getPapers: vi.fn(),
  getQueries: vi.fn(),
  getSettings: vi.fn(),
  postIngest: vi.fn(),
  postQuery: vi.fn(),
  putSettings: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

describe("router lazy routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    api.getHealthz.mockResolvedValue({ status: "ok", version: "0.0.0" });
    api.getSettings.mockResolvedValue({
      model: "anthropic:claude",
      workspacePath: "",
      language: "en",
    });
    api.getPapers.mockResolvedValue([]);
    api.getConcepts.mockResolvedValue([]);
    api.getQueries.mockResolvedValue([]);
  });

  it("renders the eager workspace route and lazily loads the queries route", async () => {
    // Import inside the test so the module-level router picks up the api mock.
    const { router } = await import("@/router");

    render(
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>,
    );

    // `/` redirects to the eagerly-loaded workspace route.
    expect(await screen.findByText("Default Workspace")).toBeInTheDocument();

    // Navigating triggers the dynamic import of the queries route chunk.
    await act(async () => {
      await router.navigate({ to: "/queries" });
    });

    expect(await screen.findByText("Query archive")).toBeInTheDocument();
  });
});
