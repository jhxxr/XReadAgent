// SPDX-License-Identifier: AGPL-3.0-or-later
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  getDocument,
  InvalidPDFException,
  type PDFDocumentLoadingTask,
  type PDFDocumentProxy,
} from "pdfjs-dist";
import * as React from "react";

import { ensurePdfWorker } from "@/lib/pdfjs";
import { usePageRenderer } from "@/lib/use-page-renderer";
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
  /** Fraction of document bytes downloaded (0–1), null while unknown. */
  progress: number | null;
}

/**
 * Detect password-protected PDF errors by name, since `PasswordException`
 * is not re-exported from the pdfjs-dist top-level module.
 */
function isPasswordError(cause: unknown): boolean {
  // `PasswordException` is not exported from pdfjs-dist; narrow by name property.
  return (cause as { name?: string } | null)?.name === "PasswordException";
}

/**
 * PDF viewer with virtual scrolling.
 *
 * Renders only pages in the current viewport (+ buffer) instead of all pages
 * at once. Uses `@tanstack/react-virtual` for virtualization. Each virtual
 * "row" is either one page (single mode) or two pages side-by-side (dual
 * mode). Page rendering is delegated to `usePageRenderer` for extensibility.
 */
export function PdfViewer({ url, mode, className, pageWidth = 720 }: PdfViewerProps) {
  const [state, setState] = React.useState<LoadState>({
    status: "loading",
    doc: null,
    error: null,
    progress: null,
  });

  React.useEffect(() => {
    ensurePdfWorker();
    let cancelled = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;

    setState({ status: "loading", doc: null, error: null, progress: null });

    async function load() {
      try {
        const task = getDocument({
          url,
          useSystemFonts: true,
        });
        loadingTask = task;

        task.onProgress = (progress: { loaded: number; total: number }) => {
          if (cancelled) return;
          const fraction = progress.total > 0 ? progress.loaded / progress.total : null;
          setState((prev) => ({ ...prev, progress: fraction }));
        };

        const doc = await task.promise;
        if (cancelled) {
          await doc.destroy();
          return;
        }
        setState({ status: "ready", doc, error: null, progress: 1 });
      } catch (cause) {
        if (cancelled) return;
        let message = "Failed to load PDF";
        if (isPasswordError(cause)) {
          message = "This PDF requires a password, which is not yet supported";
        } else if (cause instanceof InvalidPDFException) {
          message = "This file is not a valid PDF";
        } else if (cause instanceof Error) {
          message = cause.message;
        }
        setState({ status: "error", doc: null, error: message, progress: null });
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
    const pct =
      state.progress !== null ? `${Math.round(state.progress * 100)}%` : "…";
    return (
      <div
        data-slot="pdf-viewer"
        data-state="loading"
        className={cn(
          "text-muted-foreground flex h-full flex-col items-center justify-center gap-3 text-sm",
          className,
        )}
        role="status"
        aria-live="polite"
      >
        <span>Loading PDF {pct}</span>
        {state.progress !== null && (
          <div className="bg-muted h-1.5 w-48 overflow-hidden rounded-full">
            <div
              className="bg-primary h-full rounded-full transition-all duration-300"
              style={{ width: `${(state.progress * 100).toString()}%` }}
            />
          </div>
        )}
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

  return (
    <PdfPages doc={state.doc} mode={mode} pageWidth={pageWidth} className={className} />
  );
}

// ---------------------------------------------------------------------------
// Virtualised page list
// ---------------------------------------------------------------------------

interface Row {
  /** 1-based page numbers in this row. Single mode: [n]; dual: [left, right?]. */
  pages: readonly number[];
}

interface PdfPagesProps {
  doc: PDFDocumentProxy;
  mode: PdfViewerMode;
  pageWidth: number;
  className?: string;
}

function PdfPages({ doc, mode, pageWidth, className }: PdfPagesProps) {
  const scrollRef = React.useRef<HTMLDivElement>(null);

  // Build the list of rows from the document page count and mode.
  const rows: readonly Row[] = React.useMemo(() => {
    const result: Row[] = [];
    if (mode === "dual") {
      for (let i = 1; i <= doc.numPages; i += 2) {
        const left = i;
        const right = i + 1 <= doc.numPages ? i + 1 : null;
        result.push({ pages: right !== null ? [left, right] : [left] });
      }
    } else {
      for (let i = 1; i <= doc.numPages; i++) {
        result.push({ pages: [i] });
      }
    }
    return result;
  }, [doc, mode]);

  // Estimate row heights. We need a way to give the virtualizer a good
  // estimate before a row is actually rendered. Strategy:
  //   - Measure the first page's aspect ratio once we can get it.
  //   - Use that ratio for all subsequent estimates.
  //   - Once a row is measured, the virtualizer gets the real height.
  const [avgPageHeight, setAvgPageHeight] = React.useState<number | null>(null);

  // We measure the first page's viewport on mount to seed the estimate.
  React.useEffect(() => {
    let cancelled = false;
    async function measure() {
      try {
        const page = await doc.getPage(1);
        if (cancelled) {
          page.cleanup();
          return;
        }
        const vp = page.getViewport({ scale: 1 });
        const computedScale = pageWidth / vp.width;
        const estimated = Math.ceil(vp.height * computedScale);
        setAvgPageHeight(estimated);
        page.cleanup();
      } catch {
        // If we can't measure, the virtualizer will use the default estimate.
      }
    }
    void measure();
    return () => {
      cancelled = true;
    };
  }, [doc, pageWidth]);

  const isDual = mode === "dual";

  // Default estimate for row height before we measure.
  const defaultEstimate = avgPageHeight ?? pageWidth * 1.35; // ~1.35:1 is typical letter/A4

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => defaultEstimate + 24, // 24 = vertical gap + padding
    overscan: 3,
  });

  return (
    <div
      data-slot="pdf-viewer"
      data-state="ready"
      data-mode={mode}
      className={cn("h-full overflow-auto", className)}
      ref={scrollRef}
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize().toString()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const row = rows[virtualRow.index];
          if (row === undefined) return null;
          return (
            <div
              key={virtualRow.key}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualRow.start.toString()}px)`,
              }}
              className="flex justify-center px-4 py-3"
            >
              <div
                data-slot="pdf-pair"
                className={cn(
                  "grid items-start gap-4",
                  isDual
                    ? "w-full max-w-[1600px] grid-cols-1 md:grid-cols-2"
                    : "w-full max-w-[800px] grid-cols-1",
                )}
              >
                {row.pages.map((pageNumber) => (
                  <PdfPage
                    key={pageNumber}
                    doc={doc}
                    pageNumber={pageNumber}
                    pageWidth={pageWidth}
                  />
                ))}
                {/* In dual mode, if a row has only one page, add a blank cell. */}
                {isDual && row.pages.length === 1 && <div aria-hidden className="h-1" />}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single page renderer
// ---------------------------------------------------------------------------

interface PdfPageProps {
  doc: PDFDocumentProxy;
  pageNumber: number;
  pageWidth: number;
}

function PdfPage({ doc, pageNumber, pageWidth }: PdfPageProps) {
  const { canvasRef, isLoading, error, pageHeight } = usePageRenderer(doc, pageNumber, pageWidth);

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

  if (isLoading) {
    return (
      <div
        data-slot="pdf-page-loading"
        data-page={pageNumber}
        className="bg-muted border-border/60 flex w-full items-center justify-center rounded border shadow-sm"
        style={{ height: `${pageHeight.toString()}px` }}
        aria-label={`Page ${pageNumber.toString()} loading`}
      >
        <span className="text-muted-foreground text-xs">Page {pageNumber}</span>
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
