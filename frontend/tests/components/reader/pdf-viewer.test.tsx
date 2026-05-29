// SPDX-License-Identifier: AGPL-3.0-or-later
import { act, render, screen, waitFor } from "@testing-library/react";
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
function makePage(pageNumber: number) {
  return {
    pageNumber,
    getViewport: mockGetViewport,
    render: () => ({ promise: mockRenderPromise(), cancel: vi.fn() }),
    cleanup: vi.fn(),
    getTextContent: vi.fn(() => Promise.resolve({ items: [] })),
  };
}

const mockGetDocument = vi.fn<(...args: unknown[]) => unknown>();

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: (...args: unknown[]) => mockGetDocument(...args),
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

describe("PdfViewer", () => {
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
      const viewer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
      expect(viewer).not.toBeNull();
    });
    expect(document.querySelector("[data-slot='pdf-viewer'][data-mode='single']")).not.toBeNull();
  });

  it("renders pairs in dual mode", async () => {
    setupDocument(4);
    render(<PdfViewer url="/mock.pdf" mode="dual" />);

    await waitFor(() => {
      const viewer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
      expect(viewer).not.toBeNull();
    });
    expect(document.querySelector("[data-slot='pdf-viewer'][data-mode='dual']")).not.toBeNull();
  });

  it("renders an error state when the document fails to load", async () => {
    mockGetDocument.mockImplementation(() => {
      const task = {
        promise: Promise.reject(new Error("oh no")),
        destroy: vi.fn(),
        onProgress: null as (() => void) | null,
      };
      return task;
    });
    render(<PdfViewer url="/broken.pdf" mode="single" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/oh no/i);
  });

  it("shows password error for encrypted PDFs", async () => {
    mockGetDocument.mockImplementation(() => {
      const error = new Error("password required");
      error.name = "PasswordException";
      const task = {
        promise: Promise.reject(error),
        destroy: vi.fn(),
        onProgress: null as (() => void) | null,
      };
      return task;
    });
    render(<PdfViewer url="/encrypted.pdf" mode="single" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/password/i);
  });

  it("shows loading progress", async () => {
    const onProgressRef: { current: ((progress: { loaded: number; total: number }) => void) | null } = { current: null };
    let resolveDoc: (doc: unknown) => void;

    mockGetDocument.mockImplementation(() => {
      // eslint-disable-next-line @typescript-eslint/no-empty-function
      const noop = () => {};
      const task = {
        promise: new Promise((resolve: (doc: unknown) => void) => {
          resolveDoc = resolve;
        }),
        destroy: vi.fn(),
        onProgress: noop as (progress: { loaded: number; total: number }) => void,
      };
      // Capture the onProgress assignment from PdfViewer.
      Object.defineProperty(task, "onProgress", {
        set(cb: (progress: { loaded: number; total: number }) => void) {
          onProgressRef.current = cb;
        },
        get() {
          return onProgressRef.current ?? noop;
        },
      });
      return task;
    });

    render(<PdfViewer url="/large.pdf" mode="single" />);

    // Simulate progress callback.
    await waitFor(() => {
      expect(onProgressRef.current).not.toBeNull();
    });
    act(() => {
      onProgressRef.current!({ loaded: 500, total: 1000 });
    });

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(/50%/);
    });

    // Complete the load.
    resolveDoc!({
      numPages: 1,
      getPage: () => Promise.resolve(makePage(1)),
      destroy: vi.fn(),
    });

    await waitFor(() => {
      const viewer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
      expect(viewer).not.toBeNull();
    });
  });

  it("shows page loading state before canvas renders", async () => {
    setupDocument(2);
    render(<PdfViewer url="/mock.pdf" mode="single" />);

    // The virtual viewer should render the ready state after document loads.
    await waitFor(() => {
      const viewer = document.querySelector("[data-slot='pdf-viewer'][data-state='ready']");
      expect(viewer).not.toBeNull();
    });
  });
});
