# Research: Layout-Preserving PDF Translation — pdf2zh / pdf2zh-next / BabelDOC

- **Query**: How to provide "格式还原翻译" (layout-preserving PDF translation) in XReadAgent — pdf2zh / pdf2zh-next / BabelDOC ecosystem and Python integration patterns.
- **Scope**: external (GitHub, PyPI, docs) + comparison with alternatives.
- **Date**: 2026-05-22

---

## Summary (Recommended Approach for XReadAgent)

1. **Use BabelDOC directly via `babeldoc.format.pdf.high_level.async_translate`** — not pdf2zh-next. BabelDOC v0.6.2 (PyPI, May 2026) is the actively-developed engine. pdf2zh-next is just a thin orchestrator around it (CLI + WebUI + subprocess wrapper + 12 translator backends). Since XReadAgent is Python-first and we want to own the translator layer (already wired to our LLM provider), the pdf2zh-next wrapper adds little value and bundles a lot of weight (gradio, deepl, ollama, xinference, tencent SDK…). **Note the trade-off**: BabelDOC's authors say "All APIs of BabelDOC should be considered internal — direct use is not supported." We'll pin a known-good version and own breaking-change risk.
2. **Run translation in a separate process** (multiprocessing or `concurrent.futures.ProcessPoolExecutor`), not in the FastAPI/asyncio main loop. pdf2zh-next's own reference implementation `_translate_in_subprocess` does exactly this — see `pdf2zh_next/high_level.py:313`. Reason: CPU-bound work (ONNX layout model, font subsetting, PDF re-rendering) starves the event loop; a crashing PDF should not crash the API server; and BabelDOC uses threads + global state internally (`process_pool`, `ProgressMonitor`).
3. **Lazy-download the 21 MB BabelDOC wheel + ~50 MB of ONNX/font assets on first use**, with a visible "Preparing translation engine…" step. Both pdf2zh-next and the official `babeldoc --warmup` flow do this. License is **AGPL-3.0** — this materially constrains how we distribute XReadAgent (see "Packaging" section).

---

## pdf2zh-next / BabelDOC Deep Dive

### Repo & maintenance state (verified 2026-05-22)

| Project | Active repo | Latest version | Released | Pushed |
|---|---|---|---|---|
| **BabelDOC** | [`funstory-ai/BabelDOC`](https://github.com/funstory-ai/BabelDOC) | **0.6.2** | 2026-05-08 | 2026-05-09 |
| **pdf2zh-next** (active) | [`PDFMathTranslate-next/PDFMathTranslate-next`](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) | **2.9.0** (PyPI, May 2026) | git main pinned to babeldoc 0.6.2 | actively maintained |
| **pdf2zh-next** (stale mirror) | `PDFMathTranslate/PDFMathTranslate-next` (org-fork) | git tag 2.8.2 | 2026-01-18 | last push 2026-04-08 (WebUI only) |
| **pdf2zh** (legacy v1.x) | [`PDFMathTranslate/PDFMathTranslate`](https://github.com/PDFMathTranslate/PDFMathTranslate) | **1.9.11** | 2025-07-11 | last code change 2026-04-06, no release since |

**Conclusion**: pin to `babeldoc==0.6.2` (or `>=0.6.2,<0.7.0`) directly. If we want translator-router goodies (DeepL, Google, Ollama, etc.), depend on `pdf2zh-next==2.9.0` from PyPI — *not* the GitHub org "PDFMathTranslate" (that's the legacy v1.x team; the rename-fork created confusion). The hyphenated org `PDFMathTranslate-next` is the real upstream.

### Architecture — how layout is preserved

BabelDOC pipeline (from `babeldoc/format/pdf/high_level.py` `TRANSLATE_STAGES`):

1. **Parse PDF → Intermediate Representation (IL)** — custom XML-ish IL built on pdfminer.six fork + PyMuPDF (14.12% of time budget).
2. **DetectScannedFile** — bail out early on image-only PDFs (2.45%).
3. **LayoutParser** — runs DocLayout-YOLO ONNX model (`doclayout_yolo_docstructbench_imgsz1024.onnx`, ~50 MB, downloaded on demand from HuggingFace + China mirror) to classify each region: text / title / formula / figure / table / list (14.03%).
4. **TableParser** — optional (1%).
5. **ParagraphFinder** — clusters lines into paragraphs respecting columns (6.26%).
6. **StylesAndFormulas** — splits formula tokens out of paragraph text using font/char heuristics (1.66%). Formulas are kept as-is (not translated).
7. **AutomaticTermExtractor** — first LLM pass to build a per-document glossary (30%).
8. **ILTranslator** — second LLM pass; translates each paragraph; injects glossary into prompt; rejects identical-to-source results (46.96% — the bulk).
9. **Typesetting** — reflows translated text into original bounding boxes; auto-shrinks font if overflow; handles RTL (4.71%).
10. **FontMapper** — picks a CJK font (`china-ss` / `china-ts` / `japan-s` / `korea-s` from `resfont_map`) matching the original style (serif/sans/script) (0.61%).
11. **PDFCreater** — emits draw-instructions back into a fresh PDF; preserves images, vector graphics, links, forms (1.96%).
12. **Subset font** — embeds only used glyphs to keep file size down (0.92%).
13. **Save PDF** — pymupdf safe_save + cmap fixup + metadata stamping (6.34%).

The clever part is **NOT** running LaTeX — it's **per-paragraph bbox reuse + glyph re-rendering**. Math formulas are detected at step 6 (heuristic on font/char patterns like `Cambria Math`, `STIX`, U+1D400 range) and excluded from the translation set so they survive as-is.

### Required dependencies (BabelDOC)

From `pyproject.toml`:

- **PyMuPDF ≥ 1.25.1** — primary PDF I/O.
- **onnx + onnxruntime** — for DocLayout-YOLO. Optional GPU extras: `directml`, `cuda`. Default = CPU. Inference ~1-3 s/page on modern CPU.
- **opencv-python-headless** — image preprocessing for layout model.
- **scikit-image, scikit-learn, scipy, numpy** — heavy numeric stack.
- **freetype-py, uharfbuzz, fontTools** — font shaping and subsetting.
- **hyperscan, rtree** — fast spatial indexing (paragraph bbox lookup) and regex. Note: `hyperscan` is x86-only — **no native ARM wheels**, so this is a blocker on Apple Silicon unless rosetta or `vectorscan` workaround.
- **tiktoken** — LLM token counting.
- **httpx[socks], openai** — translator side.
- **peewee** — SQLite cache for translation results (so re-runs are fast).
- **pyzstd, msgpack, orjson, lxml, bitstring** — IL serialization.

Wheel size on PyPI: **21.4 MB** for BabelDOC source dist; runtime deps balloon the install to ~300-500 MB including ONNX runtime and numpy/scipy/scikit. The DocLayout-YOLO model adds ~50 MB; CJK fonts add another ~30-80 MB.

### License: AGPL-3.0 (BOTH BabelDOC and pdf2zh-next)

This is critical. AGPL is more restrictive than GPL:

- If we **link** BabelDOC into XReadAgent and serve translation **over the network** (FastAPI endpoint), AGPL requires we offer XReadAgent's source code to remote users.
- Calling it via a **subprocess** with a well-defined IPC boundary *may* qualify as separate works ("mere aggregation") — but this is legally ambiguous and the Immersive Translate team (BabelDOC's commercial sponsor) sells a paid commercial license precisely to allow proprietary integration.
- If XReadAgent is itself open-source (AGPL-compatible) or local-only (no network service), this is fine.
- If XReadAgent intends to be closed-source SaaS, we **must** either (a) negotiate a commercial license with funstory-ai, (b) ship it as an optional plug-in that the user installs themselves, or (c) shell out to an externally-installed `babeldoc` CLI binary (treat as a system tool, like calling `ffmpeg`).

### `do_translate_async_stream` — the exact API

Defined at `pdf2zh_next/high_level.py:609`. Signature:

```python
async def do_translate_async_stream(
    settings: SettingsModel,        # pdf2zh_next.config.model.SettingsModel
    file: Path | str,
) -> AsyncGenerator[dict, None]:
    ...
```

It wraps BabelDOC's own `babeldoc.format.pdf.high_level.async_translate(config: TranslationConfig)`. Internally it either:

- **debug=True** → runs `babeldoc_translate` in the current process (good for breakpoints).
- **default** → spawns a `multiprocessing.Process` via `_translate_in_subprocess` (lines 313-…), with bidirectional pipes for progress events and a cancel signal, plus a `multiprocessing.Queue` for log records.

The yielded **event dict** schema (verified from `async_translate` docstring + `_translate_wrapper`):

```python
# Stage lifecycle
{"type": "progress_start", "stage": str, "stage_progress": 0.0,
 "stage_current": 0, "stage_total": int}

{"type": "progress_update", "stage": str, "stage_progress": 0-100,
 "stage_current": int, "stage_total": int, "overall_progress": 0-100}

{"type": "progress_end", "stage": str, "stage_progress": 100.0,
 "stage_current": int, "stage_total": int, "overall_progress": 0-100}

# Terminal events
{"type": "finish", "translate_result": TranslateResult,
 "token_usage": {"main": {...}, "term": {...}}}

{"type": "error", "error": str,
 "error_type": "BabeldocError|SubprocessError|IPCError|...",
 "details": str}
```

`TranslateResult` (from `babeldoc/format/pdf/translation_config.py:509`):

```python
@dataclass
class TranslateResult:
    mono_pdf_path: Path | None              # translated-only PDF
    dual_pdf_path: Path | None              # side-by-side / alternating original+translated
    no_watermark_mono_pdf_path: Path | None # if watermark_output_mode=Both
    no_watermark_dual_pdf_path: Path | None
    total_seconds: float
    original_pdf_path: Path
```

So **mono+dual export is built-in** — controlled by `TranslationConfig.no_mono`, `no_dual`, `use_alternating_pages_dual` (alternating vs side-by-side), and `watermark_output_mode ∈ {Watermarked, NoWatermark, Both}`.

### Cancellation, retry, progress

- **Cancellation**: caller cancels the async generator's task; the wrapper sends a sentinel through `pipe_cancel_message_send`; subprocess sets a `threading.Event` and calls `config.cancel_translation()`. If subprocess doesn't exit within 2 s → terminate; 1 s more → kill. So cancel is cooperative but reasonably bounded.
- **Retry**: BabelDOC uses `tenacity` internally for LLM/API calls (exponential backoff). Asset download retries on `httpx.HTTPError | ConnectionError | TimeoutError`. We should NOT retry the whole `do_translate_async_stream` automatically — it's expensive and the translation cache (peewee SQLite at `~/.cache/babeldoc/`) makes re-runs cheap anyway.
- **Progress reporting**: per-stage with `stage_current/stage_total` plus a global `overall_progress` 0-100 — perfect for a frontend progress bar. Reporting interval defaults to 0.1 s (`report_interval`).

### Calling from a long-running FastAPI/asyncio server

**Yes, possible** (pdf2zh-next ships a FastAPI HTTP shim — `pdf2zh_next/http_api.py` — that does exactly this). Gotchas:

- The translation runs in a `multiprocessing.Process`, so on Windows we need to guard with `if __name__ == "__main__"` somewhere up the import tree, **and on Windows the default spawn method serializes everything** — make sure `settings` is pickle-clean (no closures, no DB sessions). pdf2zh-next handles this via Pydantic `SettingsModel`.
- BabelDOC keeps a module-level process pool (`babeldoc.const.close_process_pool`) — call it on shutdown to avoid zombie processes.
- The async generator yields ~10 events/sec; consume promptly or back-pressure on the pipe will stall translation.
- Concurrent translations on one server: each one spawns its own subprocess; the ONNX layout model is loaded per subprocess (RAM cost ~500 MB-1 GB each). Use a semaphore to limit concurrency.

---

## Integration Patterns: direct-import vs subprocess vs runtime-asset-download

### Option A — Direct import (Python-side library)

```python
# Pseudocode for XReadAgent
from babeldoc.format.pdf.high_level import async_translate
from babeldoc.format.pdf.translation_config import TranslationConfig, WatermarkOutputMode
from babeldoc.translator.translator import BaseTranslator

class XReadAgentTranslator(BaseTranslator):
    # subclass to route LLM calls through our own provider abstraction
    async def do_llm_translate(self, prompts): ...

config = TranslationConfig(
    translator=XReadAgentTranslator(...),
    input_file=pdf_path,
    lang_in="en", lang_out="zh",
    doc_layout_model=None,        # auto-load
    no_mono=False, no_dual=False,
    watermark_output_mode=WatermarkOutputMode.NoWatermark,
    output_dir=output_dir,
    auto_extract_glossary=True,
)
async for event in async_translate(config):
    # forward to SSE/WebSocket client
    ...
```

- **Pros**: shortest path; we own translator routing; no subprocess pickling headaches in dev.
- **Cons**: a crash in BabelDOC kills the API process. AGPL linking case is strongest here. ONNX runtime + scikit + scipy must live in the same venv as the rest of XReadAgent (heavy).

### Option B — pdf2zh-next as subprocess library (mirror OpenSciReader's approach)

Use `do_translate_async_stream` from pdf2zh-next. It already does the subprocess split for us; we just consume events.

- **Pros**: process isolation for free; pdf2zh-next gives us 12 translator backends out of the box (Google, DeepL, Ollama, Tencent, Azure, etc.) without writing adapters. Cancel/timeout/IPC error handling already polished.
- **Cons**: pulls gradio + every translator SDK as a dep even if unused (deepl, ollama, xinference-client, tencentcloud-sdk-python-tmt). Heavier install.

### Option C — Separate runtime asset download (OpenSciReader's distribution model)

Ship XReadAgent as a slim binary, then on first "Translate" click:

1. Detect Python runtime availability (or embed a portable CPython 3.12 like OpenSciReader did).
2. `uv pip install --target=./runtime pdf2zh-next==2.9.0` — into an isolated directory.
3. `babeldoc --warmup` — pre-downloads ONNX model + fonts to `~/.cache/babeldoc/`.
4. Spawn the binary as needed via subprocess.

- **Pros**: keeps base installer ~50 MB instead of 500 MB+; users who never translate never pay the size cost; strong process boundary helps AGPL story.
- **Cons**: more shipping complexity; needs network on first use; uv/pip must work behind corporate proxies.

### Recommendation matrix for XReadAgent

| If XReadAgent is… | Pick |
|---|---|
| Local-only desktop app, open-source | **Option A** (direct import) — simplest, AGPL fine because the whole app is FOSS |
| Local-only desktop, closed-source | **Option C** (runtime download) — user installs the AGPL component themselves, like installing ffmpeg |
| Self-hosted server (homelab) | **Option A or B** — AGPL "remote network use" clause kicks in but you're your own user |
| SaaS / multi-tenant cloud | **Option C** with a "BYO translation engine" disclaimer, OR commercial license from funstory-ai |
| Just MVP / prototype | **Option B** — fastest path, swap later |

---

## Alternatives Comparison Table

| Approach | Layout fidelity | Cost (per 30 pg PDF) | Latency | Privacy | License | Effort to integrate |
|---|---|---|---|---|---|---|
| **BabelDOC direct** | High — keeps formulas, figures, tables, columns | ~$0.02-0.10 (Gemini/GPT-4o-mini tokens only) | 60-180 s | Local PDF + LLM call | AGPL-3.0 | Medium (subclass BaseTranslator) |
| **pdf2zh-next wrapper** | Same as BabelDOC | Same | Same + IPC overhead | Same | AGPL-3.0 | Low (just call API) |
| **LLM-direct markdown** (PyMuPDF text extract → LLM → render markdown) | Low — loses 2-column layout, formulas, figures inline broken | ~$0.01-0.05 | 20-60 s | Same | We control license | Low |
| **DeepL Document Translator API** | High — DeepL's renderer is reportedly excellent | **$30/1M chars** = ~$3 per 30-pg paper (≈ 100K chars) | 30-120 s | DeepL servers — paper text uploaded | Commercial, paid | Low (REST API) |
| **Google Translate Document API** (Cloud Translation v3) | Medium — DOCX/PDF supported but layout breaks on multi-column scientific PDFs | $20/1M chars + $0.08/page | 60+ s | Google Cloud | Commercial | Low |
| **Azure Translator Document Translation** | Medium-Low for scientific PDFs | ~$15/1M chars | 30-120 s | Azure | Commercial | Medium |
| **Custom: PyMuPDF bbox redraw** | Medium — works for simple papers, breaks on math/figures | Just LLM cost | 30-90 s | Local | MIT | High (effectively rebuilding BabelDOC) |
| **MinerU + LLM** ([opendatalab/MinerU](https://github.com/opendatalab/MinerU)) | High parsing, but output is Markdown not PDF | LLM cost | 60-180 s | Local | AGPL-3.0 | High (no PDF re-render) |
| **Edge browser PDF translate** | Built into Edge; uses Bing Translator; layout decent but no programmatic API | Free | Realtime | Microsoft | Closed | N/A — not callable |
| **SciSpace / Scholarcy translate** | Good but proprietary | Subscription | Variable | Cloud | Commercial | API may not exist |

**Honest take**: BabelDOC is the **only open-source thing that actually rebuilds a layout-faithful PDF**. Everything else either (a) gives up the PDF and switches to Markdown (loses layout but might be acceptable for an "AI reader" UI), (b) costs real money per page (DeepL), or (c) doesn't exist as a callable API (Edge). For an AI literature-reading app where the user-facing primary view will probably be a custom markdown-style chat panel, we should support **both**:

- **Fast lane**: PyMuPDF → markdown → LLM translate → display in our chat panel (no PDF generated). Cheap, ~20 s.
- **Slow lane** (on user click "Export translated PDF"): BabelDOC → mono+dual PDF. Heavy but exactly preserves layout, exportable.

---

## Packaging / Distribution Recommendations

### What modern Python apps do (2026 state of the art)

1. **uv tool install** — the official BabelDOC install path. `uv tool install --python 3.12 BabelDOC` creates an isolated venv and exposes `babeldoc` CLI. For an end-user-facing app this requires uv pre-installed, which is unrealistic for non-developers.
2. **PyInstaller / Nuitka one-file binary** — bundles CPython + all deps into a single .exe. For BabelDOC this would balloon to ~400-600 MB even with UPX, because of ONNX runtime, scipy, scikit-learn, numpy. Acceptable for "Pro" installer; bad for slim installer.
3. **Embedded Python + on-demand pip install** — what OpenSciReader does. Ship a slim app (50-100 MB) with embeddable-CPython; first-run installs the heavy deps to a sub-folder. Best balance for desktop apps.
4. **Tauri / Electron front + Python sidecar** — front-end framework spawns a Python "service" subprocess; sidecar can be either bundled or downloaded.
5. **Docker / containerized server** — if XReadAgent is server-side, just use a `python:3.12-slim` base image and `pip install pdf2zh-next`. Image ~1.5 GB.

### Concrete recommendation for XReadAgent

Given the user said XReadAgent is Python-first and wants a layout-preserving PDF feature:

- **MVP phase**: depend on `babeldoc==0.6.2` directly in `pyproject.toml`. Run it via `concurrent.futures.ProcessPoolExecutor` (one worker = one translation). Cache the ONNX model at the standard `~/.cache/babeldoc/` location.
- **Distribution phase**: switch to a "feature flag" install — base install excludes BabelDOC; `xreadagent[translate-layout]` extra pulls it in. First-time UI flow: "Layout translation requires downloading ~150 MB of models. Continue?" then `pip install babeldoc` via in-process pip (or `uv` if installed).
- **Asset prefetch**: expose a CLI command `xreadagent warmup-translator` that runs `babeldoc --warmup`. Document this for power users / Docker users.
- **Concurrency cap**: only 1 BabelDOC translation per process at a time (RAM cost ~1 GB each); queue further requests.

### Lazy-install considerations

- `babeldoc` and `onnxruntime` are pure-wheels on Windows/macOS/Linux x86-64. ARM Linux has wheels. **ARM macOS (Apple Silicon)** — `hyperscan` is the problem; check whether BabelDOC has fallback. Some forks use `vectorscan`. Verify before promising Mac M1/M2 support.
- pip install at runtime in a frozen app is fragile (PEP 668 may block, system Python may be missing). Better: bundle a venv-creator and ship `uv` alongside the app.

---

## Comparable Products' Approach

| Product | Approach | What we can borrow |
|---|---|---|
| **Microsoft Edge PDF translate** | Built-in; uses Bing Translator; renders text overlay on existing PDF pages (HTML/CSS overlay, not a new PDF) | The "overlay" idea: don't generate a new PDF — render translation as a transparent text layer in our viewer. Cheap, fast, preserves original perfectly. Doesn't export though. |
| **DeepL Document Translator** | Server-side proprietary engine; produces translated DOCX/PDF/PPTX. Excellent layout fidelity for office docs, weaker for academic 2-column LaTeX papers. | Their pricing model ($0.10/page-ish) is a sanity check on "is this worth a paid feature". |
| **Google Cloud Translation v3 — Document Translation** | REST API; you POST PDF, get back PDF. Layout fidelity is mediocre for scientific multi-column papers. | The async batch API pattern (long-running operation polling) — good model for our backend's translate endpoint shape. |
| **SciSpace (formerly Typeset)** | Cloud-only; uses their own parsing engine (probably similar to GROBID + Surya + custom typesetter); offers translation + Q&A on papers. | Their UX model — translation is a sidebar feature, not the main act. Suggests we should not over-invest in the PDF-output side; markdown chat panel is the primary UI. |
| **MinerU** ([opendatalab/MinerU](https://github.com/opendatalab/MinerU), AGPL) | Layout-aware PDF → Markdown/LaTeX. Doesn't translate, but the parsing stage is comparable to BabelDOC's IL. Heavier model stack but better at complex layouts. | Could replace BabelDOC's parsing with MinerU + our own renderer — but writing the renderer is the hard part BabelDOC solved. Not worth it. |
| **Mathpix** | Commercial; OCR for math; not really a translator | Inspiration for formula handling — BabelDOC's heuristic detection is simpler than Mathpix but covers most papers. |
| **Doc2X (noedgeai)** | Chinese commercial competitor; PDF → LaTeX → re-typeset in target language | The LaTeX intermediate route — high-fidelity but slow and only works for papers with LaTeX-like structure. BabelDOC's bbox-rewriting trick is more robust on arbitrary PDFs. |

---

## Open Questions

1. **AGPL distribution strategy** — does XReadAgent intend to be FOSS, dual-licensed, or proprietary SaaS? This single answer determines Option A vs C. Worth asking the user explicitly before writing code.
2. **macOS Apple Silicon support** — does `babeldoc` install cleanly on M1/M2? The `hyperscan` dep is the suspect. Need a quick `uv pip install --dry-run babeldoc` on a Mac (or check PyPI for `hyperscan` ARM wheels).
3. **Translator subclass quality** — when we subclass `babeldoc.translator.translator.BaseTranslator` to route through our LLM abstraction, do we get the same translation quality as pdf2zh-next's `OpenAITranslator`? They have specific prompt engineering for the "translate paragraph respecting glossary, return placeholder for formulas" task. Need to read `pdf2zh_next/translator/translator_impl/openai.py` to crib the prompts.
4. **Watermark policy** — `WatermarkOutputMode.Watermarked` (default) stamps "Translation generated by AI, please carefully discern" into the PDF metadata producer field. Acceptable? Required by upstream? Or do we use `NoWatermark`?
5. **Disk cache lifecycle** — BabelDOC's translation cache at `~/.cache/babeldoc/cache.db` grows unbounded. Need a UI to clear it; otherwise users will hit "why is my disk full" 6 months in.
6. **Per-paper translator config** — should we let users pick translation model per-paper (e.g. cheap mini for skim, expensive flagship for keepers)? BabelDOC supports it via `term_extraction_translator` separate from main translator.
7. **Mono vs dual default** — power users want dual (compare original on right); newcomers want mono. Default? Make it a setting.
8. **First-run UX for asset download** — `babeldoc --warmup` is ~50 MB ONNX + ~30 MB fonts = ~80 MB total. Acceptable to download silently? Or show a progress dialog?

---

## Sources

### Active upstream
- BabelDOC repo: https://github.com/funstory-ai/BabelDOC (v0.6.2, pushed 2026-05-09, 8.5 k stars, AGPL-3.0)
- BabelDOC PyPI: https://pypi.org/project/BabelDOC/ (sdist 21.4 MB)
- BabelDOC docs: https://funstory-ai.github.io/BabelDOC/
- pdf2zh-next active repo: https://github.com/PDFMathTranslate-next/PDFMathTranslate-next (v2.9.0 on PyPI May 2026)
- pdf2zh-next PyPI: https://pypi.org/project/pdf2zh-next/ (pins `babeldoc>=0.6.2,<0.7.0`)
- pdf2zh-next docs site: https://pdf2zh-next.com

### Stale / legacy (avoid)
- Original pdf2zh: https://github.com/PDFMathTranslate/PDFMathTranslate (v1.9.11, no release since 2025-07-11; pins old babeldoc 0.1.x-0.3.x; **don't use for new work**)
- Stale next-mirror: `PDFMathTranslate/PDFMathTranslate-next` (fork in old org, last push 2026-04-08)

### Key source files (read these before implementing)
- `babeldoc/format/pdf/high_level.py` — `async_translate(config)` is THE entry point
- `babeldoc/format/pdf/translation_config.py` — `TranslationConfig` 60+ params; `TranslateResult.{mono,dual}_pdf_path`; `WatermarkOutputMode` enum
- `babeldoc/translator/translator.py` — `BaseTranslator` to subclass
- `babeldoc/assets/assets.py` — model & font download / SHA verify
- `pdf2zh_next/high_level.py:313` — `_translate_in_subprocess` is the reference subprocess wrapper to copy
- `pdf2zh_next/high_level.py:609` — `do_translate_async_stream` is what OpenSciReader called
- `pdf2zh_next/http_api.py` — FastAPI HTTP API reference

### Recent issues to be aware of (BabelDOC)
- #592 "Translated text is overlapped and is merged into one line" (open, 2026-05)
- #593 Font corruption with bold/italic CJK text (open, 2026-05)
- #588 Highlight/background color not preserved after translation (open, 2026-04)
- #578 Symbol rotation issues (180° rotate edge case)
- #569 Control characters cause JSON parsing failure
- General theme: edge-case PDFs (heavy formatting, non-Latin source fonts, scanned-mixed) still break. Mainstream English-to-Chinese scientific papers work well.

### Alternatives referenced
- MinerU: https://github.com/opendatalab/MinerU (PDF→Markdown, AGPL)
- DeepL Document API: https://www.deepl.com/docs-api/documents
- Google Cloud Translation v3 Document: https://cloud.google.com/translate/docs/advanced/translate-documents
- Microsoft Azure Document Translation: https://learn.microsoft.com/en-us/azure/ai-services/translator/document-translation/

### Caveats / Not Verified
- **PyPI vs GitHub version mismatch for pdf2zh-next**: PyPI shows 2.9.0 (May 2026); the org `PDFMathTranslate-next` is the true upstream. I scraped pyproject.toml from there and confirmed; the confusion is real because there's a separate org `PDFMathTranslate` (without hyphen) that hosts the legacy v1.x and a stale `-next` mirror.
- **Apple Silicon support** — NOT verified; the `hyperscan` dep is suspect. Test before committing to Mac support.
- **AGPL "linking via subprocess" legal question** — I am not a lawyer; consult one if monetization is planned. The conservative read is that AGPL covers subprocess use too if the subprocess is "an integral part" of the offered service.
- **`do_translate_async_stream` event ordering** — I read the source; runtime behavior under cancellation may surface stage events out of order. Worth a small spike test.
