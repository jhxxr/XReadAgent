// SPDX-License-Identifier: AGPL-3.0-or-later
import { TextLayer } from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";
import * as React from "react";

/**
 * Result of the page renderer hook.
 *
 * - `canvasRef` — attach to a `<canvas>` element in the DOM.
 * - `textLayerRef` — attach to a `<div>` element that will host the text layer.
 * - `isLoading` — true while the page is being fetched/rendered.
 * - `error` — non-null when the page failed to load or render.
 * - `pageHeight` — the rendered height of the page in CSS pixels, or an
 *   estimate while loading. Useful for virtualizer row sizing.
 */
export interface PageRendererResult {
  canvasRef: React.RefCallback<HTMLCanvasElement>;
  textLayerRef: React.RefCallback<HTMLDivElement>;
  isLoading: boolean;
  error: string | null;
  pageHeight: number;
}

/**
 * Renders a single PDF page to a canvas element and overlays a transparent
 * text layer for selection.
 *
 * The hook manages the full lifecycle:
 * 1. Fetches the page from the document proxy via `doc.getPage(pageNumber)`.
 * 2. Computes the viewport at the scale that fits `pageWidth`.
 * 3. Renders the page to the canvas (using a ref callback).
 * 4. Renders the pdfjs-dist TextLayer on top of the canvas.
 * 5. Cleans up the PDFPageProxy and TextLayer on unmount or when inputs change.
 *
 * This abstraction decouples page rendering from the virtual-list layout,
 * making it straightforward to add search highlighting or annotation layers
 * in future PRs.
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
  // Track the current TextLayer instance so we can cancel it.
  const textLayerInstanceRef = React.useRef<TextLayer | null>(null);
  // Track whether the component is still mounted.
  const mountedRef = React.useRef(true);
  // Track the text layer container DOM element.
  const textLayerContainerRef = React.useRef<HTMLDivElement | null>(null);

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
      if (textLayerInstanceRef.current !== null) {
        textLayerInstanceRef.current.cancel();
        textLayerInstanceRef.current = null;
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
      // Clean up previous page and text layer.
      if (textLayerInstanceRef.current !== null) {
        textLayerInstanceRef.current.cancel();
        textLayerInstanceRef.current = null;
      }
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

  // Ref callback for the text layer container div — just stores the element.
  const textLayerRef = React.useCallback((containerEl: HTMLDivElement | null) => {
    textLayerContainerRef.current = containerEl;

    // Clear any existing text layer when the container changes.
    if (textLayerInstanceRef.current !== null) {
      textLayerInstanceRef.current.cancel();
      textLayerInstanceRef.current = null;
    }
    if (containerEl !== null) {
      // Clear any stale DOM content from a previous render.
      while (containerEl.firstChild !== null) {
        containerEl.removeChild(containerEl.firstChild);
      }
    }
  }, []);

  // Effect: render the text layer once the page proxy and container are both
  // available. This handles the async timing gap between the canvas ref
  // callback (which fetches and stores the page proxy) and the text layer
  // container mount. We include `isLoading` as a dependency so that when
  // canvas rendering completes (isLoading transitions false), the effect
  // re-evaluates and finds the page proxy ready.
  React.useEffect(() => {
    const page = pageRef.current;
    const container = textLayerContainerRef.current;
    if (page === null || container === null) return;

    // Store narrowed values as const so the closure retains the non-null type.
    const narrowedPage = page;
    const narrowedContainer = container;

    // Cancel any existing text layer.
    if (textLayerInstanceRef.current !== null) {
      textLayerInstanceRef.current.cancel();
      textLayerInstanceRef.current = null;
    }

    let cancelled = false;

    async function renderTextLayer() {
      try {
        // Clear any existing content in the container.
        while (narrowedContainer.firstChild !== null) {
          narrowedContainer.removeChild(narrowedContainer.firstChild);
        }

        const baseViewport = narrowedPage.getViewport({ scale: 1 });
        const scale = pageWidth / baseViewport.width;
        const viewport = narrowedPage.getViewport({ scale });

        const textContent = await narrowedPage.getTextContent();
        if (cancelled || !mountedRef.current) return;

        const textLayer = new TextLayer({
          textContentSource: textContent,
          container: narrowedContainer,
          viewport,
        });
        textLayerInstanceRef.current = textLayer;
        await textLayer.render();
      } catch (cause) {
        if (cancelled || !mountedRef.current) return;
        // Text layer failures are non-fatal — the canvas still renders fine.
        const errName = (cause as { name?: string } | null)?.name;
        if (errName === "RenderingCancelledException") return;
        // Silently ignore text layer errors — canvas rendering is the primary
        // concern and text layer is a best-effort overlay.
      }
    }

    void renderTextLayer();

    return () => {
      cancelled = true;
      if (textLayerInstanceRef.current !== null) {
        textLayerInstanceRef.current.cancel();
        textLayerInstanceRef.current = null;
      }
    };
  }, [doc, pageNumber, pageWidth, isLoading]);

  return { canvasRef, textLayerRef, isLoading, error, pageHeight };
}