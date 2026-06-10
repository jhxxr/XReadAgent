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
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "@/lib/i18n";
import { ThemeProvider } from "@/lib/theme";
import { SettingsRoute } from "@/routes/settings";

const { getSettings, putSettings } = vi.hoisted(() => ({
  getSettings: vi.fn(),
  putSettings: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getSettings,
  putSettings,
}));

afterEach(() => {
  vi.clearAllMocks();
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
        <LanguageProvider>
          <RouterProvider router={router} />
        </LanguageProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

describe("Settings route", () => {
  beforeEach(() => {
    getSettings.mockResolvedValue({
      model: "openai:gpt-4o",
      workspacePath: "/tmp/ws",
      language: "zh",
    });
    putSettings.mockImplementation((req: { language?: "en" | "zh" }) => ({
      model: "openai:gpt-4o",
      workspacePath: "/tmp/ws",
      language: req.language ?? "zh",
    }));
  });

  it("renders the settings page with form fields after loading", async () => {
    renderSettings();

    // Wait for the form to appear (query must resolve first).
    expect(await screen.findByRole("textbox", { name: /^模型$/ })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /工作区路径/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /保存设置/ })).toBeInTheDocument();
  });

  it("switches the settings UI language and persists the choice", async () => {
    const user = userEvent.setup();
    renderSettings();

    await user.click(await screen.findByRole("tab", { name: /语言/ }));
    await user.click(screen.getByRole("radio", { name: /English/i }));

    expect(putSettings).toHaveBeenCalledWith({ language: "en" });
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /General/i })).toBeInTheDocument();
  });
});
