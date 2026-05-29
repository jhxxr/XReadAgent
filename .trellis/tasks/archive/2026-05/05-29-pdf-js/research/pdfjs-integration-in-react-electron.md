# Research: PDF.js Integration in React/Electron

- **Query**: How do modern apps integrate PDF.js for reading in React/Electron? What's the best approach for a dual-column reader?
- **Scope**: Mixed (internal codebase + external libraries)
- **Date**: 2026-05-29

## Findings

### XReadAgent's Current Implementation

The project already has a working PDF.js integration. Key files:

| File Path | Description |
|---|---|
| `frontend/src/components/reader/pdf-viewer.tsx` | Main PdfViewer component with `single` and `dual` modes |
| `frontend/src/lib/pdfjs.ts` | Worker bootstrap (idempotent `ensurePdfWorker()`) |
| `frontend/src/routes/paper-read.tsx` | Paper read route with 3-tab layout (Original/Dual/Translated) |
| `frontend/package.json` | Already depends on `pdfjs-dist@5.4.149` |

**Architecture choices already made:**

1. **Direct pdfjs-dist** (not react-pdf or react-pdf-viewer). The project imports `getDocument` and `PDFDocumentProxy`/`PDFPageProxy` directly from `pdfjs-dist`. This gives full control over rendering lifecycle.

2. **Canvas-based rendering**. Each page is rendered to a `<canvas>` element via `page.render({ canvasContext, viewport, canvas })`. No SVG or text-layer rendering is used.

3. **Worker setup via Vite `?url` suffix**. In `lib/pdfjs.ts`, the worker is imported as `pdfjs-dist/build/pdf.worker.min.mjs?url`, which Vite resolves to a hashed URL under `/assets/` in production. This is registered once via `GlobalWorkerOptions.workerSrc`.

4. **Dual mode via BabelDOC's alternating-pages PDF**. The dual mode does NOT render two separate PDFs side by side. Instead, BabelDOC produces a single PDF where odd pages are original and even pages are translated. The PdfViewer splits these into pairs (page 1+2, 3+4, etc.) and renders them in a 2-column CSS grid.

5. **No virtual scrolling**. All pages are rendered immediately when the document loads. The component comment explicitly states: "No virtual scrolling, no thumbnails, no annotations -- the goal is a working reader, not a full PDF.js application."

6. **No text layer or annotation layer**. Pure canvas rendering only. Users cannot select text, search within the PDF, or interact with annotations.

### External Library Comparison

| Library | Approach | Pros | Cons |
|---|---|---|---|
| **pdfjs-dist (direct)** | Current approach. Low-level API, canvas rendering | Full control, minimal bundle, no abstraction leak | No built-in text layer, no virtual scroll, more manual wiring |
| **react-pdf** | `Document`/`Page` React wrappers around pdfjs-dist | Simple API, built-in loading states, text layer support | Opinionated, may conflict with custom dual-column layout, adds a dependency layer |
| **@react-pdf-viewer/core** | Full-featured viewer plugin system | Thumbnails, search, annotation, scroll mode, theme | Heavy bundle, plugin system may fight custom dual-column, opinionated UI |
| **pdf.js web viewer** | Mozilla's full viewer app (`viewer.html`) | Complete viewer, all features | Not a React component, iframe-based, hard to customize for dual-column |

### XReadAgent-Specific Considerations

1. **Vite + Electron dual target**: The `?url` import suffix for the worker works in both Vite dev mode and the production build. Electron renderer loads the worker from the `file://` protocol via the Vite output. The current `ensurePdfWorker()` pattern handles this correctly.

2. **pdfjs-dist version pinning**: Pinned at exact `5.4.149`. The frontend spec index explicitly lists this pinning strategy. Per the spec: "PDF rendering: `pdfjs-dist` (pinned exact, e.g. `5.4.149`) -- loaded only by `components/reader/*` and `lib/pdfjs.ts`".

3. **No react-pdf needed**: The project already has a working viewer. Adding react-pdf would introduce an unnecessary abstraction layer on top of code that already directly uses pdfjs-dist.

4. **Dual-column is already built**: The `mode="dual"` prop renders pairs of pages in a CSS grid. This leverages BabelDOC's alternating-pages dual PDF format, not a two-PDF side-by-side layout.

### Current Limitations (descriptive, not prescriptive)

- No text selection or copy from rendered pages
- No in-PDF search
- No virtual scrolling (all pages rendered at once -- could be slow for 100+ page PDFs)
- No thumbnail sidebar
- No page bookmarking or annotation
- No scroll-to-page or page number input
- No zoom controls (page width is fixed at 720px CSS)
- Canvas-only rendering means accessibility tools cannot read the PDF text

### External References

- [PDF.js documentation](https://mozilla.github.io/pdf.js/) -- upstream docs for pdfjs-dist API
- [react-pdf GitHub](https://github.com/wojtekmaj/react-pdf) -- React wrapper, uses pdfjs-dist internally
- [@react-pdf-viewer](https://react-pdf-viewer.js.org/) -- plugin-based viewer built on pdfjs-dist
- [pdfjs-dist npm](https://www.npmjs.com/package/pdfjs-dist) -- current version 5.x, Apache-2.0 license

### Related Specs

- `.trellis/spec/frontend/index.md` -- Stack Pinning section explicitly lists `pdfjs-dist` as the PDF rendering choice
- `.trellis/spec/guides/cross-layer-thinking-guide.md` -- Electron/Renderer boundary rules for worker URL resolution
- `.trellis/tasks/archive/2026-05/05-25-phase-2-babeldoc-layout-preserving-translation-pdf-reader/prd.md` -- Original Phase 2B implementation plan

## Caveats / Not Found

- The project does NOT use react-pdf or @react-pdf-viewer. Adding them would be a new dependency decision requiring spec update per the frontend index "Don't add a new UI primitive... without updating both `package.json` and this table."
- No research was done on PDF.js text layer API (which would enable text selection) as that was not in the research scope.