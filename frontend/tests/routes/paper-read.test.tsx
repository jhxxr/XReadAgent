// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/lib/theme";
import { writeWorkspacePath } from "@/lib/workspace";

// Stub pdfjs imports so the route can render without canvas/worker support.
vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({
  default: "blob:mock-worker-url",
}));
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: () => ({
    promise: Promise.resolve({
      numPages: 1,
      getPage: () =>
        Promise.resolve({
          getViewport: ({ scale }: { scale: number }) => ({
            width: 100 * scale,
            height: 200 * scale,
          }),
          render: () => ({ promise: Promise.resolve() }),
          cleanup: vi.fn(),
        }),
      destroy: vi.fn(),
    }),
    destroy: vi.fn(),
  }),
}));

import { PaperReadRoute } from "@/routes/paper-read";

function renderReader(slug = "alpha-aaaaaaaaaaaa") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  const rootRoute = createRootRoute();
  const readRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/paper/$slug/read",
    component: PaperReadRoute,
  });
  // The component renders an internal `Link to="/paper/$slug"` button —
  // register a stub destination so TanStack doesn't error on the `to`.
  const paperRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/paper/$slug",
    component: () => <div>paper stub</div>,
  });

  const router = createRouter({
    routeTree: rootRoute.addChildren([readRoute, paperRoute]),
    history: createMemoryHistory({ initialEntries: [`/paper/${slug}/read`] }),
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

describe("PaperReadRoute", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    // restoreAllMocks resets the vi.fn() impl that backs the matchMedia
    // stub installed in tests/setup.ts. Re-install it so ThemeProvider can
    // run without crashing.
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
    HTMLCanvasElement.prototype.getContext = vi.fn(
      () => ({}) as unknown as CanvasRenderingContext2D,
    ) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the no-workspace state when localStorage is empty", async () => {
    renderReader();
    expect(await screen.findByText(/no workspace selected/i)).toBeInTheDocument();
  });

  it("defaults to the Dual tab when a dual translation exists", async () => {
    writeWorkspacePath("/tmp/ws");
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          version: 1,
          entries: [
            {
              sourceSlug: "alpha-aaaaaaaaaaaa",
              sourceHash: "h1",
              targetLang: "zh",
              model: "anthropic:claude-3-7-sonnet-latest",
              monoPath: "translations/alpha-aaaaaaaaaaaa.mono.pdf",
              dualPath: "translations/alpha-aaaaaaaaaaaa.dual.pdf",
              translatedAt: "2026-05-25T10:00:00Z",
              durationS: 12.5,
              babeldocVersion: "0.6.2",
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    renderReader();

    await waitFor(() => {
      const dual = screen.getByRole("tab", { name: /^dual$/i });
      expect(dual.getAttribute("data-state")).toBe("active");
    });
  });

  it("falls back to the Original tab when no translation exists", async () => {
    writeWorkspacePath("/tmp/ws");
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ version: 1, entries: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    renderReader();

    await waitFor(() => {
      const original = screen.getByRole("tab", { name: /^original$/i });
      expect(original.getAttribute("data-state")).toBe("active");
    });
    // Dual + Translated are disabled when no entry exists.
    const dual = screen.getByRole("tab", { name: /^dual$/i });
    expect(dual.hasAttribute("disabled") || dual.getAttribute("aria-disabled") === "true")
      .toBe(true);
  });
});
