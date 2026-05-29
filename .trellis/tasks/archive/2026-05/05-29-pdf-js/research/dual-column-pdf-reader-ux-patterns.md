# Research: Dual-Column PDF Reader UX Patterns

- **Query**: How do translation apps display original and translated PDF side by side? What scroll sync strategies exist?
- **Scope**: Mixed (internal + external patterns)
- **Date**: 2026-05-29

## Findings

### XReadAgent's Current Dual-Column Approach

XReadAgent uses **BabelDOC's alternating-pages dual PDF** format. This is NOT a two-PDF side-by-side layout. Key details from `pdf-viewer.tsx`:

- BabelDOC produces a single PDF where odd-indexed pages are the source and even-indexed are the translation.
- The `PdfViewer` component with `mode="dual"` splits this single PDF into pairs (page 1+2, page 3+4, etc.) and renders them in a 2-column CSS grid.
- Each pair is wrapped in a `<div data-slot="pdf-pair">` with `className="grid grid-cols-1 items-start gap-4 md:grid-cols-2"`.
- Max width per pair row is `max-w-[1600px]`.
- There is **no scroll synchronization** because both columns are part of the same vertical scroll flow. The pairs naturally scroll together since they are rows in a single column flex layout.

**Code reference** (`pdf-viewer.tsx:136-165`):
```tsx
if (mode === "dual") {
  const pairs: (readonly [number, number | null])[] = [];
  for (let i = 0; i < pageNumbers.length; i += 2) {
    const left = pageNumbers[i] ?? null;
    const right = pageNumbers[i + 1] ?? null;
    if (left === null) continue;
    pairs.push([left, right]);
  }
  // Rendered as grid rows in a flex column
}
```

### External Dual-Column Patterns

#### 1. BabelDOC / pdf2zh Approach (What XReadAgent Uses)

- **Single PDF, alternating pages**: The translation engine outputs one PDF where page 1 = original, page 2 = translation, page 3 = original, etc.
- **No scroll sync needed**: The viewer pairs pages by index and renders them in rows. Both columns scroll as part of the same vertical flow.
- **Layout fidelity**: BabelDOC preserves the exact layout of the original page in the translation, so figures/tables/equations stay in the same positions.
- **Limitation**: Page counts must match. If a paragraph expands in the target language, the translated page may be longer, breaking the strict alternating-page contract. BabelDOC handles this by re-typesetting to fit the same page dimensions.

#### 2. Two-PDF Side-by-Side (DeepL Document Viewer Style)

- **Two independent PDF documents**: Original on the left, translated on the right.
- **Scroll synchronization required**: Both viewers must track each other's scroll position so that page N original aligns with page N translation.
- **Scroll sync strategies**:
  - **Page-based sync**: When one viewer scrolls to page N, the other jumps to page N. Simple but abrupt.
  - **Proportional sync**: Both viewers share a scroll percentage (e.g., 42% through the document). Smooth but misaligns when page sizes differ.
  - **Pixel-ratio sync**: Scroll position of viewer A multiplied by a ratio derived from total document heights. Complex, brittle.
  - **Intersection Observer sync**: Use `IntersectionObserver` on page elements to detect which page is in view, then sync the other viewer to the same page. Robust for varying page sizes.
- **Advantages**: Works with any two PDFs (not limited to BabelDOC output). Supports independently zooming each panel.
- **Disadvantages**: Requires scroll sync implementation. May drift when pages have different heights. More complex state management (two loading states, two error states).

#### 3. Google Translate Bilingual View

- **Overlay/replace approach**: Google Translate's document translation replaces text in-place on the original page layout. No side-by-side; the translated text appears where the original was.
- **No dual-column needed**: The output is a single PDF with translated text replacing the original.
- **Layout preservation**: Similar to BabelDOC, uses font subsetting and bbox-level text replacement.

#### 4. pdf2zh Viewer (BabelDOC's sibling project)

- pdf2zh (the library BabelDOC wraps) provides its own web viewer that renders the dual PDF with a similar alternating-pages approach.
- The pdf2zh viewer uses PDF.js with a custom page-pair layout, similar to what XReadAgent has built.

### Scroll Sync Implementation Patterns (for reference)

If a two-PDF side-by-side mode were ever needed, these are the established patterns:

| Pattern | How it works | Robustness | Complexity |
|---|---|---|---|
| Page-locked sync | Both viewers scroll to the same page number | High (page boundaries are discrete) | Low |
| Proportional scroll | `scrollTop_A / scrollHeight_A = scrollTop_B / scrollHeight_B` | Low (breaks on different page counts/sizes) | Low |
| Intersection Observer | Observe which page element is centered; sync the other viewer | High (works with any page size) | Medium |
| Virtual scroll sync | Shared virtual scroll state drives both viewers | High (single source of truth) | High |

### Current XReadAgent Tab Architecture

The `paper-read.tsx` route uses a 3-tab layout (not a persistent side-by-side):

| Tab | What it shows | PdfViewer mode |
|---|---|---|
| Original | `raw/{slug}.pdf` | `mode="single"` |
| Dual | `translations/{slug}.dual.pdf` | `mode="dual"` |
| Translated | `translations/{slug}.mono.pdf` | `mode="single"` |

The default tab selection logic (`defaultTab()`):
1. If `dual` exists, default to "dual"
2. Else if `original` exists, default to "original"
3. Else if `mono` exists, default to "translated"

After a translation completes, the tab auto-switches:
- If `dual_path` is present in the finish event, switch to "dual" and pin
- Else if `mono_path` is present, switch to "translated" and pin
- Once pinned, the user's manual tab choice is respected over auto-defaults

### Related Specs

- `.trellis/tasks/archive/2026-05/05-25-phase-2-babeldoc-layout-preserving-translation-pdf-reader/prd.md` -- Original PRD with dual-column reader design decisions
- `.trellis/spec/frontend/index.md` -- Component and styling guidelines

## Caveats / Not Found

- No external web search was performed for this topic (tool not available). Patterns described are from general knowledge of the translation app space.
- DeepL's document viewer is proprietary; its exact scroll sync mechanism is not publicly documented.
- The current implementation already handles the most common use case well (BabelDOC alternating-pages PDF). A two-PDF side-by-side mode would only be needed if users wanted to compare translations from different models or different runs side by side.