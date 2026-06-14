// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppSidebar } from "@/components/shell/app-sidebar";
import { LanguageProvider } from "@/lib/i18n";
import { ThemeProvider } from "@/lib/theme";

const { getSettings, postIngest, putSettings } = vi.hoisted(() => ({
  getSettings: vi.fn(),
  postIngest: vi.fn(),
  putSettings: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getSettings,
  postIngest,
  putSettings,
  createWorkspace: vi.fn(),
}));

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
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });

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
    routeTree: rootRoute.addChildren([workspaceRoute, paperRoute, queriesRoute, settingsRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
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

function installMockElectronAPI(): NonNullable<Window["electronAPI"]> {
  const api: NonNullable<Window["electronAPI"]> = {
    platform: "win32",
    isPackaged: true,
    getSidecarPort: vi.fn(() => 8765),
    onSidecarReady: vi.fn(),
    onSidecarStatus: vi.fn(),
    onSplashStatus: vi.fn(),
    onSplashError: vi.fn(),
    sendSplashRetry: vi.fn(),
    showOpenFileDialog: vi.fn().mockResolvedValue([]),
    getPathForFile: vi.fn(() => "/tmp/paper.pdf"),
    showNotification: vi.fn(),
    getSidecarStatus: vi.fn().mockResolvedValue({
      status: "running",
      pid: 1,
      port: 8765,
      startedAt: "2026-06-03T00:00:00Z",
      restartCount: 0,
    }),
    getSidecarLogs: vi.fn().mockResolvedValue([]),
    restartSidecar: vi.fn().mockResolvedValue(undefined),
    onSidecarRestarting: vi.fn(),
    getSidecarRestartInfo: vi.fn().mockResolvedValue(null),
    onDeepLink: vi.fn(),
    onOpenWorkspace: vi.fn(),
    onMenuNavigate: vi.fn(),
    listWorkspaces: vi.fn(() => Promise.resolve([])),
    createWorkspace: vi.fn(),
    renameWorkspace: vi.fn(),
    deleteWorkspace: vi.fn(() => Promise.resolve()),
    touchWorkspace: vi.fn(() => Promise.resolve()),
    revealWorkspace: vi.fn(() => Promise.resolve()),
  };
  Object.defineProperty(window, "electronAPI", {
    configurable: true,
    value: api,
    writable: true,
  });
  return api;
}

describe("AppSidebar", () => {
  beforeEach(() => {
    window.localStorage.clear();
    Object.defineProperty(window, "electronAPI", {
      configurable: true,
      value: undefined,
      writable: true,
    });
    getSettings.mockResolvedValue({ model: "", workspacePath: "", language: "zh" });
    putSettings.mockResolvedValue({ model: "", workspacePath: "", language: "zh" });
    postIngest.mockResolvedValue({ title: "Paper" });
    stubMatchMedia();
  });

  it("renders the XReadAgent brand label", async () => {
    renderSidebar();

    expect(await screen.findByText("XReadAgent")).toBeInTheDocument();
  });

  it("renders all navigation links", async () => {
    renderSidebar();

    expect(await screen.findByRole("link", { name: /工作区/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /论文/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /问答/ })).toBeInTheDocument();
  });

  it("renders the Settings link", async () => {
    renderSidebar();

    expect(await screen.findByRole("link", { name: /设置/ })).toBeInTheDocument();
  });

  it("renders the workspace switcher label", async () => {
    renderSidebar();

    // The workspace switcher is a button with data-slot="workspace-switcher".
    const switcher = await screen.findByRole("button", { name: /工作区/i });
    expect(switcher).toHaveAttribute("data-slot", "workspace-switcher");
    expect(switcher).toHaveTextContent("工作区");
  });

  it("renders the default workspace name", async () => {
    renderSidebar();

    expect(await screen.findByText("默认")).toBeInTheDocument();
  });

  it("opens the workspace manager from the switcher", async () => {
    installMockElectronAPI();
    const user = userEvent.setup();
    renderSidebar();

    await user.click(await screen.findByRole("button", { name: /工作区 默认/i }));

    // The managed workspace manager dialog opens (no native folder picker).
    expect(await screen.findByPlaceholderText(/new workspace name/i)).toBeInTheDocument();
  });
});
