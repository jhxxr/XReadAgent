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
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/lib/theme";
import { writeWorkspacePath } from "@/lib/workspace";
import { WorkspaceRoute } from "@/routes/workspace";

const { getConcepts, getPapers, getQueries, runIngestJob } = vi.hoisted(() => ({
  getConcepts: vi.fn(),
  getPapers: vi.fn(),
  getQueries: vi.fn(),
  runIngestJob: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getConcepts,
  getPapers,
  getQueries,
}));

vi.mock("@/lib/ingest-job", () => ({ runIngestJob }));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    loading: vi.fn(),
    success: vi.fn(),
  },
}));

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
    showOpenFolderDialog: vi.fn().mockResolvedValue(["/tmp/ws"]),
    showOpenFileDialog: vi.fn().mockResolvedValue(["/tmp/paper.pdf"]),
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
  };
  Object.defineProperty(window, "electronAPI", {
    configurable: true,
    value: api,
    writable: true,
  });
  return api;
}

function renderWorkspace() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });

  const rootRoute = createRootRoute();
  const workspaceRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/workspace",
    component: WorkspaceRoute,
  });
  const router = createRouter({
    routeTree: rootRoute.addChildren([workspaceRoute]),
    history: createMemoryHistory({ initialEntries: ["/workspace"] }),
  });

  return render(
    <ThemeProvider defaultTheme="light">
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <RouterProvider router={router} />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

describe("Workspace empty state", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, "electronAPI", {
      configurable: true,
      value: undefined,
      writable: true,
    });
    getPapers.mockResolvedValue([]);
    getConcepts.mockResolvedValue([]);
    getQueries.mockResolvedValue([]);
    runIngestJob.mockResolvedValue({
      type: "finish",
      slug: "paper",
      title: "Paper",
      cache_hit: false,
      files_touched: [],
      duration_s: 1,
      ts: "2026-06-11T00:00:00Z",
    });
  });

  it("renders the empty-state heading and import button", async () => {
    renderWorkspace();
    expect(await screen.findByRole("heading", { name: /your wiki is empty/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open workspace/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /import paper/i })).toBeInTheDocument();
    expect(screen.getByText(/what is an llm wiki/i)).toBeInTheDocument();
  });

  it("opens the native workspace picker from the empty state", async () => {
    const api = installMockElectronAPI();
    const user = userEvent.setup();
    renderWorkspace();

    await user.click(await screen.findByRole("button", { name: /open workspace/i }));

    expect(api.showOpenFolderDialog).toHaveBeenCalledWith("Open Workspace");
    expect(window.localStorage.getItem("xreadagent.workspacePath")).toBe("/tmp/ws");
  });

  it("imports a selected document when a workspace is active", async () => {
    const api = installMockElectronAPI();
    const user = userEvent.setup();
    writeWorkspacePath("/tmp/ws");
    renderWorkspace();

    await user.click(await screen.findByRole("button", { name: /import paper/i }));

    expect(api.showOpenFileDialog).toHaveBeenCalledWith("Import Paper");
    expect(runIngestJob).toHaveBeenCalledWith(
      {
        workspacePath: "/tmp/ws",
        filePath: "/tmp/paper.pdf",
      },
      expect.anything(),
    );
  });

  it("chooses a workspace first when importing without an active workspace", async () => {
    const api = installMockElectronAPI();
    const user = userEvent.setup();
    renderWorkspace();

    await user.click(await screen.findByRole("button", { name: /import paper/i }));

    expect(api.showOpenFolderDialog).toHaveBeenCalledWith("Open Workspace");
    expect(api.showOpenFileDialog).toHaveBeenCalledWith("Import Paper");
    expect(runIngestJob).toHaveBeenCalledWith(
      {
        workspacePath: "/tmp/ws",
        filePath: "/tmp/paper.pdf",
      },
      expect.anything(),
    );
  });
});
