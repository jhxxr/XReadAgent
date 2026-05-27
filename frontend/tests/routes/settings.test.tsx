// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "@/lib/theme";
import { SettingsRoute } from "@/routes/settings";

vi.mock("@/lib/api", () => ({
  getSettings: vi.fn().mockResolvedValue({
    model: "openai:gpt-4o",
    workspacePath: "/tmp/ws",
  }),
  putSettings: vi.fn().mockResolvedValue({
    model: "openai:gpt-4o",
    workspacePath: "/tmp/ws",
  }),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });

  const rootRoute = createRootRoute();
  const settingsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/settings",
    component: SettingsRoute,
  });
  const router = createRouter({
    routeTree: rootRoute.addChildren([settingsRoute]),
    history: createMemoryHistory({ initialEntries: ["/settings"] }),
  });

  return render(
    <ThemeProvider defaultTheme="light">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

describe("Settings route", () => {
  it("renders the settings page with form fields after loading", async () => {
    renderSettings();

    // Wait for the form to appear (query must resolve first).
    expect(await screen.findByLabelText(/model/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/workspace path/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save settings/i })).toBeInTheDocument();
  });
});
