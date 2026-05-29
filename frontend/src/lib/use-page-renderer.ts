// SPDX-License-Identifier: AGPL-3.0-or-later
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";
import * as React from "react";

/**
 * Result of the page renderer hook.
 *
 * - `canvasRef` — attach to a `<canvas>` element in the DOM.
 * - `isLoading` — true while the page is being fetched/rendered.
 * - `error` — non-null when the page failed to load or render.
 * - `pageHeight` — the rendered height of the page in CSS pixels, or an
 *   estimate while loading. Useful for virtualizer row sizing.
 */
export interface PageRendererResult {
  canvasRef: React.RefCallback<HTMLCanvasElement>;
  isLoading: boolean;
  error: string | null;
  pageHeight: number;
}

/**
 * Renders a single PDF page to a canvas element.
 *
 * The hook manages the full lifecycle:
 * 1. Fetches the page from the document proxy via `doc.getPage(pageNumber)`.
 * 2. Computes the viewport at the scale that fits `pageWidth`.
 * 3. Renders the page to the canvas (using a ref callback).
 * 4. Cleans up the PDFPageProxy on unmount or when inputs change.
 *
 * This abstraction decouples page rendering from the virtual-list layout,
 * making it straightforward to add text-layer overlay, search highlighting,
 * or annotation layers in future PRs.
 *
 * @param doc         The loaded PDF document proxy.
 * @param pageNumber  1-based page number.
 * @param pageWidth   Desired CSS pixel width for the rendered page canvas.
 */
export function usePageRenderer(
  doc: PDFDocumentProxy,
  pageNumber: number,
  pageWidth: number,
): PageRendererResult {
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [pageHeight, setPageHeight] = React.useState(() => pageWidth * 1.35);

  // Track the current page proxy so we can clean it up when inputs change.
  const pageRef = React.useRef<PDFPageProxy | null>(null);
  // Track the current render task so we can cancel it.
  const renderTaskRef = React.useRef<RenderTask | null>(null);
  // Track whether the component is still mounted.
  const mountedRef = React.useRef(true);

  // Reset state when inputs change.
  React.useEffect(() => {
    setIsLoading(true);
    setError(null);
  }, [doc, pageNumber, pageWidth]);

  // Cleanup on unmount.
  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (renderTaskRef.current !== null) {
        renderTaskRef.current.cancel();
        renderTaskRef.current = null;
      }
      if (pageRef.current !== null) {
        pageRef.current.cleanup();
        pageRef.current = null;
      }
    };
  }, []);

  // Ref callback: called when a <canvas> element mounts or changes.
  // We kick off the render here so we always have a real DOM canvas.
  const canvasRef = React.useCallback(
    (canvasEl: HTMLCanvasElement | null) => {
      // Cancel any in-flight render.
      if (renderTaskRef.current !== null) {
        renderTaskRef.current.cancel();
        renderTaskRef.current = null;
      }
      // Clean up previous page.
      if (pageRef.current !== null) {
        pageRef.current.cleanup();
        pageRef.current = null;
      }

      if (canvasEl === null) {
        // Canvas was removed from the DOM (virtualized away).
        return;
      }

      // Capture the non-null canvas in a local const so TypeScript can narrow
      // it inside the async closure below.
      const canvas = canvasEl;
      let cancelled = false;

      async function renderPage() {
        try {
          const page = await doc.getPage(pageNumber);
          if (cancelled || !mountedRef.current) {
            page.cleanup();
            return;
          }
          pageRef.current = page;

          const baseViewport = page.getViewport({ scale: 1 });
          const scale = pageWidth / baseViewport.width;
          const viewport = page.getViewport({ scale });

          if (!cancelled && mountedRef.current) {
            setPageHeight(Math.ceil(viewport.height));
          }

          canvas.width = Math.ceil(viewport.width);
          canvas.height = Math.ceil(viewport.height);
          canvas.style.width = `${viewport.width.toString()}px`;
          canvas.style.height = `${viewport.height.toString()}px`;

          const ctx = canvas.getContext("2d");
          if (ctx === null) {
            if (!cancelled && mountedRef.current) {
              setError("canvas 2d context unavailable");
              setIsLoading(false);
            }
            return;
          }

          const renderTask = page.render({ canvasContext: ctx, viewport, canvas });
          renderTaskRef.current = renderTask;
          await renderTask.promise;

          if (!cancelled && mountedRef.current) {
            setIsLoading(false);
          }
        } catch (cause) {
          if (cancelled || !mountedRef.current) return;
          // RenderingCancelledException is expected when scrolling fast — not a real error.
          // `RenderingCancelledException` is not exported from pdfjs-dist; narrow by name.
          const errName = (cause as { name?: string } | null)?.name;
          if (errName === "RenderingCancelledException") return;
          const message = cause instanceof Error ? cause.message : "Failed to render page";
          setError(message);
          setIsLoading(false);
        } finally {
          renderTaskRef.current = null;
        }
      }

      void renderPage();

      // Cleanup when the ref callback element is removed or replaced.
      return () => {
        cancelled = true;
      };
    },
    [doc, pageNumber, pageWidth],
  );

  return { canvasRef, isLoading, error, pageHeight };
}