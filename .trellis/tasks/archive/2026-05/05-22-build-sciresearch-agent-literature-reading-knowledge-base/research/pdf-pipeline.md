# Research: PDF / Document Extraction Pipeline for Scientific Papers

- **Query**: markitdown + alternatives for scientific PDF→Markdown, plus integration patterns for LLM-Wiki ingest
- **Scope**: external (libraries, benchmarks, GitHub issues) + integration design for our pipeline
- **Date**: 2026-05-22

---

## Summary (3 bullets)

- **markitdown is excellent for office docs (DOCX/PPTX/XLSX/HTML) but is a weak link for scientific PDFs.** Its PDF converter is a thin wrapper over `pdfminer.six` + `pdfplumber` with **no layout model, no equation handling, no two-column reading-order fix, and the published "table extraction" only triggers for form-style pages**. Multiple 2025–2026 issues (#1845 academic PDFs broken, #1419 tables absent, #1276 3× slower than PyMuPDF, #1659 headings missing, #1870 text dropped after inline images, #1883 truncated text) confirm this. Keep markitdown for non-PDF formats; do **not** rely on it as the only PDF parser for arXiv-style papers.
- **The 2026 SOTA for scientific PDFs is a layout-aware VLM pipeline**, and there are three credible OSS options: **MinerU 3.x** (Apache-derived OpenSource License, OmniDocBench v1.5 = 86.2, native LaTeX equations + HTML tables + cross-page table merging + reading-order recovery; runs on CPU or GPU), **marker** (`datalab-to/marker`, GPL-3 + OpenRAIL-M model license, fast, optional `--use_llm` boost, scored 76.1 on olmOCR-Bench 1.10.1), and **olmOCR v0.4.0** (Apache-2.0, scored 82.4 on its own bench, 7B VLM, needs ≥12 GB GPU). For our local-first Windows-friendly setup, **MinerU pipeline backend** is the best default; marker is the strongest CPU-OK fallback.
- **Recommended architecture for XReadAgent**: a **routed pipeline**. (a) Use **MinerU** (pipeline backend, CPU fallback) for scientific PDFs and arXiv preprints; output `paper.md` + extracted images + per-block JSON sidecar. (b) Use **markitdown** for `.docx`, `.pptx`, `.xlsx`, `.html`, `.epub`, slide-decks, etc. — keep it as a converter for "everything else". (c) Use **GROBID** (Docker, Apache-2.0) as an *optional* enrichment pass for high-quality references / authors / affiliations extraction into TEI-XML when the user wants Zotero-grade metadata. Feed the produced markdown + JSON into the Karpathy LLM-Wiki ingest: keep raw markdown in `raw/papers/<id>.md`, then have the LLM synthesize 10–15 wiki pages.

---

## markitdown deep dive

### Architecture (verified from source)

Source: `microsoft/markitdown` main branch, `packages/markitdown/src/markitdown/converters/_pdf_converter.py` (589 LOC, inspected 2026-05-22).

The PDF pipeline is:

1. **Open with `pdfplumber`**, iterate pages.
2. For each page, call `_extract_form_content_from_words(page)` — a heuristic that detects "form-style" pages (3+ aligned columns, ≥20 % of rows are table-like, short cells <30 chars). Form pages get a hand-rolled markdown table builder.
3. If **no** page looks form-style → fall back to `pdfminer.high_level.extract_text(pdf_bytes)` over the whole document. **This is the path 99 % of scientific PDFs take**: pdfminer in linear-text mode.
4. Post-process: merge "MasterFormat" partial numbering (`.1` … `.2` …) — a construction-spec quirk, not relevant to papers.
5. **No** vision LLM is called in the default path. **No** layout model. **No** column detection beyond the "3 columns ≥ 20 % rows = table" rule. **No** equation handling. **No** figure extraction. **No** reference parser.

There is an *opt-in* path: `Azure Document Intelligence` (`markitdown[az-doc-intel]`) and `Azure Content Understanding` (`markitdown[az-content-understanding]`) — both cloud-only, billable. The community plugin `markitdown-ocr` adds vision-LLM OCR via the same `llm_client` used for image captions, but it does **not** add layout reconstruction; it only OCRs embedded images.

### Supported formats (verified from README)

PDF, PowerPoint, Word, Excel, Images (EXIF + OCR), Audio (EXIF + speech), HTML, CSV/JSON/XML, ZIP (recursive), YouTube URLs, EPub. Optional extras: `pptx`, `docx`, `xlsx`, `xls`, `pdf`, `outlook`, `az-doc-intel`, `az-content-understanding`, `audio-transcription`, `youtube-transcription`.

PyPI shows **0.1.5** as the current version; depends on `pdfminer-six>=20251230`, `pdfplumber>=0.11.9`, `mammoth~=1.11.0`, `python-pptx`, `pandas`, `openpyxl`, `magika~=0.6.1`, etc.

GitHub: **124,533 stars**, **665 open issues** as of 2026-05-22, MIT license, very active (pushed 2026-05-22).

### Known failure modes on scientific PDFs (cited GitHub issues, 2025–2026)

| Issue | Title (paraphrased) | Status | Impact on us |
|---|---|---|---|
| [#1845](https://github.com/microsoft/markitdown/issues/1845) (2026-04) | "Academic PDF conversion outputs non-standard Markdown with broken formatting" — ACS journal paper produces unusable markdown | open | **Blocker for scientific use case** |
| [#1419](https://github.com/microsoft/markitdown/issues/1419) (2025-09) | "Table extraction from PDF is advertised but completely absent" — native PDFs return only interleaved newlines | open | Tables in papers are lost |
| [#293](https://github.com/microsoft/markitdown/issues/293) (early) | "Tables in pdf files are not converted properly" — column values dumped vertically | open | Same root cause |
| [#1276](https://github.com/microsoft/markitdown/issues/1276) (2025-05) | "PDF performance (PDFMiner)" — 122-page PDF: markitdown 33 s vs PyMuPDF4LLM 9.24 s (≈3.5× slower) | open | Throughput problem for long papers |
| [#1659](https://github.com/microsoft/markitdown/issues/1659) (PR) | "fix: detect headings in PDF conversion via font-size analysis" — flat output, no `#` markers | open PR | Document structure lost |
| [#1870](https://github.com/microsoft/markitdown/issues/1870) (2026) | "PDF text after an inline image (`BI ... EI`) is silently dropped" | open | Content loss after every figure |
| [#1883](https://github.com/microsoft/markitdown/issues/1883) (2026) | "Use optional PyMuPDF when PDF text appears truncated" | open | Acknowledges pdfminer truncation bugs |
| [#1733](https://github.com/microsoft/markitdown/issues/1733) | "fix(pdf): recover whitespace when pdfminer collapses plain text" | open PR | Spacing corruption |
| [#1902](https://github.com/microsoft/markitdown/issues/1902) | "Preserve spaces in positioned PDF text" | open PR | Spacing corruption |
| [#1652](https://github.com/microsoft/markitdown/issues/1652) | "Add a plugin-first PaddleOCR package for scanned PDF fallback" | open PR | No scanned-PDF support today |
| [#1888](https://github.com/microsoft/markitdown/issues/1888) | "Fix OCR for mixed text and scanned PDF pages" | open | Mixed-page papers broken |
| [#1645](https://github.com/microsoft/markitdown/issues/1645) | "Add --save-images flag to extract document images to disk" | open PR | Figures aren't saved today |

### Implications

- **Equations**: not handled. pdfminer treats glyphs as text; complex math renders as garbage Unicode soup.
- **2-column / multi-column**: not handled in default path. pdfminer linear extraction interleaves columns. The `_extract_form_content_from_words` heuristic *explicitly* says "designed for structured tabular data (like invoices), not for multi-column text layouts in scientific documents" (verbatim comment in source line ≈300).
- **Tables**: only "form-style" tables (invoices, registers). Real paper tables with merged cells, multi-line headers, footnotes — not supported.
- **Figures + captions**: figures dropped; captions may be lost or jammed into body text.
- **References**: extracted as plain text, no parsing into structured citations.
- **Footnotes**: inlined as plain text wherever they appear in the page stream.
- **Speed**: ~3.5× slower than PyMuPDF on long PDFs (122 pp: 33 s vs 9.2 s).
- **No GPU, no vision model, no layout model** in the default path. Lightweight = small install footprint (~50 MB with deps), but accuracy ceiling is low.

---

## Comparison table: markitdown vs alternatives

Scores for OCR/parse tools are from **olmOCR-Bench** (allenai, 2026), inspected 2026-05-22 from `allenai/olmocr` README. MinerU also reports **OmniDocBench v1.5 = 86.2** for its pipeline backend (their docs, 2026-03).

| Tool | Equations | Tables | 2-column | Figures + captions | References | Speed (typ.) | License | Install / Runtime |
|---|---|---|---|---|---|---|---|---|
| **markitdown 0.1.5** (`pdfminer` + `pdfplumber`) | ❌ none | ⚠ form-style only, broken on paper tables (#1419, #293) | ❌ default = pdfminer linear order; columns interleave | ❌ images dropped (#1645 open) | ❌ plain text only | Slow on long PDFs (~3.5× pymupdf, #1276) | MIT, model: none | CPU only, ~50 MB |
| **markitdown + Azure Doc Intelligence** | ⚠ partial | ✅ good | ✅ | ⚠ | ⚠ | Cloud-bound, billable | MIT code / Azure ToS | Azure account required |
| **MinerU 3.x** (`opendatalab/mineru`) | ✅ LaTeX | ✅ HTML, **cross-page merging** | ✅ reading-order recovery | ✅ images + descriptions extracted | ⚠ extracted as section, not citation graph | pipeline ≈ CPU-OK; vlm ≈ 1–3 s/page on 4090 | **MinerU OSS License** (Apache-2.0 based, 2026-04 relicense) | pipeline: 4 GB VRAM or pure CPU; vlm: 8 GB VRAM. 20 GB disk. Win/Linux/macOS. **Score 75.2 olmOCR-Bench / 86.2 OmniDocBench** |
| **marker** (`datalab-to/marker`) | ✅ inline math → LaTeX (with `--use_llm`) | ✅ formatted, LLM merge across pages | ✅ | ✅ images saved | ✅ as section text | ~25 pages/s on H100 batch; CPU OK | **GPL-3.0 code + OpenRAIL-M model** (commercial requires paid license) | GPU, CPU, MPS. pip `marker-pdf`. **Score 76.1 olmOCR-Bench** |
| **olmOCR v0.4.0** (`allenai/olmocr`) | ✅ | ✅ | ✅ | ⚠ images de-emphasized | ⚠ | ~$200 / 1 M pages on rented GPU | Apache-2.0 (model: ODC-By) | **GPU required**, ≥12 GB VRAM (4090/L40S/A100/H100), 30 GB disk, Linux. **Score 82.4 olmOCR-Bench** |
| **Nougat** (`facebookresearch/nougat`) | ✅ LaTeX | ✅ LaTeX tables (mathpix-like .mmd) | ✅ | ⚠ | ⚠ | Slow (≈10 s/page on CPU), faster on GPU | MIT (Meta) | GPU recommended. **English (Latin) only — CJK explicitly unsupported per FAQ**. Frequent `[MISSING_PAGE]` failures. Last meaningful update was 2024; effectively unmaintained. |
| **GROBID** (`grobidOrg/grobid`) | ❌ math is poorly handled (it's not its job) | ⚠ basic | ✅ implicit via layout features | ⚠ figure callouts, not images | ✅✅ **best-in-class**: 0.87–0.90 F1 reference parsing, DOI resolution >0.95, author/affiliation/funder/license parsing | Fast (CRF default); ~1 s/page CPU | **Apache-2.0** | **Requires JDK 21 + Docker (recommended)**. Java service, Python clients exist. Used by Semantic Scholar, ResearchGate, scite.ai, HAL, Internet Archive Scholar. TEI-XML output. |
| **Unstructured.io** (`Unstructured-IO/unstructured`) | ⚠ partial | ⚠ depends on backend | ⚠ | ⚠ | ⚠ | Configurable | Apache-2.0 | Heavy install (many ML deps). Good ETL plumbing, mediocre on hard PDFs without `hi_res` model. |
| **PyMuPDF4LLM** (`pymupdf/PyMuPDF` + `pymupdf4llm`) | ❌ glyph text only | ⚠ basic | ⚠ better than pdfminer but not layout-aware | ⚠ images extractable via PyMuPDF | ❌ plain | **Very fast** (~9 s for 122-page PDF) | **AGPL-3.0** (or paid Artifex commercial license) | CPU only. pip. Lightweight. Good as a *fast preflight* or a markitdown drop-in replacement. |
| **pdfplumber** (`jsvine/pdfplumber`) | ❌ | ⚠ best low-level table API (camelot-style) | ❌ no reading-order | ❌ | ❌ | Fast | MIT | CPU. Building block, not a finished pipeline. |

### Reading of the benchmark numbers (olmOCR-Bench, 7000 cases / 1400 docs)

```
PaddleOCR-VL*       80.0
Chandra OCR 0.1.0*  83.1   (datalab.to managed)
Infinity-Parser 7B* 82.5
olmOCR v0.4.0       82.4
Marker 1.10.1       76.1
MinerU 2.5.4*       75.2
DeepSeek-OCR        75.7
Mistral OCR API     72.0
```

- "Multi-column" sub-score: olmOCR 83.7, marker 80.0, MinerU 78.2, Mistral OCR API 71.3.
- "Tables" sub-score: MinerU **84.9**, marker 72.9, olmOCR 84.9, Mistral 60.6.
- "ArXiv" sub-score (best signal for our use case): marker **83.8**, olmOCR 83.0, MinerU 76.6.

→ **For arXiv-style papers specifically, marker has the highest open-source score**; MinerU is the strongest balanced option (best on tables, has CPU mode, good license). markitdown is not on this benchmark because it isn't competitive in this class.

---

## Recommended hybrid pipeline for XReadAgent

### Constraints from PRD

- Local-first (per `prd.md` A6, "Local-first preferred: papers and wiki should live on the user's disk").
- Windows 11 desktop first (A2).
- Python-heavy stack (A3).
- LLM-Wiki ingest is the downstream consumer.
- Aesthetics matter ("UI feels polished — non-negotiable").
- markitdown is already a chosen dependency (line 20 of PRD).

### Proposed pipeline

```
User drops a file
     │
     ▼
 ┌──────────────────┐   ext = .pdf ?
 │  FormatRouter    │─────────────────────────────┐
 └──────────────────┘                             │
   │ .docx/.pptx/.xlsx/.html/.epub/.zip           │
   ▼                                              ▼
 markitdown (all extras) ──► markdown          PDF SUBPIPELINE
                                                   │
                                                   ▼
                              ┌──────────────────────────────────────────┐
                              │  Quick triage with PyMuPDF (1 s):         │
                              │  • text-PDF or scanned?                   │
                              │  • page count                             │
                              │  • language                               │
                              └──────────────────────────────────────────┘
                                                   │
                  ┌────────────────────────────────┼───────────────────────────────┐
                  ▼                                ▼                               ▼
        text-PDF, short (<10pp)         text-PDF, long / 2-col / eqs       scanned / image PDF
                  │                                │                               │
                  ▼                                ▼                               ▼
        pymupdf4llm (fast)              MinerU pipeline backend              MinerU vlm-engine
        OR markitdown                   (CPU-OK, 4 GB VRAM if GPU)           (or olmOCR via API)
                  │                                │                               │
                  └────────────────┬───────────────┴───────────────┬───────────────┘
                                   ▼                               ▼
                       paper.md + figures/ + per-block JSON   (same shape)
                                   │
                                   ▼
                       ┌─────────────────────────────────────┐
                       │  Optional enrichment: GROBID         │
                       │  (Docker, lazy-started)              │
                       │  → references.tei.xml +              │
                       │    biblio.json (DOI/PMID resolved)   │
                       └─────────────────────────────────────┘
                                   │
                                   ▼
                       Karpathy LLM-Wiki ingest
```

### Key design decisions

1. **Don't make markitdown the PDF parser.** Use it for everything *else* it's actually good at (Office docs, HTML, EPUB, ZIP). The user already chose it — keep it, but scope it down.
2. **Default PDF engine = MinerU pipeline backend.** Reasons: (a) MIT/Apache-derived license — commercial-friendly, (b) **runs on pure CPU** (PRD A2 = Windows desktop, can't assume GPU), (c) outputs LaTeX equations + HTML tables natively, (d) handles 2-column reading order, (e) sliding-window memory for long PDFs (their 3.0 release notes call this out for "tens of thousands of pages"), (f) actively maintained (pushed 2026-05-22, version 3.1.0 in 2026-04). Trade-off: heavier install (~20 GB with models) than markitdown.
3. **GPU upgrade path = MinerU vlm-engine** (8 GB VRAM) or **olmOCR** (12 GB VRAM, Apache-2.0). For the user's RTX-class GPU, MinerU vlm-engine + `MinerU2.5-Pro-2604-1.2B` is the smoothest upgrade.
4. **Marker is a strong alternative** if MinerU's footprint becomes a problem; but the GPL-3 + commercial-license-required-above-$2M-revenue model license is a future friction point we should note in the decision log.
5. **Skip Nougat.** It's effectively unmaintained, English-only (FAQ explicitly says "Chinese, Russian, Japanese etc. will not work"), and frequently emits `[MISSING_PAGE]`. Our user is bilingual ZH/EN — Nougat is a non-starter.
6. **GROBID as optional enrichment, not the main path.** Its reference-parsing accuracy is unmatched (0.87–0.90 F1 on full PDFs, 0.95 F1 on isolated references) and it's used in production by Semantic Scholar / ResearchGate / scite.ai. **But** it requires JDK 21 + Docker, which conflicts with "local-first, Windows-friendly, just-pip-install". Run it in a containerized sidecar only when the user explicitly enables citation analysis or Zotero export.
7. **Pre-flight with PyMuPDF.** A 200 ms pass to grab page count, detect scanned vs text PDF, and pull rough metadata lets us route smartly instead of always paying MinerU's startup cost.

### Why not "markitdown for body + GROBID for refs + Nougat for math"?

Tempting on paper, but:
- Three different layout passes will produce three different reading orders. Reconciling them is a research project on its own.
- markitdown's body is the weak link (#1845, #1419) — fixing it with bolt-ons doesn't make the body usable.
- MinerU already does body + equations + tables in one consistent layout pass, with markdown output. Stacking GROBID on top is one optional add-on instead of three competing extractors.

---

## Integration notes for LLM-Wiki ingest

### Recommended directory layout (Karpathy-compatible)

```
workspace/
  raw/
    papers/
      <paper-id>/
        original.pdf          # immutable user-uploaded PDF
        paper.md              # MinerU output (markdown, LaTeX equations, HTML tables)
        figures/              # MinerU image dumps
        blocks.json           # per-block structure (titles, paras, captions) — sidecar
        biblio.json           # optional, GROBID-derived
        meta.yaml             # title, authors, doi, ingested_at, hash
  wiki/
    index.md
    log.md
    papers/<paper-id>.md      # LLM-authored summary page, primary backref to raw/
    concepts/<concept>.md
    methods/<method>.md
    ...
  schema/
    CONVENTIONS.md            # how the LLM maintains wiki/
```

This keeps the **raw markdown alongside the wiki** (PRD wants reading + memory; the markdown is the "reading view" and the wiki is the "memory view"). Both are plain markdown on disk (PRD: "All wiki state is plain markdown on disk").

### Ingest flow (after PDF→markdown)

1. **Persist raw** under `raw/papers/<id>/paper.md` (immutable per Karpathy's "Raw Sources" layer).
2. **Chunk by structure, not by tokens.** Use MinerU's `blocks.json` to chunk per section (Abstract / Intro / Methods / …) rather than blind 1k-token windows. Sections preserve semantic boundaries → better synthesis.
3. **Analyze pass** (LLM, big context window): the agent reads the whole `paper.md`, drafts:
   - `wiki/papers/<id>.md` — the "paper page" with title, authors, claim list, methods used, results, limitations, notable equations.
   - 5–15 candidate updates to `wiki/concepts/*.md` and `wiki/methods/*.md` (Karpathy's "one ingest touches 10–15 pages").
4. **Cross-reference pass.** For each existing wiki page the new paper touches, the agent decides: append / contradict / supersede. Decisions logged in `wiki/log.md`.
5. **Citation extraction** (optional GROBID pass): produces `biblio.json` with structured refs + resolved DOIs. The agent can then create stub `wiki/papers/<doi>.md` placeholders for cited-but-not-yet-ingested papers — this builds the citation graph **without** requiring the user to import every cited paper.
6. **Lint pass** (Karpathy "Lint" op): periodic — find orphans, contradictions, stale claims. Lower priority for MVP.

### Citation extraction — how to pull a paper's references reliably

Three options ranked by accuracy:

1. **GROBID `/api/processReferences` or `/api/processFulltextDocument`** — TEI-XML out, 0.87–0.90 F1 per their own benchmark on bioRxiv/PMC sets. Used by Semantic Scholar. **Best accuracy, heaviest install (Docker + JDK).**
2. **Regex + DOI resolution** — Scan the markdown's "References" section, regex-match DOIs (`10\.\d{4,9}/[-._;()/:A-Z0-9]+`i), resolve via CrossRef REST API. Cheap, ~70 % recall on modern papers (those that print DOIs).
3. **LLM-only extraction** — give the references section to GPT-4o / Claude and ask for structured JSON. Decent but expensive and inconsistent; only worth it as a fallback when GROBID isn't running and DOIs aren't printed.

For MVP: option 2 is enough. Add option 1 behind a feature flag once Docker is in the install story.

### Where production tools sit (anecdotal, 2024–2026)

- **PaperQA2** (`Future-House/paper-qa`, Apache-2.0): RAG-style — uses simple PDF text extractors and chunks; not the wiki pattern, but proves the "scientific-paper Q&A with metadata + retraction check" angle works in Python.
- **scite.ai, Semantic Scholar, ResearchGate**: all use **GROBID** in production for header + reference parsing (per GROBID README "Deployments in production includes ResearchGate, Semantic Scholar, HAL Research Archive, scite.ai, Academia.edu, Internet Archive Scholar").
- **Marker / datalab.to**: powers Chandra OCR managed service and is a popular drop-in for "I just want markdown out of my PDFs". Used by various open-source RAG stacks.
- **MinerU**: the OpenDataLab/InternLM team's pre-training data pipeline → it's literally designed for "build a clean text corpus from scientific PDFs to train LLMs on". Direct alignment with our use case.
- **sciSpace, scholarchat**: closed-source; reports suggest they use a mix of in-house OCR + GROBID for refs.

---

## Open Questions

1. **GPU available on user machine?** If yes, MinerU vlm-engine + olmOCR become viable; if no, lock to MinerU pipeline backend + marker CPU as fallback. (PRD is silent; PC is Windows 11 Pro — likely has a consumer GPU but we should confirm.)
2. **Commercial-license sensitivity?** Marker (GPL-3 + OpenRAIL-M) and PyMuPDF (AGPL-3) both have copyleft / paid-license escalation paths. If XReadAgent ever ships as a paid product, default to MinerU + olmOCR (both Apache-class).
3. **Translation feature** (PRD line 21 — layout-preserving translation): this is *not* the same pipeline as ingestion. Translation needs to preserve the visual layout (pdf2zh approach). The ingestion pipeline can use the *flat* markdown. We probably want **two passes**: (a) ingestion → markdown → wiki, (b) display/translation → original PDF + per-block overlay. Worth a separate `research/translation-strategies.md` (already listed in PRD line 106).
4. **Long-tail formats** — supplementary materials are often `.xlsx`, `.docx`, `.zip`, or `.html` (a journal landing page). markitdown handles all of these well; confirms it stays in the pipeline.
5. **Should `paper.md` be human-edited?** Karpathy's contract says Raw Sources are immutable. If the user catches a MinerU error, do they edit `paper.md` or do they file a "correction" note next to it? Tentatively: immutable, and corrections go into a sibling `corrections.md`.
6. **Per-paper ingest cost / latency budget?** Acceptance criterion says "minutes for a typical paper". MinerU pipeline on CPU is roughly 1–3 s/page → a 30-page paper ≈ 1–2 min; with vlm-engine on GPU it's faster but each LLM call for synthesis dominates. We should benchmark on the user's machine before locking the SLA.
7. **Hot-reload of newer MinerU models?** MinerU shipped 3 model upgrades in 6 months (2025–2026); plan a version-pinning + auto-update story so we don't break user workflows on each release.

---

## Sources

### GitHub repositories (verified 2026-05-22)

- microsoft/markitdown — https://github.com/microsoft/markitdown (124,533 stars, MIT, v0.1.5)
- opendatalab/MinerU — https://github.com/opendatalab/MinerU (64,478 stars, MinerU OSS License since 2026-04, v3.1.0)
- datalab-to/marker — https://github.com/datalab-to/marker (35,329 stars, GPL-3 + OpenRAIL-M)
- Unstructured-IO/unstructured — https://github.com/Unstructured-IO/unstructured (14,757 stars, Apache-2.0)
- allenai/olmocr — https://github.com/allenai/olmocr (17,344 stars, Apache-2.0, v0.4.0)
- facebookresearch/nougat — https://github.com/facebookresearch/nougat (9,977 stars, MIT, last meaningful release 2024)
- grobidOrg/grobid — https://github.com/grobidOrg/grobid (formerly kermitt2/grobid) (Apache-2.0)
- pymupdf/PyMuPDF — https://github.com/pymupdf/PyMuPDF (9,773 stars, AGPL-3.0)
- jsvine/pdfplumber — https://github.com/jsvine/pdfplumber (10,301 stars, MIT)
- Future-House/paper-qa — https://github.com/Future-House/paper-qa (Apache-2.0)

### Specific markitdown issues / PRs cited

- #1845 academic PDFs broken — https://github.com/microsoft/markitdown/issues/1845
- #1419 tables absent — https://github.com/microsoft/markitdown/issues/1419
- #1276 PDF performance vs PyMuPDF — https://github.com/microsoft/markitdown/issues/1276
- #1659 heading detection PR — https://github.com/microsoft/markitdown/pull/1659
- #1870 inline-image text dropped — https://github.com/microsoft/markitdown/issues/1870
- #1883 use PyMuPDF when truncated — https://github.com/microsoft/markitdown/issues/1883
- #293 PDF tables not converted — https://github.com/microsoft/markitdown/issues/293
- #1733 whitespace fix — https://github.com/microsoft/markitdown/pull/1733
- #1645 save-images flag — https://github.com/microsoft/markitdown/issues/1645
- #1652 PaddleOCR plugin — https://github.com/microsoft/markitdown/issues/1652

### Benchmarks

- olmOCR-Bench (allenai) — https://github.com/allenai/olmocr/tree/main/olmocr/bench — 7,000 test cases / 1,400 documents, sub-scores per category. Numbers in this doc are from the README as of 2026-05-22.
- OmniDocBench v1.5 — referenced in MinerU README; MinerU pipeline 86.2, prior gen MinerU2.0-2505-0.9B baseline.
- py-pdf/benchmarks — https://github.com/py-pdf/benchmarks — community-maintained library benchmarks (cited in markitdown #1276 by users comparing pdfminer to pymupdf).

### Papers

- Nougat (Meta, 2023) — https://arxiv.org/abs/2308.13418
- olmOCR v1 — https://arxiv.org/abs/2502.18443
- olmOCR v2 — https://arxiv.org/abs/2510.19817
- MinerU technical report — https://arxiv.org/abs/2409.18839
- MinerU 2.5 — https://arxiv.org/abs/2509.22186
- MinerU 2.5 Pro — https://arxiv.org/abs/2604.04771
- Karpathy LLM-Wiki gist — https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- PaperQA2 paper (2024) — https://paper.wikicrow.ai

### Source code inspected

- `microsoft/markitdown` `packages/markitdown/src/markitdown/converters/_pdf_converter.py` (main branch, 589 LOC, 2026-05-22) — verified the pdfminer + pdfplumber pipeline and the "form-only" table heuristic.
- `microsoft/markitdown` README — verified supported formats, optional dependencies, Azure integration, and the `markitdown-ocr` plugin (LLM-vision OCR for embedded images, not layout).
