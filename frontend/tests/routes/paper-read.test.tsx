// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/lib/theme";
import { writeWorkspacePath } from "@/lib/workspace";

// Stub pdfjs imports so the route can render without canvas/worker support.
vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({
  default: "blob:mock-worker-url",
}));
const { getDocumentMock } = vi.hoisted(() => ({
  getDocumentMock: vi.fn(),
}));
function installGetDocumentMock() {
  getDocumentMock.mockImplementation(() => ({
    promise: Promise.resolve({
      numPages: 1,
      getPage: () =>
        Promise.resolve({
          getViewport: ({ scale }: { scale: number }) => ({
            width: 100 * scale,
            height: 200 * scale,
          }),
          render: () => ({ promise: Promise.resolve(), cancel: vi.fn() }),
          cleanup: vi.fn(),
          getTextContent: vi.fn(() => Promise.resolve({ items: [] })),
        }),
      destroy: vi.fn(),
    }),
    destroy: vi.fn(),
  }));
}
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: getDocumentMock,
  TextLayer: class TextLayerMock {
    render() {
      return Promise.resolve(undefined);
    }
    cancel() {
      // no-op
    }
  },
  InvalidPDFException: class InvalidPDFException extends Error {
    constructor(msg: string) {
      super(msg);
      this.name = "InvalidPDFException";
    }
  },
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

function mockManifestFetch(entries: unknown[]): Response {
  return new Response(JSON.stringify({ version: 1, entries }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function mockPaperFetch(overrides: Record<string, unknown> = {}): Response {
  return new Response(
    JSON.stringify({
      slug: "alpha-aaaaaaaaaaaa",
      content: "# Alpha",
      frontmatter: { title: "Alpha" },
      sourcePath: "raw/_processed/alpha-aaaaaaaaaaaa.pdf",
      sourceKind: "pdf",
      ...overrides,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

const TRANSLATION_ENTRY = {
  sourceSlug: "alpha-aaaaaaaaaaaa",
  sourceHash: "h1",
  targetLang: "zh",
  model: "anthropic:claude-3-7-sonnet-latest",
  monoPath: "translations/alpha-aaaaaaaaaaaa.mono.pdf",
  dualPath: "translations/alpha-aaaaaaaaaaaa.dual.pdf",
  translatedAt: "2026-05-25T10:00:00Z",
  durationS: 12.5,
  babeldocVersion: "0.6.2",
};

/**
 * The reader keeps all tab panels mounted (forceMount) and hides inactive
 * ones with the `hidden` attribute, so label/text queries would match the
 * hidden panels too. Role queries exclude hidden elements — scope toolbar
 * queries to the single visible tabpanel.
 */
function activePanel(): HTMLElement {
  return screen.getByRole("tabpanel");
}

describe("PaperReadRoute", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    installGetDocumentMock();
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
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(mockManifestFetch([TRANSLATION_ENTRY]))
      .mockResolvedValueOnce(mockPaperFetch());

    renderReader();

    await waitFor(() => {
      const dual = screen.getByRole("tab", { name: /^dual$/i });
      expect(dual.getAttribute("data-state")).toBe("active");
    });
  });

  it("falls back to the Original tab when no translation exists", async () => {
    writeWorkspacePath("/tmp/ws");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(mockManifestFetch([]))
      .mockResolvedValueOnce(mockPaperFetch());

    renderReader();

    await waitFor(() => {
      const original = screen.getByRole("tab", { name: /^original$/i });
      expect(original.getAttribute("data-state")).toBe("active");
    });
    // Dual + Translated are disabled when no entry exists.
    const dual = screen.getByRole("tab", { name: /^dual$/i });
    expect(dual.hasAttribute("disabled") || dual.getAttribute("aria-disabled") === "true").toBe(
      true,
    );
  });

  it("preserves zoom level across tab switches", async () => {
    writeWorkspacePath("/tmp/ws");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(mockManifestFetch([TRANSLATION_ENTRY]))
      .mockResolvedValueOnce(mockPaperFetch());

    renderReader();

    // Wait for the Dual tab to be active (it has all three sources available).
    await waitFor(() => {
      const dual = screen.getByRole("tab", { name: /^dual$/i });
      expect(dual.getAttribute("data-state")).toBe("active");
    });

    // Wait for the page rendering to complete (zoom buttons are disabled while rendering).
    await waitFor(() => {
      expect(within(activePanel()).getByLabelText("Zoom in")).not.toBeDisabled();
    });

    // Zoom in using the toolbar button.
    const zoomInButton = within(activePanel()).getByLabelText("Zoom in");
    await userEvent.click(zoomInButton);

    // Verify zoom level changed.
    await waitFor(() => {
      expect(within(activePanel()).getByLabelText(/zoom level/i)).toHaveTextContent("125%");
    });

    // Switch to the Original tab.
    const originalTab = screen.getByRole("tab", { name: /^original$/i });
    await userEvent.click(originalTab);

    await waitFor(() => {
      expect(originalTab.getAttribute("data-state")).toBe("active");
    });

    // Zoom level should be preserved across tabs.
    expect(within(activePanel()).getByLabelText(/zoom level/i)).toHaveTextContent("125%");
  });

  it("preserves page position when switching tabs", async () => {
    writeWorkspacePath("/tmp/ws");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(mockManifestFetch([TRANSLATION_ENTRY]))
      .mockResolvedValueOnce(mockPaperFetch());

    renderReader();

    // Wait for the Dual tab to be active.
    await waitFor(() => {
      const dual = screen.getByRole("tab", { name: /^dual$/i });
      expect(dual.getAttribute("data-state")).toBe("active");
    });

    // Switch to the Original tab.
    const originalTab = screen.getByRole("tab", { name: /^original$/i });
    await userEvent.click(originalTab);

    await waitFor(() => {
      expect(originalTab.getAttribute("data-state")).toBe("active");
    });

    // The page number input should show page 1 (default).
    const pageInput = within(activePanel()).getByLabelText(/page number/i);
    expect(pageInput).toHaveValue("1");

    // Switch back to Dual tab.
    const dualTab = screen.getByRole("tab", { name: /^dual$/i });
    await userEvent.click(dualTab);

    await waitFor(() => {
      expect(dualTab.getAttribute("data-state")).toBe("active");
    });

    // Page number should still be 1 for the dual tab.
    const pageInputDual = within(activePanel()).getByLabelText(/page number/i);
    expect(pageInputDual).toHaveValue("1");
  });

  it("keeps PDF documents alive across tab switches without reloading", async () => {
    writeWorkspacePath("/tmp/ws");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(mockManifestFetch([TRANSLATION_ENTRY]))
      .mockResolvedValueOnce(mockPaperFetch());

    renderReader();

    await waitFor(() => {
      const dual = screen.getByRole("tab", { name: /^dual$/i });
      expect(dual.getAttribute("data-state")).toBe("active");
    });

    // All three sources exist; each forceMount panel loads its document once.
    await waitFor(() => {
      expect(getDocumentMock).toHaveBeenCalledTimes(3);
    });

    // Switch away and back.
    const originalTab = screen.getByRole("tab", { name: /^original$/i });
    await userEvent.click(originalTab);
    await waitFor(() => {
      expect(originalTab.getAttribute("data-state")).toBe("active");
    });

    const dualTab = screen.getByRole("tab", { name: /^dual$/i });
    await userEvent.click(dualTab);
    await waitFor(() => {
      expect(dualTab.getAttribute("data-state")).toBe("active");
    });

    // No additional getDocument calls — the documents survived the switches.
    expect(getDocumentMock).toHaveBeenCalledTimes(3);
  });

  it("hides inactive reader panels while keeping them mounted", async () => {
    writeWorkspacePath("/tmp/ws");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(mockManifestFetch([TRANSLATION_ENTRY]))
      .mockResolvedValueOnce(mockPaperFetch());

    const { container } = renderReader();

    await waitFor(() => {
      const dual = screen.getByRole("tab", { name: /^dual$/i });
      expect(dual.getAttribute("data-state")).toBe("active");
    });

    const panels = container.querySelectorAll("[role='tabpanel']");
    expect(panels).toHaveLength(3);
    const hiddenPanels = Array.from(panels).filter((panel) => panel.hasAttribute("hidden"));
    expect(hiddenPanels).toHaveLength(2);
    const visiblePanel = Array.from(panels).find((panel) => !panel.hasAttribute("hidden"));
    expect(visiblePanel?.getAttribute("data-state")).toBe("active");
  });

  it("uses the canonical sourcePath for the original PDF URL", async () => {
    writeWorkspacePath("C:/Users/me/XRead Workspace");
    const mockFetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(mockManifestFetch([]))
      .mockResolvedValueOnce(mockPaperFetch({ sourcePath: "raw/_processed/alpha archived.pdf" }));

    renderReader();

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /^original$/i }).getAttribute("data-state")).toBe(
        "active",
      );
    });

    await waitFor(() => {
      expect(getDocumentMock).toHaveBeenCalled();
    });
    expect(mockFetch).toHaveBeenCalledTimes(2);
    const firstPdfCall = getDocumentMock.mock.calls[0];
    expect(firstPdfCall?.[0]).toMatchObject({
      url: "/api/workspaces/file?workspacePath=C%3A%2FUsers%2Fme%2FXRead+Workspace&path=raw%2F_processed%2Falpha+archived.pdf",
    });
  });

  it("shows a no-PDF state and disables Translate for non-PDF sources", async () => {
    writeWorkspacePath("/tmp/ws");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(mockManifestFetch([]))
      .mockResolvedValueOnce(
        mockPaperFetch({ sourcePath: "raw/_processed/notes.docx", sourceKind: "office" }),
      );

    renderReader();

    expect(await screen.findByText(/no pdf source is available/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /translate/i })).toBeDisabled();
  });
});
