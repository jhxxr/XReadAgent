// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the worker URL import.
vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({
  default: "blob:mock-worker-url",
}));

// Mock pdfjs-dist with TextLayer mock.
vi.mock("pdfjs-dist", () => {
  return {
    GlobalWorkerOptions: { workerSrc: "" },
    getDocument: vi.fn(),
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
  };
});

import { usePageRenderer } from "@/lib/use-page-renderer";
import type { PDFDocumentProxy } from "pdfjs-dist";

const mockGetViewport = vi.fn(({ scale }: { scale: number }) => ({
  width: 100 * scale,
  height: 200 * scale,
}));
const mockCleanup = vi.fn();
const mockRenderPromise = vi.fn(() => Promise.resolve(undefined));
const mockCancel = vi.fn();
const mockGetTextContent = vi.fn(() =>
  Promise.resolve({
    items: [
      { str: "Hello", dir: "ltr", width: 50, height: 12, transform: [12, 0, 0, 12, 10, 180] },
    ],
  }),
);

function makePage(pageNumber: number) {
  return {
    pageNumber,
    getViewport: mockGetViewport,
    render: () => ({ promise: mockRenderPromise(), cancel: mockCancel }),
    cleanup: mockCleanup,
    getTextContent: mockGetTextContent,
  };
}

function makeDoc(numPages: number) {
  return {
    numPages,
    getPage: (n: number) => Promise.resolve(makePage(n)),
    destroy: vi.fn(),
  };
}

// Track TextLayer render/cancel calls via a module-level ref.
const textLayerRenderCalls = { count: 0 };
const textLayerCancelCalls = { count: 0 };

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
      <div ref={result.textLayerRef} data-testid="textLayer" />
    </div>
  );
}

describe("usePageRenderer TextLayer extension", () => {
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
    mockGetViewport.mockClear();
    mockCleanup.mockClear();
    mockRenderPromise.mockClear();
    mockCancel.mockClear();
    mockGetTextContent.mockClear();
    textLayerRenderCalls.count = 0;
    textLayerCancelCalls.count = 0;
    HTMLCanvasElement.prototype.getContext = vi.fn(
      () => ({}) as unknown as CanvasRenderingContext2D,
    ) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("provides a textLayerRef callback", async () => {
    const doc = makeDoc(5) as unknown as PDFDocumentProxy;
    render(<PageRendererProbe doc={doc} pageNumber={1} pageWidth={200} />);

    await waitFor(() => {
      expect(document.querySelector('[data-testid="isLoading"]')?.textContent).toBe("false");
    });

    // The text layer container div should be rendered.
    const textLayerDiv = document.querySelector('[data-testid="textLayer"]');
    expect(textLayerDiv).not.toBeNull();
  });

  it("calls getTextContent on the page to render the text layer", async () => {
    const doc = makeDoc(1) as unknown as PDFDocumentProxy;
    render(<PageRendererProbe doc={doc} pageNumber={1} pageWidth={100} />);

    await waitFor(() => {
      expect(mockGetTextContent).toHaveBeenCalled();
    });
  });

  it("handles text layer render failure gracefully", async () => {
    // Override getTextContent to reject so the text layer rendering fails.
    mockGetTextContent.mockRejectedValueOnce(new Error("text layer failed"));
    const doc = makeDoc(1) as unknown as PDFDocumentProxy;
    render(<PageRendererProbe doc={doc} pageNumber={1} pageWidth={100} />);

    // The canvas should still render successfully — text layer errors are non-fatal.
    await waitFor(() => {
      expect(document.querySelector('[data-testid="isLoading"]')?.textContent).toBe("false");
    });
    // No error should be surfaced for text layer failures.
    expect(document.querySelector('[data-testid="error"]')?.textContent).toBe("none");
  });
});