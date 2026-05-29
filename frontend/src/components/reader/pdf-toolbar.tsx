// SPDX-License-Identifier: AGPL-3.0-or-later
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  Maximize2Icon,
  RotateCcwIcon,
  ZoomInIcon,
  ZoomOutIcon,
} from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/** Zoom range constants. */
export const ZOOM_MIN = 50;
export const ZOOM_MAX = 300;
export const ZOOM_STEP = 25;
export const ZOOM_DEFAULT = 100;

export interface PdfToolbarProps {
  /** Current zoom percentage (50-300). */
  zoom: number;
  /** Callback when zoom changes. */
  onZoomChange: (zoom: number) => void;
  /** Current 1-based page number. */
  currentPage: number;
  /** Total number of pages. */
  totalPages: number;
  /** Callback to navigate to a specific 1-based page. */
  onNavigateToPage: (page: number) => void;
  /** Whether the viewer is currently loading the document. */
  isLoading?: boolean;
  /** Whether pages are still being rendered after document load. */
  isRendering?: boolean;
  /** Whether this is a large document (50+ pages). */
  isLargeDocument?: boolean;
  className?: string;
}

/**
 * Toolbar for PDF viewer with zoom controls and page navigation.
 *
 * Zoom range: 50%-300%, step 25%.
 * Keyboard shortcuts (registered in PdfViewer, not here):
 *   Ctrl+=  zoom in
 *   Ctrl+-  zoom out
 *   Ctrl+0  reset to 100%
 *   PageUp/PageDown  navigate pages
 *   Home/End  first/last page
 */
export function PdfToolbar({
  zoom,
  onZoomChange,
  currentPage,
  totalPages,
  onNavigateToPage,
  isLoading = false,
  isRendering = false,
  isLargeDocument = false,
  className,
}: PdfToolbarProps) {
  const [pageInputValue, setPageInputValue] = React.useState(currentPage.toString());
  const [isEditingPage, setIsEditingPage] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Sync the input value when currentPage changes externally (e.g. scrolling).
  React.useEffect(() => {
    if (!isEditingPage) {
      setPageInputValue(currentPage.toString());
    }
  }, [currentPage, isEditingPage]);

  const canZoomIn = zoom < ZOOM_MAX;
  const canZoomOut = zoom > ZOOM_MIN;
  const canPrevPage = currentPage > 1;
  const canNextPage = currentPage < totalPages;

  function handleZoomIn() {
    if (canZoomIn) {
      onZoomChange(Math.min(zoom + ZOOM_STEP, ZOOM_MAX));
    }
  }

  function handleZoomOut() {
    if (canZoomOut) {
      onZoomChange(Math.max(zoom - ZOOM_STEP, ZOOM_MIN));
    }
  }

  function handleFitWidth() {
    // Fit-width maps to 100% for now; future: compute from container width.
    onZoomChange(ZOOM_DEFAULT);
  }

  function handleReset() {
    onZoomChange(ZOOM_DEFAULT);
  }

  function handlePageInputSubmit() {
    const page = parseInt(pageInputValue, 10);
    if (!Number.isNaN(page) && page >= 1 && page <= totalPages) {
      onNavigateToPage(page);
    } else {
      // Reset to current page on invalid input.
      setPageInputValue(currentPage.toString());
    }
    setIsEditingPage(false);
  }

  function handlePageInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      handlePageInputSubmit();
    } else if (e.key === "Escape") {
      setPageInputValue(currentPage.toString());
      setIsEditingPage(false);
    }
  }

  function handlePageInputFocus() {
    setIsEditingPage(true);
    // Select all text on focus for easy editing.
    setTimeout(() => {
      inputRef.current?.select();
    }, 0);
  }

  function handlePageInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    setPageInputValue(e.target.value);
  }

  const disableControls = isLoading;

  return (
    <div
      data-slot="pdf-toolbar"
      className={cn(
        "border-border/60 flex h-10 items-center gap-1 border-b px-2",
        className,
      )}
    >
      {/* Rendering indicator — informational only, does not disable controls */}
      {isRendering && (
        <span className="text-muted-foreground mr-1 text-xs animate-pulse">
          Rendering{isLargeDocument ? " large document" : ""}...
        </span>
      )}

      {/* Zoom controls */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            onClick={handleZoomOut}
            disabled={!canZoomOut || disableControls}
            aria-label="Zoom out"
          >
            <ZoomOutIcon className="size-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Zoom Out (Ctrl+-)</TooltipContent>
      </Tooltip>

      <span
        className="text-muted-foreground w-12 text-center text-xs tabular-nums hidden sm:inline"
        aria-label={`Zoom level: ${zoom.toString()}%`}
      >
        {zoom}%
      </span>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            onClick={handleZoomIn}
            disabled={!canZoomIn || disableControls}
            aria-label="Zoom in"
          >
            <ZoomInIcon className="size-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Zoom In (Ctrl+=)</TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            onClick={handleFitWidth}
            disabled={disableControls}
            aria-label="Fit width"
          >
            <Maximize2Icon className="size-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Fit Width</TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            onClick={handleReset}
            disabled={zoom === ZOOM_DEFAULT || disableControls}
            aria-label="Reset zoom"
          >
            <RotateCcwIcon className="size-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Reset Zoom (Ctrl+0)</TooltipContent>
      </Tooltip>

      {/* Separator */}
      <div className="bg-border/60 mx-1 h-4 w-px" />

      {/* Page navigation */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            onClick={() => onNavigateToPage(currentPage - 1)}
            disabled={!canPrevPage || disableControls}
            aria-label="Previous page"
          >
            <ChevronLeftIcon className="size-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Previous Page (PageUp)</TooltipContent>
      </Tooltip>

      <div className="flex items-center gap-1 text-xs">
        <input
          ref={inputRef}
          type="text"
          inputMode="numeric"
          value={pageInputValue}
          onChange={handlePageInputChange}
          onFocus={handlePageInputFocus}
          onBlur={handlePageInputSubmit}
          onKeyDown={handlePageInputKeyDown}
          className="bg-muted h-6 w-8 rounded border-none text-center text-xs tabular-nums outline-none focus:ring-1 focus:ring-ring"
          disabled={disableControls || totalPages === 0}
          aria-label={`Page number, ${currentPage} of ${totalPages}`}
        />
        <span className="text-muted-foreground">/</span>
        <span className="text-muted-foreground tabular-nums">{totalPages}</span>
      </div>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            onClick={() => onNavigateToPage(currentPage + 1)}
            disabled={!canNextPage || disableControls}
            aria-label="Next page"
          >
            <ChevronRightIcon className="size-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Next Page (PageDown)</TooltipContent>
      </Tooltip>
    </div>
  );
}