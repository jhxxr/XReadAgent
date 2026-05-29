// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the worker URL import.
vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({
  default: "blob:mock-worker-url",
}));

const mockGetViewport = vi.fn(({ scale }: { scale: number }) => ({
  width: 100 * scale,
  height: 200 * scale,
}));
const mockCleanup = vi.fn();
const mockRenderPromise = vi.fn(() => Promise.resolve(undefined));
const mockCancel = vi.fn();

function makePage(pageNumber: number) {
  return {
    pageNumber,
    getViewport: mockGetViewport,
    render: () => ({ promise: mockRenderPromise(), cancel: mockCancel }),
    cleanup: mockCleanup,
  };
}

function makeDoc(numPages: number) {
  return {
    numPages,
    getPage: (n: number) => Promise.resolve(makePage(n)),
    destroy: vi.fn(),
  };
}

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: vi.fn(),
  InvalidPDFException: class InvalidPDFException extends Error {
    constructor(msg: string) {
      super(msg);
      this.name = "InvalidPDFException";
    }
  },
}));

import { usePageRenderer } from "@/lib/use-page-renderer";
import type { PDFDocumentProxy } from "pdfjs-dist";

// A probe component that exposes the hook result for assertions.
function PageRendererProbe({
  doc,
  pageNumber,
  pageWidth,
}: {
  doc: PDFDocumentProxy;
  pageNumber: number;
  pageWidth: number;
}) {
  const result = usePageRenderer(doc, pageNumber, pageWidth);
  return (
    <div data-testid="result">
      <span data-testid="isLoading">{result.isLoading ? "true" : "false"}</span>
      <span data-testid="error">{result.error ?? "none"}</span>
      <span data-testid="pageHeight">{result.pageHeight.toString()}</span>
      <canvas ref={result.canvasRef} data-testid="canvas" />
    </div>
  );
}

describe("usePageRenderer", () => {
  beforeEach(() => {
    // setup.ts stub is wiped by restoreAllMocks; re-install it.
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
    mockGetViewport.mockClear();
    mockCleanup.mockClear();
    mockRenderPromise.mockClear();
    mockCancel.mockClear();
    HTMLCanvasElement.prototype.getContext = vi.fn(
      () => ({}) as unknown as CanvasRenderingContext2D,
    ) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders a page to a canvas and reports pageHeight", async () => {
    const doc = makeDoc(5) as unknown as PDFDocumentProxy;
    render(<PageRendererProbe doc={doc} pageNumber={1} pageWidth={200} />);

    // Initially loading.
    expect(document.querySelector('[data-testid="isLoading"]')?.textContent).toBe("true");

    await waitFor(() => {
      expect(document.querySelector('[data-testid="isLoading"]')?.textContent).toBe("false");
    });
    // pageWidth=200, base width=100, so scale=2, viewport height=200*2=400
    expect(document.querySelector('[data-testid="pageHeight"]')?.textContent).toBe("400");
    expect(mockGetViewport).toHaveBeenCalledWith({ scale: 1 });
    expect(mockRenderPromise).toHaveBeenCalled();
  });

  it("reports error when page rendering fails", async () => {
    mockRenderPromise.mockRejectedValueOnce(new Error("render failure"));
    const doc = makeDoc(1) as unknown as PDFDocumentProxy;
    render(<PageRendererProbe doc={doc} pageNumber={1} pageWidth={100} />);

    await waitFor(() => {
      expect(document.querySelector('[data-testid="error"]')?.textContent).toBe("render failure");
    });
    expect(document.querySelector('[data-testid="isLoading"]')?.textContent).toBe("false");
  });

  it("reports error when canvas context is unavailable", async () => {
    HTMLCanvasElement.prototype.getContext = vi.fn(() => null);
    const doc = makeDoc(1) as unknown as PDFDocumentProxy;
    render(<PageRendererProbe doc={doc} pageNumber={1} pageWidth={100} />);

    await waitFor(() => {
      expect(document.querySelector('[data-testid="error"]')?.textContent).toBe(
        "canvas 2d context unavailable",
      );
    });
  });
});
