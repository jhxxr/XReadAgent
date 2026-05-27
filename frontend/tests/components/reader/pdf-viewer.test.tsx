// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the worker URL import — Vitest needs an explicit resolver since `?url`
// is a Vite-specific suffix.
vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({
  default: "blob:mock-worker-url",
}));

// Mock pdfjs-dist itself so we can drive the render lifecycle without a real
// worker / canvas backend (jsdom has neither).
const mockRenderPromise = vi.fn(() => Promise.resolve(undefined));
const mockGetViewport = vi.fn(({ scale }: { scale: number }) => ({
  width: 100 * scale,
  height: 200 * scale,
}));
const makePage = (pageNumber: number) => ({
  pageNumber,
  getViewport: mockGetViewport,
  render: () => ({ promise: mockRenderPromise() }),
  cleanup: vi.fn(),
});

const mockGetDocument = vi.fn<(...args: unknown[]) => unknown>();

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: (...args: unknown[]) => mockGetDocument(...args),
}));

import { PdfViewer } from "@/components/reader/pdf-viewer";

function setupDocument(numPages: number) {
  mockGetDocument.mockImplementation(() => ({
    promise: Promise.resolve({
      numPages,
      getPage: (n: number) => Promise.resolve(makePage(n)),
      destroy: vi.fn(),
    }),
    destroy: vi.fn(),
  }));
}

describe("PdfViewer", () => {
  beforeEach(() => {
    mockGetDocument.mockReset();
    mockRenderPromise.mockClear();
    // jsdom's `<canvas>` returns null from getContext; stub it.
    HTMLCanvasElement.prototype.getContext = vi.fn(
      () => ({}) as unknown as CanvasRenderingContext2D,
    ) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders pages in single mode", async () => {
    setupDocument(3);
    render(<PdfViewer url="/mock.pdf" mode="single" />);

    await waitFor(() => {
      const canvases = document.querySelectorAll("canvas[data-slot='pdf-page']");
      expect(canvases.length).toBe(3);
    });
    expect(document.querySelector("[data-slot='pdf-viewer'][data-mode='single']")).not.toBeNull();
  });

  it("renders pairs in dual mode", async () => {
    setupDocument(4);
    render(<PdfViewer url="/mock.pdf" mode="dual" />);

    await waitFor(() => {
      const canvases = document.querySelectorAll("canvas[data-slot='pdf-page']");
      expect(canvases.length).toBe(4);
    });
    const pairs = document.querySelectorAll("[data-slot='pdf-pair']");
    // 4 pages → 2 pairs.
    expect(pairs.length).toBe(2);
  });

  it("renders an error state when the document fails to load", async () => {
    mockGetDocument.mockImplementation(() => ({
      promise: Promise.reject(new Error("oh no")),
      destroy: vi.fn(),
    }));
    render(<PdfViewer url="/broken.pdf" mode="single" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/oh no/i);
  });
});
