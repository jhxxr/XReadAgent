// SPDX-License-Identifier: AGPL-3.0-or-later
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppSidebar } from "@/components/shell/app-sidebar";
import { ThemeProvider } from "@/lib/theme";

/** Re-install the matchMedia stub that afterEach/restoreAllMocks tears down. */
function stubMatchMedia() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function renderSidebar(initialPath = "/workspace") {
  const rootRoute = createRootRoute({
    component: function SidebarLayout() {
      return (
        <div>
          <AppSidebar />
          <main>
            <Outlet />
          </main>
        </div>
      );
    },
  });
  const workspaceRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/workspace",
    component: () => <div>workspace content</div>,
  });
  const paperRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/paper",
    component: () => <div>paper content</div>,
  });
  const queriesRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/queries",
    component: () => <div>queries content</div>,
  });
  const settingsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/settings",
    component: () => <div>settings content</div>,
  });

  const router = createRouter({
    routeTree: rootRoute.addChildren([
      workspaceRoute,
      paperRoute,
      queriesRoute,
      settingsRoute,
    ]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  });

  return render(
    <ThemeProvider defaultTheme="light">
      <RouterProvider router={router} />
    </ThemeProvider>,
  );
}

describe("AppSidebar", () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubMatchMedia();
  });

  it("renders the XReadAgent brand label", async () => {
    renderSidebar();

    expect(await screen.findByText("XReadAgent")).toBeInTheDocument();
  });

  it("renders all navigation links", async () => {
    renderSidebar();

    expect(await screen.findByRole("link", { name: /workspace/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /papers/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /queries/i })).toBeInTheDocument();
  });

  it("renders the Settings link", async () => {
    renderSidebar();

    expect(await screen.findByRole("link", { name: /settings/i })).toBeInTheDocument();
  });

  it("renders the workspace switcher label", async () => {
    renderSidebar();

    // The workspace switcher is a button with data-slot="workspace-switcher"
    // that contains a small uppercase "Workspace" label.
    const switcher = await screen.findByRole("button", { name: /workspace/i });
    expect(switcher).toHaveAttribute("data-slot", "workspace-switcher");
    expect(switcher).toHaveTextContent("Workspace");
  });

  it("renders the default workspace name", async () => {
    renderSidebar();

    expect(await screen.findByText("Default")).toBeInTheDocument();
  });
});