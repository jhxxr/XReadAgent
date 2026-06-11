// SPDX-License-Identifier: AGPL-3.0-or-later
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  getDocument,
  InvalidPDFException,
  type PDFDocumentLoadingTask,
  type PDFDocumentProxy,
} from "pdfjs-dist";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { ensurePdfWorker } from "@/lib/pdfjs";
import { usePageRenderer } from "@/lib/use-page-renderer";
import { ZOOM_DEFAULT, ZOOM_MAX, ZOOM_MIN, ZOOM_STEP } from "@/components/reader/pdf-toolbar";
import type { PdfToolbarProps } from "@/components/reader/pdf-toolbar";
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
   * Zoom percentage (50-300). When provided, the viewer is controlled by the
   * parent. When omitted, the viewer manages zoom internally.
   */
  zoom?: number;
  /** Callback when zoom changes. */
  onZoomChange?: (zoom: number) => void;
  /**
   * Current 1-based page number for controlled navigation.
   * When provided along with onNavigateToPage, the viewer is controlled.
   */
  currentPage?: number;
  /** Callback when the current page changes (e.g. user scrolls). */
  onCurrentPageChange?: (page: number) => void;
  /** Callback to navigate to a specific page. */
  onNavigateToPage?: (page: number) => void;
  /** Total pages callback — fires when document is loaded. */
  onTotalPagesChange?: (totalPages: number) => void;
  /** Toolbar render prop. Receives toolbar controls props. */
  renderToolbar?: (props: PdfToolbarProps) => React.ReactNode;
}

interface LoadState {
  status: "loading" | "ready" | "error";
  doc: PDFDocumentProxy | null;
  error: string | null;
  /** Fraction of document bytes downloaded (0-1), null while unknown. */
  progress: number | null;
}

/** Timeout in milliseconds before showing the "slow load" hint. */
const SLOW_LOAD_TIMEOUT_MS = 60_000;

/** Page count threshold for the "large document" warning. */
const LARGE_DOCUMENT_THRESHOLD = 50;

/**
 * Detect password-protected PDF errors by name, since `PasswordException`
 * is not re-exported from the pdfjs-dist top-level module.
 */
function isPasswordError(cause: unknown): boolean {
  // `PasswordException` is not exported from pdfjs-dist; narrow by name property.
  if (typeof cause === "object" && cause !== null && "name" in cause) {
    return cause.name === "PasswordException";
  }
  return false;
}

/**
 * Detect network/server errors from pdfjs-dist.
 *
 * pdfjs-dist reports network failures as "Unexpected server response (0)" and
 * browser-originated failures as "Failed to fetch" or similar.
 */
function isNetworkError(cause: unknown): boolean {
  if (cause instanceof Error) {
    const msg = cause.message;
    return (
      msg.includes("Unexpected server response (0)") ||
      msg.includes("Failed to fetch") ||
      msg.includes("NetworkError")
    );
  }
  return false;
}

/**
 * PDF viewer with virtual scrolling, text layer, zoom, and page navigation.
 *
 * Renders only pages in the current viewport (+ buffer) instead of all pages
 * at once. Uses `@tanstack/react-virtual` for virtualization. Each virtual
 * "row" is either one page (single mode) or two pages side-by-side (dual
 * mode). Page rendering is delegated to `usePageRenderer` for extensibility.
 */
export function PdfViewer({
  url,
  mode,
  className,
  zoom: controlledZoom,
  onZoomChange: controlledOnZoomChange,
  currentPage: controlledCurrentPage,
  onCurrentPageChange,
  onNavigateToPage: controlledOnNavigateToPage,
  onTotalPagesChange,
  renderToolbar,
}: PdfViewerProps) {
  const [state, setState] = React.useState<LoadState>({
    status: "loading",
    doc: null,
    error: null,
    progress: null,
  });

  // Internal zoom state (used when not controlled).
  const [internalZoom, setInternalZoom] = React.useState(ZOOM_DEFAULT);
  // Internal current page state (used when not controlled).
  const [internalCurrentPage, setInternalCurrentPage] = React.useState(1);

  // Retry mechanism: incrementing this key re-triggers the load effect.
  const [retryKey, setRetryKey] = React.useState(0);
  // Slow load detection: true when loading exceeds SLOW_LOAD_TIMEOUT_MS.
  const [slowLoad, setSlowLoad] = React.useState(false);

  const zoom = controlledZoom ?? internalZoom;
  const currentPage = controlledCurrentPage ?? internalCurrentPage;

  const handleZoomChange = React.useCallback(
    (newZoom: number) => {
      const clamped = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, newZoom));
      if (controlledOnZoomChange !== undefined) {
        controlledOnZoomChange(clamped);
      } else {
        setInternalZoom(clamped);
      }
    },
    [controlledOnZoomChange],
  );

  const handleCurrentPageChange = React.useCallback(
    (page: number) => {
      if (onCurrentPageChange !== undefined) {
        onCurrentPageChange(page);
      }
      setInternalCurrentPage(page);
    },
    [onCurrentPageChange],
  );

  React.useEffect(() => {
    ensurePdfWorker();
    let cancelled = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;

    setState({ status: "loading", doc: null, error: null, progress: null });
    setSlowLoad(false);

    // Slow load detection: show a hint after the timeout.
    const slowLoadTimerId = setTimeout(() => {
      if (!cancelled) {
        setSlowLoad(true);
      }
    }, SLOW_LOAD_TIMEOUT_MS);

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
        clearTimeout(slowLoadTimerId);
        setState({ status: "ready", doc, error: null, progress: 1 });
        onTotalPagesChange?.(doc.numPages);
      } catch (cause) {
        if (cancelled) return;
        clearTimeout(slowLoadTimerId);
        let message = "Failed to load PDF";
        if (isPasswordError(cause)) {
          message = "This PDF requires a password, which is not yet supported";
        } else if (cause instanceof InvalidPDFException) {
          message = "This file is not a valid PDF";
        } else if (isNetworkError(cause)) {
          message = "Could not connect to server. The file may not exist or the server is unavailable.";
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
      clearTimeout(slowLoadTimerId);
    };
  }, [url, onTotalPagesChange, retryKey]);

  const handleRetry = React.useCallback(() => {
    setRetryKey((prev) => prev + 1);
  }, []);

  if (state.status === "loading") {
    const pct =
      state.progress !== null ? `${Math.round(state.progress * 100)}%` : "...";
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
        {slowLoad && (
          <span className="text-muted-foreground text-xs">
            Loading is taking longer than expected...
          </span>
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
          "text-destructive flex h-full flex-col items-center justify-center gap-3 text-sm",
          className,
        )}
        role="alert"
      >
        <span>Could not load PDF: {state.error ?? "unknown error"}</span>
        <Button
          type="button"
          onClick={handleRetry}
          size="sm"
          aria-label="Retry loading PDF"
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <PdfPages
      doc={state.doc}
      mode={mode}
      zoom={zoom}
      onZoomChange={handleZoomChange}
      currentPage={currentPage}
      onCurrentPageChange={handleCurrentPageChange}
      onNavigateToPage={controlledOnNavigateToPage}
      renderToolbar={renderToolbar}
      className={className}
    />
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
  zoom: number;
  onZoomChange: (zoom: number) => void;
  currentPage: number;
  onCurrentPageChange: (page: number) => void;
  onNavigateToPage?: (page: number) => void;
  renderToolbar?: (props: PdfToolbarProps) => React.ReactNode;
  className?: string;
}

function PdfPages({
  doc,
  mode,
  zoom,
  onZoomChange,
  currentPage,
  onCurrentPageChange,
  onNavigateToPage,
  renderToolbar,
  className,
}: PdfPagesProps) {
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const containerWidthRef = React.useRef(0);

  // Compute the base page width at 100% zoom.
  // We use 720 as the default base width; fit-width mode would compute from
  // the container, but the container width varies so we track it.
  const BASE_PAGE_WIDTH = 720;

  // The effective page width at the current zoom level.
  const pageWidth = Math.round(BASE_PAGE_WIDTH * (zoom / 100));

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

  // Map from row index to the first page number in that row.
  // Used to determine which page is currently in view.
  const rowToFirstPage = React.useMemo(() => {
    return rows.map((row) => row.pages[0] ?? 1);
  }, [rows]);

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

  // Track which page is currently in view based on the virtualizer.
  // We observe which virtual rows are visible and pick the first one.
  const virtualItems = virtualizer.getVirtualItems();

  React.useEffect(() => {
    if (virtualItems.length === 0) return;
    // Find the row closest to the center of the viewport.
    const scrollElement = scrollRef.current;
    if (scrollElement === null) return;
    // A viewer kept alive inside a hidden tab panel (display:none) measures
    // zero height; skip page tracking so it can't report a bogus position.
    if (scrollElement.clientHeight === 0) return;

    const viewportCenter = scrollElement.scrollTop + scrollElement.clientHeight / 2;

    let closestRow = virtualItems[0];
    if (closestRow === undefined) return;
    let closestDistance = Infinity;

    for (const item of virtualItems) {
      const itemCenter = item.start + (item.size / 2);
      const distance = Math.abs(viewportCenter - itemCenter);
      if (distance < closestDistance) {
        closestDistance = distance;
        closestRow = item;
      }
    }

    if (closestRow !== undefined) {
      const firstPage = rowToFirstPage[closestRow.index];
      if (firstPage !== undefined && firstPage !== currentPage) {
        onCurrentPageChange(firstPage);
      }
    }
  }, [virtualItems, rowToFirstPage, currentPage, onCurrentPageChange]);

  // Handle navigate to page: scroll the virtualizer so the row containing
  // the target page is in view. Always scrolls internally; also notifies the
  // parent callback if provided.
  const handleNavigateToPage = React.useCallback(
    (page: number) => {
      // Find the row index that contains this page.
      const rowIndex = rows.findIndex((row) => row.pages.includes(page));
      if (rowIndex >= 0) {
        virtualizer.scrollToIndex(rowIndex, { align: "center" });
      }
      // Notify the parent if they provided a callback.
      onNavigateToPage?.(page);
    },
    [onNavigateToPage, rows, virtualizer],
  );

  // Initial scroll-to-page: on mount, scroll to the currentPage position
  // so that tab switches restore the user's reading position.
  const initialScrollDoneRef = React.useRef(false);
  React.useEffect(() => {
    if (initialScrollDoneRef.current) return;
    if (rows.length === 0) return;
    initialScrollDoneRef.current = true;

    if (currentPage > 1) {
      const rowIndex = rows.findIndex((row) => row.pages.includes(currentPage));
      if (rowIndex >= 0) {
        // Defer to the next frame so the virtualizer has laid out items.
        requestAnimationFrame(() => {
          virtualizer.scrollToIndex(rowIndex, { align: "start" });
        });
      }
    }
  }, [currentPage, rows, virtualizer]);

  // Track whether at least one page has finished rendering.
  // Used to show the "Rendering pages..." indicator.
  const [firstPageRendered, setFirstPageRendered] = React.useState(false);
  const handlePageRendered = React.useCallback(() => {
    setFirstPageRendered(true);
  }, []);

  const isLargeDocument = doc.numPages > LARGE_DOCUMENT_THRESHOLD;

  // Track container width for fit-width calculations.
  React.useEffect(() => {
    const el = scrollRef.current;
    if (el === null) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerWidthRef.current = entry.contentRect.width;
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Keyboard shortcuts for zoom and navigation.
  React.useEffect(() => {
    const el = scrollRef.current;
    if (el === null) return;

    function handleKeyDown(e: KeyboardEvent) {
      const isCtrl = e.ctrlKey || e.metaKey;

      // Zoom shortcuts
      if (isCtrl && (e.key === "=" || e.key === "+")) {
        e.preventDefault();
        onZoomChange(Math.min(zoom + ZOOM_STEP, ZOOM_MAX));
      } else if (isCtrl && e.key === "-") {
        e.preventDefault();
        onZoomChange(Math.max(zoom - ZOOM_STEP, ZOOM_MIN));
      } else if (isCtrl && e.key === "0") {
        e.preventDefault();
        onZoomChange(ZOOM_DEFAULT);
      }
      // Page navigation shortcuts (only when no input is focused)
      else if (
        e.key === "PageUp" &&
        !(e.target instanceof HTMLInputElement) &&
        !(e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        if (currentPage > 1) {
          handleNavigateToPage(currentPage - 1);
        }
      } else if (
        e.key === "PageDown" &&
        !(e.target instanceof HTMLInputElement) &&
        !(e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        if (currentPage < doc.numPages) {
          handleNavigateToPage(currentPage + 1);
        }
      } else if (
        e.key === "Home" &&
        !(e.target instanceof HTMLInputElement) &&
        !(e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        handleNavigateToPage(1);
      } else if (
        e.key === "End" &&
        !(e.target instanceof HTMLInputElement) &&
        !(e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        handleNavigateToPage(doc.numPages);
      }
    }

    el.addEventListener("keydown", handleKeyDown);
    return () => el.removeEventListener("keydown", handleKeyDown);
  }, [zoom, onZoomChange, currentPage, doc.numPages, handleNavigateToPage]);

  // Make the scroll container focusable for keyboard events.
  const handleContainerMouseDown = React.useCallback(() => {
    scrollRef.current?.focus();
  }, []);

  const isRendering = !firstPageRendered;

  const toolbarProps: PdfToolbarProps = {
    zoom,
    onZoomChange,
    currentPage,
    totalPages: doc.numPages,
    onNavigateToPage: handleNavigateToPage,
    isLoading: false,
    isRendering,
    isLargeDocument,
  };

  return (
    <div className={cn("flex h-full flex-col", className)}>
      {renderToolbar?.(toolbarProps)}
      <div className="relative flex-1 overflow-hidden">
        <div
          data-slot="pdf-viewer"
          data-state="ready"
          data-mode={mode}
          className="h-full overflow-auto outline-none"
          ref={scrollRef}
          tabIndex={-1}
          onMouseDown={handleContainerMouseDown}
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
                        onPageRendered={handlePageRendered}
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
        {/* Rendering overlay — shows briefly until first page paints. */}
        {isRendering && (
          <div
            data-slot="pdf-rendering-overlay"
            className="bg-background/80 absolute bottom-4 left-1/2 -translate-x-1/2 rounded-md px-3 py-1.5 text-xs shadow-sm backdrop-blur-sm"
            role="status"
            aria-live="polite"
          >
            {isLargeDocument
              ? "Large document, rendering may take a moment..."
              : "Rendering pages..."}
          </div>
        )}
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
  /** Callback fired when this page finishes rendering. */
  onPageRendered?: () => void;
}

function PdfPage({ doc, pageNumber, pageWidth, onPageRendered }: PdfPageProps) {
  const { canvasRef, textLayerRef, isLoading, error, pageHeight } = usePageRenderer(
    doc,
    pageNumber,
    pageWidth,
  );

  // Notify parent when this page finishes rendering.
  const prevLoadingRef = React.useRef(isLoading);
  React.useEffect(() => {
    if (prevLoadingRef.current && !isLoading) {
      onPageRendered?.();
    }
    prevLoadingRef.current = isLoading;
  }, [isLoading, onPageRendered]);

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
    <div
      data-slot="pdf-page-container"
      data-page={pageNumber}
      className="relative"
      style={isLoading ? { height: `${pageHeight.toString()}px` } : undefined}
    >
      {/* Skeleton overlay shown while canvas is rendering. The canvas element
          must always be in the DOM so that the canvasRef callback fires and
          triggers the actual page render. */}
      {isLoading && (
        <div
          data-slot="pdf-page-loading"
          data-page={pageNumber}
          className="bg-muted border-border/60 animate-pulse absolute inset-0 z-10 flex items-center justify-center rounded border shadow-sm"
          aria-label={`Page ${pageNumber.toString()} loading`}
        >
          <div className="flex flex-col items-center gap-2">
            <div className="bg-muted-foreground/10 h-3 w-16 rounded" />
            <span className="text-muted-foreground text-xs">{pageNumber}</span>
          </div>
        </div>
      )}
      <canvas
        ref={canvasRef}
        data-slot="pdf-page"
        data-page={pageNumber}
        aria-label={`Page ${pageNumber.toString()}`}
        className="border-border/60 bg-background rounded border shadow-sm"
      />
      <div
        ref={textLayerRef}
        className="pdf-text-layer absolute inset-0"
        aria-hidden="true"
      />
    </div>
  );
}