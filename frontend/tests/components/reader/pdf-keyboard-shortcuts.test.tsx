// SPDX-License-Identifier: AGPL-3.0-or-later
import { act, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the worker URL import — Vitest needs an explicit resolver since `?url`
// is a Vite-specific suffix.
vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({
  default: "blob:mock-worker-url",
}));

// Mock pdfjs-dist itself so we can drive the render lifecycle without a real
// worker / canvas backend (jsdom has neither).
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: vi.fn<(...args: unknown[]) => unknown>(),
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

import { PdfViewer } from "@/components/reader/pdf-viewer";
import type { PdfToolbarProps } from "@/components/reader/pdf-toolbar";
import { PdfToolbar, ZOOM_DEFAULT, ZOOM_STEP } from "@/components/reader/pdf-toolbar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { getDocument } from "pdfjs-dist";

const mockGetDocument = getDocument as unknown as ReturnType<typeof vi.fn>;

const mockRenderPromise = vi.fn(() => Promise.resolve(undefined));
const mockGetViewport = vi.fn(({ scale }: { scale: number }) => ({
  width: 100 * scale,
  height: 200 * scale,
}));
function makePage(pageNumber: number) {
  return {
    pageNumber,
    getViewport: mockGetViewport,
    render: () => ({ promise: mockRenderPromise(), cancel: vi.fn() }),
    cleanup: vi.fn(),
    getTextContent: vi.fn(() => Promise.resolve({ items: [] })),
  };
}

function setupDocument(numPages: number) {
  mockGetDocument.mockImplementation(() => {
    const task = {
      promise: Promise.resolve({
        numPages,
        getPage: (n: number) => Promise.resolve(makePage(n)),
        destroy: vi.fn(),
      }),
      destroy: vi.fn(),
      onProgress: null as (() => void) | null,
    };
    return task;
  });
}

function renderWithTooltip(ui: React.ReactElement) {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
}

describe("PdfViewer keyboard shortcuts", () => {
  beforeEach(() => {
    window.matchMedia = (query: string) =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as MediaQueryList;
    mockGetDocument.mockReset();
    mockRenderPromise.mockClear();
    HTMLCanvasElement.prototype.getContext = vi.fn(
      () => ({}) as unknown as CanvasRenderingContext2D,
    ) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("zooms in with Ctrl+=", async () => {
    const onZoomChange = vi.fn();
    setupDocument(5);
    renderWithTooltip(
      <PdfViewer
        url="/mock.pdf"
        mode="single"
        zoom={ZOOM_DEFAULT}
        onZoomChange={onZoomChange}
        renderToolbar={(props: PdfToolbarProps) => <PdfToolbar {...props} />}
      />,
    );

    await waitFor(() => {
      const viewer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
      expect(viewer).not.toBeNull();
    });

    const scrollContainer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
    act(() => {
      scrollContainer?.dispatchEvent(
        new KeyboardEvent("keydown", { key: "=", ctrlKey: true, bubbles: true }),
      );
    });

    expect(onZoomChange).toHaveBeenCalledWith(ZOOM_DEFAULT + ZOOM_STEP);
  });

  it("zooms out with Ctrl+-", async () => {
    const onZoomChange = vi.fn();
    setupDocument(5);
    renderWithTooltip(
      <PdfViewer
        url="/mock.pdf"
        mode="single"
        zoom={ZOOM_DEFAULT}
        onZoomChange={onZoomChange}
        renderToolbar={(props: PdfToolbarProps) => <PdfToolbar {...props} />}
      />,
    );

    await waitFor(() => {
      const viewer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
      expect(viewer).not.toBeNull();
    });

    const scrollContainer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
    act(() => {
      scrollContainer?.dispatchEvent(
        new KeyboardEvent("keydown", { key: "-", ctrlKey: true, bubbles: true }),
      );
    });

    expect(onZoomChange).toHaveBeenCalledWith(ZOOM_DEFAULT - ZOOM_STEP);
  });

  it("resets zoom with Ctrl+0", async () => {
    const onZoomChange = vi.fn();
    setupDocument(5);
    renderWithTooltip(
      <PdfViewer
        url="/mock.pdf"
        mode="single"
        zoom={200}
        onZoomChange={onZoomChange}
        renderToolbar={(props: PdfToolbarProps) => <PdfToolbar {...props} />}
      />,
    );

    await waitFor(() => {
      const viewer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
      expect(viewer).not.toBeNull();
    });

    const scrollContainer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
    act(() => {
      scrollContainer?.dispatchEvent(
        new KeyboardEvent("keydown", { key: "0", ctrlKey: true, bubbles: true }),
      );
    });

    expect(onZoomChange).toHaveBeenCalledWith(ZOOM_DEFAULT);
  });

  it("navigates to next page with PageDown", async () => {
    const onNavigateToPage = vi.fn();
    setupDocument(5);
    renderWithTooltip(
      <PdfViewer
        url="/mock.pdf"
        mode="single"
        zoom={100}
        onZoomChange={vi.fn()}
        currentPage={2}
        onNavigateToPage={onNavigateToPage}
        renderToolbar={(props: PdfToolbarProps) => <PdfToolbar {...props} />}
      />,
    );

    await waitFor(() => {
      const viewer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
      expect(viewer).not.toBeNull();
    });

    const scrollContainer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
    act(() => {
      scrollContainer?.dispatchEvent(
        new KeyboardEvent("keydown", { key: "PageDown", bubbles: true }),
      );
    });

    expect(onNavigateToPage).toHaveBeenCalledWith(3);
  });

  it("navigates to previous page with PageUp", async () => {
    const onNavigateToPage = vi.fn();
    setupDocument(5);
    renderWithTooltip(
      <PdfViewer
        url="/mock.pdf"
        mode="single"
        zoom={100}
        onZoomChange={vi.fn()}
        currentPage={3}
        onNavigateToPage={onNavigateToPage}
        renderToolbar={(props: PdfToolbarProps) => <PdfToolbar {...props} />}
      />,
    );

    await waitFor(() => {
      const viewer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
      expect(viewer).not.toBeNull();
    });

    const scrollContainer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
    act(() => {
      scrollContainer?.dispatchEvent(
        new KeyboardEvent("keydown", { key: "PageUp", bubbles: true }),
      );
    });

    expect(onNavigateToPage).toHaveBeenCalledWith(2);
  });

  it("navigates to first page with Home", async () => {
    const onNavigateToPage = vi.fn();
    setupDocument(5);
    renderWithTooltip(
      <PdfViewer
        url="/mock.pdf"
        mode="single"
        zoom={100}
        onZoomChange={vi.fn()}
        currentPage={3}
        onNavigateToPage={onNavigateToPage}
        renderToolbar={(props: PdfToolbarProps) => <PdfToolbar {...props} />}
      />,
    );

    await waitFor(() => {
      const viewer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
      expect(viewer).not.toBeNull();
    });

    const scrollContainer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
    act(() => {
      scrollContainer?.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Home", bubbles: true }),
      );
    });

    expect(onNavigateToPage).toHaveBeenCalledWith(1);
  });

  it("navigates to last page with End", async () => {
    const onNavigateToPage = vi.fn();
    setupDocument(5);
    renderWithTooltip(
      <PdfViewer
        url="/mock.pdf"
        mode="single"
        zoom={100}
        onZoomChange={vi.fn()}
        currentPage={3}
        onNavigateToPage={onNavigateToPage}
        renderToolbar={(props: PdfToolbarProps) => <PdfToolbar {...props} />}
      />,
    );

    await waitFor(() => {
      const viewer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
      expect(viewer).not.toBeNull();
    });

    const scrollContainer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
    act(() => {
      scrollContainer?.dispatchEvent(
        new KeyboardEvent("keydown", { key: "End", bubbles: true }),
      );
    });

    expect(onNavigateToPage).toHaveBeenCalledWith(5);
  });
});