// SPDX-License-Identifier: AGPL-3.0-or-later
import { getDocument, type PDFDocumentProxy, type PDFPageProxy } from "pdfjs-dist";
import * as React from "react";

import { ensurePdfWorker } from "@/lib/pdfjs";
import { cn } from "@/lib/utils";

/**
 * Render mode for the viewer.
 *
 * - `single` — pages laid out vertically in one column. Used for Original
 *   and Translated tabs.
 * - `dual`  — pages laid out two-up (left = original-page, right =
 *   translation-page). Matches BabelDOC's alternating-pages dual PDF, where
 *   odd-indexed pages are the source and even-indexed are the translation.
 *   We render them side-by-side per pair so the reader sees them aligned.
 */
export type PdfViewerMode = "single" | "dual";

export interface PdfViewerProps {
  /** Absolute or `apiBase`-relative URL that resolves to a PDF binary. */
  url: string;
  mode: PdfViewerMode;
  className?: string;
  /**
   * CSS pixel width of each rendered page canvas. Defaults to 720 which
   * fits comfortably inside the reader column at typical paper aspect.
   */
  pageWidth?: number;
}

interface LoadState {
  status: "loading" | "ready" | "error";
  doc: PDFDocumentProxy | null;
  error: string | null;
}

/**
 * Thin wrapper around pdfjs-dist that renders all pages of a PDF.
 *
 * Phase 2B keeps this deliberately simple: it loads the document, renders
 * every page to a `<canvas>`, and laid out either one-column (single) or
 * two-column (dual). No virtual scrolling, no thumbnails, no annotations —
 * the goal is a working reader, not a full PDF.js application.
 */
export function PdfViewer({ url, mode, className, pageWidth = 720 }: PdfViewerProps) {
  const [state, setState] = React.useState<LoadState>({
    status: "loading",
    doc: null,
    error: null,
  });

  React.useEffect(() => {
    ensurePdfWorker();
    let cancelled = false;
    let loadingTask: { destroy: () => Promise<unknown> } | null = null;

    setState({ status: "loading", doc: null, error: null });

    async function load() {
      try {
        const task = getDocument({ url });
        loadingTask = task;
        const doc = await task.promise;
        if (cancelled) {
          await doc.destroy();
          return;
        }
        setState({ status: "ready", doc, error: null });
      } catch (cause) {
        if (cancelled) return;
        const message = cause instanceof Error ? cause.message : "Failed to load PDF";
        setState({ status: "error", doc: null, error: message });
      }
    }

    void load();

    return () => {
      cancelled = true;
      if (loadingTask !== null) {
        void loadingTask.destroy();
      }
    };
  }, [url]);

  if (state.status === "loading") {
    return (
      <div
        data-slot="pdf-viewer"
        data-state="loading"
        className={cn(
          "text-muted-foreground flex h-full items-center justify-center text-sm",
          className,
        )}
        role="status"
        aria-live="polite"
      >
        Loading PDF…
      </div>
    );
  }
  if (state.status === "error" || state.doc === null) {
    return (
      <div
        data-slot="pdf-viewer"
        data-state="error"
        className={cn(
          "text-destructive flex h-full items-center justify-center text-sm",
          className,
        )}
        role="alert"
      >
        Could not load PDF: {state.error ?? "unknown error"}
      </div>
    );
  }

  return <PdfPages doc={state.doc} mode={mode} pageWidth={pageWidth} className={className} />;
}

interface PdfPagesProps {
  doc: PDFDocumentProxy;
  mode: PdfViewerMode;
  pageWidth: number;
  className?: string;
}

function PdfPages({ doc, mode, pageWidth, className }: PdfPagesProps) {
  const pageNumbers = React.useMemo(
    () => Array.from({ length: doc.numPages }, (_, i) => i + 1),
    [doc],
  );

  if (mode === "dual") {
    const pairs: (readonly [number, number | null])[] = [];
    for (let i = 0; i < pageNumbers.length; i += 2) {
      const left = pageNumbers[i] ?? null;
      const right = pageNumbers[i + 1] ?? null;
      if (left === null) continue;
      pairs.push([left, right]);
    }
    return (
      <div
        data-slot="pdf-viewer"
        data-state="ready"
        data-mode="dual"
        className={cn("flex h-full flex-col items-center gap-6 px-4 py-6", className)}
      >
        {pairs.map(([left, right]) => (
          <div
            key={`${left}-${right ?? "blank"}`}
            data-slot="pdf-pair"
            className="grid w-full max-w-[1600px] grid-cols-1 items-start gap-4 md:grid-cols-2"
          >
            <PdfPage doc={doc} pageNumber={left} pageWidth={pageWidth} />
            {right !== null ? (
              <PdfPage doc={doc} pageNumber={right} pageWidth={pageWidth} />
            ) : (
              <div aria-hidden className="h-1" />
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      data-slot="pdf-viewer"
      data-state="ready"
      data-mode="single"
      className={cn("flex h-full flex-col items-center gap-4 px-4 py-6", className)}
    >
      {pageNumbers.map((pageNumber) => (
        <PdfPage key={pageNumber} doc={doc} pageNumber={pageNumber} pageWidth={pageWidth} />
      ))}
    </div>
  );
}

interface PdfPageProps {
  doc: PDFDocumentProxy;
  pageNumber: number;
  pageWidth: number;
}

function PdfPage({ doc, pageNumber, pageWidth }: PdfPageProps) {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    let page: PDFPageProxy | null = null;

    async function render() {
      try {
        page = await doc.getPage(pageNumber);
        if (cancelled || page === null) return;
        const canvas = canvasRef.current;
        if (canvas === null) return;
        const ctx = canvas.getContext("2d");
        if (ctx === null) {
          setError("canvas 2d context unavailable");
          return;
        }
        const baseViewport = page.getViewport({ scale: 1 });
        const scale = pageWidth / baseViewport.width;
        const viewport = page.getViewport({ scale });
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        canvas.style.width = `${viewport.width.toString()}px`;
        canvas.style.height = `${viewport.height.toString()}px`;
        await page.render({ canvasContext: ctx, viewport, canvas }).promise;
      } catch (cause) {
        if (cancelled) return;
        const message = cause instanceof Error ? cause.message : "Failed to render page";
        setError(message);
      }
    }

    void render();

    return () => {
      cancelled = true;
      if (page !== null) {
        page.cleanup();
      }
    };
  }, [doc, pageNumber, pageWidth]);

  if (error !== null) {
    return (
      <div
        data-slot="pdf-page-error"
        data-page={pageNumber}
        className="text-destructive bg-destructive/5 border-destructive/30 w-full max-w-[800px] rounded border p-3 text-xs"
        role="alert"
      >
        Page {pageNumber} failed to render: {error}
      </div>
    );
  }
  return (
    <canvas
      ref={canvasRef}
      data-slot="pdf-page"
      data-page={pageNumber}
      aria-label={`Page ${pageNumber.toString()}`}
      className="border-border/60 bg-background rounded border shadow-sm"
    />
  );
}
