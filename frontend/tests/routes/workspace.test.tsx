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
}));

vi.mock("@/lib/ingest-job", () => ({ runIngestJob }));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    loading: vi.fn(),
    success: vi.fn(),
  },
}));

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
  // The tab panels render Links to these routes — register stub destinations
  // so TanStack Router doesn't error on the `to` props.
  const paperRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/paper/$slug",
    component: () => <div>paper stub</div>,
  });
  const conceptRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/concept/$slug",
    component: () => <div>concept stub</div>,
  });
  const queryRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/query/$topic/$slug",
    component: () => <div>query stub</div>,
  });
  const router = createRouter({
    routeTree: rootRoute.addChildren([workspaceRoute, paperRoute, conceptRoute, queryRoute]),
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

describe("Workspace tabs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    writeWorkspacePath("/tmp/ws");
    getPapers.mockResolvedValue([
      {
        slug: "alpha-aaaaaaaaaaaa",
        title: "Alpha Paper",
        authors: ["Ada"],
        year: 2026,
        ingestedAt: "2026-06-01T00:00:00Z",
      },
    ]);
    getConcepts.mockResolvedValue([
      {
        slug: "attention",
        title: "Attention Mechanism",
        aliases: [],
        paperCount: 2,
      },
    ]);
    getQueries.mockResolvedValue([
      {
        id: "transformers/why-attention",
        topic: "transformers",
        question: "Why does attention work?",
        archivedAt: "2026-06-02T00:00:00Z",
      },
    ]);
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

  it("shows the documents tab by default", async () => {
    renderWorkspace();
    expect(await screen.findByText(/no documents yet/i)).toBeInTheDocument();
    expect(screen.queryByText("Alpha Paper")).not.toBeInTheDocument();
  });

  it("switches to the Papers tab when its header tab is clicked", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await screen.findByText(/no documents yet/i);

    await user.click(screen.getByRole("tab", { name: /papers/i }));

    expect(await screen.findByText("Alpha Paper")).toBeInTheDocument();
  });

  it("switches the content area when the Concepts header tab is clicked", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await screen.findByText(/no documents yet/i);

    await user.click(screen.getByRole("tab", { name: /concepts/i }));

    expect(await screen.findByText("Attention Mechanism")).toBeInTheDocument();
    expect(screen.queryByText("Alpha Paper")).not.toBeInTheDocument();
  });

  it("switches the content area when the Queries header tab is clicked", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await screen.findByText(/no documents yet/i);

    await user.click(screen.getByRole("tab", { name: /queries/i }));

    expect(await screen.findByText("Why does attention work?")).toBeInTheDocument();
    expect(screen.queryByText("Alpha Paper")).not.toBeInTheDocument();
  });

  it("returns to the papers list when Papers is re-selected", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await screen.findByText(/no documents yet/i);

    await user.click(screen.getByRole("tab", { name: /concepts/i }));
    await screen.findByText("Attention Mechanism");

    await user.click(screen.getByRole("tab", { name: /papers/i }));
    expect(await screen.findByText("Alpha Paper")).toBeInTheDocument();
  });
});
