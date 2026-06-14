// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentsTab } from "@/components/workspace/documents-tab";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/lib/theme";

const { getSources, runIngestJob } = vi.hoisted(() => ({
  getSources: vi.fn(),
  runIngestJob: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ getSources, postBuildWiki: vi.fn() }));
vi.mock("@/lib/ingest-job", () => ({ runIngestJob }));
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), loading: vi.fn(), success: vi.fn() },
}));

function renderTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return render(
    <ThemeProvider defaultTheme="light">
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <DocumentsTab workspacePath="/tmp/ws" />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

describe("DocumentsTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    runIngestJob.mockResolvedValue({ type: "finish", title: "Doc", slug: "d", cache_hit: false });
  });

  it("lists registered documents with status", async () => {
    getSources.mockResolvedValue([
      {
        slug: "built",
        title: "Built Doc",
        kind: "pdf",
        sourcePath: "raw/_processed/built.pdf",
        ingestedAt: "2026-06-14T00:00:00Z",
        pageCount: 2,
        wikiBuilt: true,
        translated: true,
      },
      {
        slug: "fresh",
        title: "Fresh Doc",
        kind: "pdf",
        sourcePath: "raw/_processed/fresh.pdf",
        ingestedAt: "2026-06-14T00:00:00Z",
        pageCount: 1,
        wikiBuilt: false,
        translated: false,
      },
    ]);
    renderTab();

    expect(await screen.findByText("Built Doc")).toBeInTheDocument();
    expect(screen.getByText("Fresh Doc")).toBeInTheDocument();
    expect(screen.getByText(/wiki built/i)).toBeInTheDocument();
    expect(screen.getByText(/registered/i)).toBeInTheDocument();
  });

  it("shows Build Wiki only for unbuilt documents and triggers a build", async () => {
    getSources.mockResolvedValue([
      {
        slug: "fresh",
        title: "Fresh Doc",
        kind: "pdf",
        sourcePath: "raw/_processed/fresh.pdf",
        ingestedAt: "2026-06-14T00:00:00Z",
        pageCount: 1,
        wikiBuilt: false,
        translated: false,
      },
    ]);
    const user = userEvent.setup();
    renderTab();

    const buildBtn = await screen.findByRole("button", { name: /build wiki/i });
    await user.click(buildBtn);
    expect(runIngestJob).toHaveBeenCalledTimes(1);
  });

  it("hides Build Wiki for already-built documents", async () => {
    getSources.mockResolvedValue([
      {
        slug: "built",
        title: "Built Doc",
        kind: "pdf",
        sourcePath: "raw/_processed/built.pdf",
        ingestedAt: "2026-06-14T00:00:00Z",
        pageCount: 2,
        wikiBuilt: true,
        translated: false,
      },
    ]);
    renderTab();

    await screen.findByText("Built Doc");
    expect(screen.queryByRole("button", { name: /build wiki/i })).not.toBeInTheDocument();
  });

  it("renders an empty hint when there are no documents", async () => {
    getSources.mockResolvedValue([]);
    renderTab();
    expect(await screen.findByText(/no documents yet/i)).toBeInTheDocument();
  });
});
