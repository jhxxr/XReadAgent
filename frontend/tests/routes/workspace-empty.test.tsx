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

const { getConcepts, getPapers, getQueries, getSources, runIngestJob } = vi.hoisted(() => ({
  getConcepts: vi.fn(),
  getPapers: vi.fn(),
  getQueries: vi.fn(),
  getSources: vi.fn(),
  runIngestJob: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getConcepts,
  getPapers,
  getQueries,
  getSources,
  createWorkspace: vi.fn(() =>
    Promise.resolve({ workspacePath: "/data/ws", title: "WS", created: true }),
  ),
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
    getSources.mockResolvedValue([]);
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
    expect(screen.getByRole("button", { name: /new workspace/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /import paper/i })).toBeInTheDocument();
    expect(screen.getByText(/what is an llm wiki/i)).toBeInTheDocument();
  });

  it("opens the workspace manager from the empty state", async () => {
    installMockElectronAPI();
    const user = userEvent.setup();
    renderWorkspace();

    await user.click(await screen.findByRole("button", { name: /new workspace/i }));

    // The managed workspace manager dialog opens (no native folder picker).
    expect(await screen.findByPlaceholderText(/new workspace name/i)).toBeInTheDocument();
  });

  it("imports a selected document when a workspace is active", async () => {
    const api = installMockElectronAPI();
    const user = userEvent.setup();
    writeWorkspacePath("/tmp/ws");
    renderWorkspace();

    // With an active workspace the Documents tab is shown; the header "Import"
    // button drives the same convert-only register flow.
    await user.click(await screen.findByRole("button", { name: "Import" }));

    expect(api.showOpenFileDialog).toHaveBeenCalledWith("Import Paper");
    expect(runIngestJob).toHaveBeenCalledWith(
      {
        workspacePath: "/tmp/ws",
        filePath: "/tmp/paper.pdf",
      },
      expect.anything(),
    );
  });

  it("refuses to import without an active workspace", async () => {
    const api = installMockElectronAPI();
    const user = userEvent.setup();
    renderWorkspace();

    await user.click(await screen.findByRole("button", { name: /import paper/i }));

    // No active workspace → no file dialog, no ingest; user is told to pick one.
    expect(api.showOpenFileDialog).not.toHaveBeenCalled();
    expect(runIngestJob).not.toHaveBeenCalled();
  });
});
