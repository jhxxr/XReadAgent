# XReadAgent — Complete Plan & Risk Assessment

> Synthesized from 5 parallel research deep-dives (see `research/`).
> Date: 2026-05-22.

---

## 0. One-Screen TL;DR

**What we're building**: A Windows-first (macOS soon-after) Python desktop app where researchers drop in papers and get back a **compounding LLM-Wiki** (Karpathy pattern) plus layout-preserving translation. The agent isn't a chatbot over PDFs — it's a disciplined wiki maintainer that touches 10–15 markdown pages per ingested paper, so synthesis happens **once** and compounds.

**Recommended stack** (each line below has a sound research basis; decisions you can override are listed in §5):

| Layer | Choice | Why |
|---|---|---|
| Agent harness | **`langchain-ai/deepagents`** on LangChain 1.x | Purpose-built for "agent edits files in a folder"; planning + subagents + virtual-FS middleware out of the box. 23k★ MIT, May 2026. |
| Provider abstraction | Thin `LLMGateway` + Pydantic 2 schemas | Avoid coupling to LangChain types in domain code. |
| Typed sub-pipelines | **Pydantic AI 1.x** (pin, 2.0 betas land 2026-05-21) | Best-in-class type safety; use for translation worker, metadata extractor. |
| Memory model | **Karpathy LLM-Wiki** with 4 page types + `queries/` isolation | Pure-agentic Tier 1 (works to ~300 papers); embed only as Tier 2 *tool*, not primary memory. |
| Vector tier (optional v2) | **`sqlite-vec` + FTS5** | Single-file, no daemon, hybrid BM25+vector matches `Awareness-Local`/`echovault`. Or shell out to **`qmd`** via MCP. |
| Document → markdown | **Routed pipeline**: MinerU 3.x for PDFs, markitdown for DOCX/PPTX/XLSX/HTML | markitdown's PDF path = pdfminer.six + pdfplumber, no equations/2-col/figures (proven by GH #1845, #1419, #1276, #1659, #1870, #1883). MinerU has best-balanced scores (OmniDocBench 86.2, tables 84.9). |
| Reference parsing (opt-in) | **GROBID** via Docker | Best-in-class (F1 0.87–0.90 on refs); Apache-2.0; behind a feature flag because JDK 21 + Docker. |
| Layout translation | **`babeldoc==0.6.2`** in subprocess via `ProcessPoolExecutor` | The actual engine. `pdf2zh-next` is a translator-router shell we don't need. ⚠ AGPL-3.0. |
| UI dev mode (4–6 wks) | **FastAPI + React/Vite/shadcn in browser tab** | Iterate on agent quality without Electron build pain. |
| UI production | **Electron + Python sidecar (HTTP/WS over loopback)** | Largest precedent (Cursor, Reor, Cherry Studio, LM Studio). Python venv dwarfs Electron anyway. |
| Distribution | `electron-builder` + `python-build-standalone` + `electron-updater` | Standard 2026 stack. |
| MCP exposure | Yes — wiki tools also available over MCP server | Karpathy community has converged on Claude Code Skills; expose to capture that audience. Free with `deepagents`. |
| Telemetry | LangSmith free tier or Pydantic Logfire (opt-in) | One env var to enable; off by default for local-first. |

---

## 1. Architecture (system view)

```
┌───────────────────────────────────────────────────────────────┐
│ Electron renderer  ── React/Vite/shadcn ── PDF.js dual-column │
│  reader · sidebar copilot · wiki browser · settings · trans.  │
└──────────────────────────────┬────────────────────────────────┘
                ┌──────────────┼──────────────┐
                │ HTTP/WS over 127.0.0.1:port │
                ▼              ▼              ▼
┌───────────────────────────────────────────────────────────────┐
│ Python sidecar (uvicorn + FastAPI, started by Electron main)  │
│ ┌─────────────────────────────────────────────────────────┐   │
│ │ Agent layer (deepagents on LangChain 1.x)               │   │
│ │   ingest / query / lint / crystallize sub-agents        │   │
│ │   ▸ wiki_tools: read / write / search / link            │   │
│ │   ▸ source_tools: convert / extract / glossary          │   │
│ │   ▸ translation_tools: babeldoc subprocess wrapper      │   │
│ └─────────────────────────────────────────────────────────┘   │
│ ┌─────────────────────────────────────────────────────────┐   │
│ │ LLMGateway (provider-agnostic; OpenAI-compat / Anthr /  │   │
│ │   Gemini / Ollama / custom; budget + rate-limit + cache)│   │
│ └─────────────────────────────────────────────────────────┘   │
│ ┌─────────────────────────────────────────────────────────┐   │
│ │ Document pipeline (routed)                              │   │
│ │   PDF → MinerU 3.x pipeline backend                     │   │
│ │   DOCX/PPTX/XLSX/HTML → markitdown                      │   │
│ │   refs (opt.) → GROBID Docker side-car                  │   │
│ └─────────────────────────────────────────────────────────┘   │
│ ┌─────────────────────────────────────────────────────────┐   │
│ │ Translation worker (ProcessPoolExecutor)                │   │
│ │   babeldoc 0.6.2 — events streamed back over WS         │   │
│ └─────────────────────────────────────────────────────────┘   │
│ ┌─────────────────────────────────────────────────────────┐   │
│ │ MCP server (optional, opt-in) — same tools, second face │   │
│ └─────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬────────────────────────────────┘
                               ▼
                ┌──────────────────────────────┐
                │ Workspace on disk            │
                │  raw/ · raw/_processed/      │
                │  extracts/                   │
                │  state/ (json sidecars)      │
                │  wiki/ (index, log, papers,  │
                │         concepts, queries,   │
                │         open-questions)      │
                └──────────────────────────────┘
```

---

## 2. LLM-Wiki — the memory core (most-differentiating subsystem)

### 2.1 Directory contract (inherits OpenSciReader + adds `queries/` isolation)

```
{workspace}/
├── raw/                       Immutable. Original sources.
│   └── _processed/            Post-ingest archive (presence = ingested).
├── extracts/                  MinerU/markitdown output (one .md per source).
├── state/                     Machine-readable distillation. Recomputable from raw.
│   ├── sources.json           Manifest with contentHash for idempotent re-scan.
│   ├── by-source/{slug}.json  {entities, claims, relations, tasks} per paper.
│   ├── compile-summary.json   "is wiki dirty" bookkeeping.
│   └── conversation-log.jsonl Append-only query/promotion log.
└── wiki/                      Human-readable. LLM-owned. The compounding artifact.
    ├── index.md               Auto-regenerated catalog.
    ├── log.md                 Chronological, append-only.
    ├── overview.md            Workspace-level synthesis.
    ├── open-questions.md      Aggregated from state/tasks.json.
    ├── hot.md                 OPTIONAL session-handoff cache (claude-obsidian).
    ├── papers/{slug}.md       Per-source page.
    ├── concepts/{slug}.md     Per-entity page.
    └── queries/{topic}/...    Archived Q&A — ISOLATED from index/log.
```

### 2.2 Page templates (borrow from `obsidian-paper-curator`)

- **Paper**: Background / Challenges / Solution / Positioning / Key Concepts / Experiments / Open Questions
- **Concept**: Summary / Related Papers / Related Claims / Open Questions
- **Query**: Question / Answer / Sources (never auto-fed back to synthesis)

Frontmatter on every page: `page_type`, `source_hash`, `reliability` (`high|medium|low`), `aliases[]` (concept pages), `topics[]`. Links via Obsidian-style `[[wiki-link]]`.

### 2.3 Three operations

- **Ingest**: PDF → MinerU → extract → LLM read → propose diffs across 10-15 wiki pages → write. Single-pass (vs OpenSciReader's two-LLM-call render — cost ~½). Per-source JSON sidecar regenerated lazily for audit/recompile.
- **Query**: Agent reads `index.md` → drills into ≤5 pages → answers with citations → archives to `wiki/queries/{topic}/{date}-{slug}.md`. **Never writes back into `papers/` or `concepts/`** without explicit user crystallize command. (paper-curator's anti-hallucination discipline.)
- **Lint**: Periodic agent pass — detect orphans (graph traversal), contradictions (LLM diff over claim pairs), staleness (timestamps). Optional `lint_scan.py` static check borrowed from paper-curator.
- **Crystallize** (`/crystallize` from `llm-wiki-skills`): user-invoked promotion from a query archive into the wiki. Replaces OpenSciReader's auto-promote.

### 2.4 Disambiguation & idempotency

- Paper slug = `kebab(title) + '-' + sha256_12(stable_key)` — directly from OpenSciReader `workspace_wiki_service.go:1227-1240`.
- Entity slug = `kebab(canonical_name)`, with `aliases[]` array merged at ingest time.
- `contentHash` on each source — re-running ingest on unchanged content is a no-op.

### 2.5 Retrieval ladder (Tier 1 ships; Tier 2 deferred)

1. **Tier 1 (agentic)**: read `index.md` → grep → drill. Validated to ~300 papers in prior art.
2. **Tier 2 (embedding, optional)**: `sqlite-vec` + FTS5 hybrid as a *tool the LLM may call when it deems navigation insufficient*. Never primary memory.
3. **Tier 3 (web fallback)**: optional, opt-in, for unknown concepts.

---

## 3. Translation subsystem (BabelDOC)

- Depend on `babeldoc==0.6.2` directly (NOT `pdf2zh-next` — adds 11 unused translator backends).
- 13-stage pipeline preserves layout via DocLayout-YOLO ONNX + per-paragraph bbox text rewrite + CJK font subset (no LaTeX rebuild).
- Run in `ProcessPoolExecutor` worker (BabelDOC's reference impl does this too — `_translate_in_subprocess`).
- Stream stage events back to UI over WebSocket: `progress_start` / `progress_update` / `progress_end` / `finish` (with `TranslateResult.mono_pdf_path` + `dual_pdf_path`) / `error`.
- mono + dual export built-in via `TranslationConfig.no_mono / no_dual / use_alternating_pages_dual`.
- Lazy-download model assets on first translation (~50 MB ONNX + ~30–80 MB CJK fonts) with "Preparing translation engine…" UX.
- Version pin tight — BabelDOC officially says "all APIs internal." Treat upgrades as breaking-change events; gate them on a smoke-test PDF suite.

### 3.1 Hard constraint — AGPL-3.0

Both BabelDOC and pdf2zh-next are AGPL-3.0. Calling it from a server that serves remote users triggers AGPL's network clause. **Three valid distribution models**, you must pick:

1. **XReadAgent itself ships as AGPL** — clean, indie-friendly, no legal review needed.
2. **BabelDOC ships as an optional plug-in the user installs themselves** ("download translation pack on first use"). The app proper stays under your chosen license.
3. **Negotiate commercial license with funstory-ai** (Immersive Translate sponsors them and sells this).

---

## 4. PDF/document pipeline (the routed default)

| Input | Engine | Output |
|---|---|---|
| `.pdf` (default) | **MinerU 3.x pipeline backend** | `paper.md` + `images/` + `blocks.json` |
| `.pdf` (Apple Silicon CPU) | MinerU pipeline-mode CPU fallback OR PyMuPDF4LLM* | same shape |
| `.docx` / `.pptx` / `.xlsx` / `.html` / `.epub` | **markitdown 0.1.5** | `source.md` |
| References enrichment (opt.) | **GROBID** via Docker | TEI-XML → merged into paper metadata |
| Scanned-only PDFs | MinerU pipeline mode (has OCR) | `paper.md` |

*PyMuPDF4LLM is AGPL-3 / paid Artifex — only use it if you've already chosen AGPL distribution.

Footprint warning: MinerU is **~20 GB on disk** with models + deps. First-run experience needs care; suggest deferring model download until first PDF ingest, with a clear "Preparing PDF engine…" step.

---

## 5. Agent layer (deepagents on LangChain 1.x)

- `create_agent(model, tools, system_prompt)` factory — one provider string (`anthropic:claude-sonnet-4-6` / `openai:gpt-5.4` / `ollama:...`) swaps the backend.
- `deepagents` adds the right primitives: `write_todos` planning tool, `write_file` / `edit_file` / `read_file` over a pluggable FS backend (real disk for us), sub-agent spawn with isolated context, long-context offload to disk.
- Subgraphs: a deterministic ingest pipeline (PDF → MinerU → propose diffs → human review → apply) can be a **LangGraph** subgraph beneath the Deep Agent top loop for resumability when the user drops 50 PDFs at once.
- Domain code (the wiki tools, the LLMGateway, the structured ingest schemas) is **plain Python + Pydantic 2**, no LangChain types leaked into it. If LangChain ever flames out, we keep the engine.
- MCP exposure via FastMCP — same tools, second face. Karpathy's whole community is on Claude Code Skills; exposing MCP lets power users drive XReadAgent's wiki engine from their existing agent of choice. Essentially free.

---

## 6. UI shell

### 6.1 Phased approach

**Weeks 1–6 — dev mode**: FastAPI + React/Vite/shadcn served via Vite dev server in browser. No Electron, no signing, no installer. Iterate on agent quality + wiki schema.

**Weeks 7+ — production shell**: Wrap the same React app in Electron. The Python sidecar is started by Electron main via `child_process.spawn`, binds `127.0.0.1:<random>`, prints `SIDECAR_READY port=…` on stdout, polled for `/healthz`. Distribution via `electron-builder` (NSIS on Windows, DMG on macOS, AppImage on Linux). Auto-update via `electron-updater`.

### 6.2 Don't bundle heavy weights

The Electron+Python idle footprint is ~120–180 MB / ~150–300 MB RAM. The Python venv with MinerU + BabelDOC + deepagents + transformers is 1–3 GB **on its own** — Electron is not the bottleneck. **First-run download** of MinerU models + BabelDOC assets keeps the installer ~200 MB instead of multi-GB. Pattern lifted from Reor / LM Studio / Ollama.

### 6.3 Windows code-signing (2024+ rule change)

Microsoft requires EV / OV code-signing certs to be on HSM-backed hardware. Affects CI plans — Azure Trusted Signing (~$10/mo) is the easiest indie route. Plan for the cert procurement upfront if you want SmartScreen to stop nagging.

---

## 7. Critical risks (the "what's not good" list)

Severity: 🔴 product-blocking · 🟠 architectural · 🟡 operational · 🟢 cosmetic.

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | **BabelDOC is AGPL-3.0** — closed-source SaaS distribution is legally ambiguous to outright blocked. | 🔴 | Pick a distribution model in §5 / D1. |
| R2 | **markitdown alone is wrong for scientific PDFs** — broken equations, broken 2-column, broken tables, content loss after inline images (GH issues confirm). | 🔴 | Use MinerU for PDFs. markitdown stays as the DOCX/PPTX/XLSX/HTML converter. |
| R3 | **MinerU adds ~20 GB on disk** with full model set. First-run UX could be brutal. | 🟠 | Deferred / on-demand model download. Show clear progress in UI. |
| R4 | **BabelDOC officially declares all APIs "internal"** — upgrades can break us. | 🟠 | Tight version pin; smoke-test PDF suite gates upgrades; subprocess wrapper isolates blast radius. |
| R5 | **Apple Silicon unverified** for BabelDOC (`hyperscan` is x86-only); MinerU's GPU acceleration is CUDA/DirectML, not MPS. | 🟠 | Verify with `uv pip install --dry-run` on M-series before promising macOS at v1. Possible workaround: `vectorscan`. |
| R6 | **Two contradictory recommendations on `promote`** — research recommends drop OpenSciReader's auto-promote and use `/crystallize` instead; user implicitly wanted OpenSciReader's promote behavior. | 🟠 | D5 decision below. |
| R7 | **deepagents is young (23k★ but <12 months)** — small risk of stewardship gaps. | 🟡 | Domain code stays framework-agnostic; deepagents can be swapped for hand-rolled `create_agent` + custom tools if needed. |
| R8 | **Pydantic AI 2.0 betas started 2026-05-21** — migration whiplash if you grab `latest`. | 🟡 | Pin to 1.x; watch the migration guide. |
| R9 | **Windows code signing requires HSM-backed cert** since 2024. | 🟡 | Azure Trusted Signing ~$10/mo; budget for it before public release. |
| R10 | **Karpathy LLM-Wiki has commoditized in Claude Code Skills.** Top repos (`SamurAIGPT/llm-wiki-agent`, `AgriciDaniel/claude-obsidian`, `moonlarry/awesome-llm-paper-wiki`) are skills, not apps. XReadAgent's differentiation can't be "we built a wiki." | 🟠 | Lean into **polished UI + format-preserving translation + integrated PDF reader + own runtime**. Expose MCP to capture the skill-user audience without competing on substrate. |
| R11 | **PyMuPDF / pymupdf4llm AGPL-3** if used as fast preflight. | 🟡 | Stick to MinerU for the primary path; if PyMuPDF needed for image extraction, you've already chosen AGPL distribution anyway. |
| R12 | **marker is GPL-3 + OpenRAIL-M with a $2M revenue cap** — even FOSS users hit the OpenRAIL-M model-license fine print. | 🟡 | Don't pick marker unless v1 stays OSS and small. |
| R13 | **No `embedding` tier in v1** means a user with 500+ papers will hit walls. | 🟢 | Tier 2 design already planned; ship when users complain. |
| R14 | **OpenSciReader's two-LLM-call render pipeline** is wasteful (we'd be repeating). | 🟢 | Single-pass structured-output ingest; per-source JSON regenerated lazily. |
| R15 | **`hot.md` (claude-obsidian) is a session-cache hack** — useful but unproven at scale. | 🟢 | Build it behind a feature flag; observe before formalizing. |

---

## 8. Decisions you need to make

Defaults are research-recommended. Override any of these in chat.

### D1 — Distribution license model 🔴

| Option | Trade-off | Recommendation |
|---|---|---|
| A. **XReadAgent itself is AGPL-3.0** (or GPL-3.0-compatible). | Indie-friendly, no legal review, but commercial SaaS later requires re-licensing or re-write. | ⭐ if this is a personal/research/community tool |
| B. **BabelDOC as user-installed optional plug-in.** Main app stays under your chosen license. | Most flexibility; some UX friction (user installs translation pack on first use). | ⭐ if commercialization is plausible |
| C. **Negotiate commercial license with funstory-ai.** | Cleanest legal story but costs money + procurement time. | If well-funded |

### D2 — PDF engine default 🟠

| Option | Trade-off | Recommendation |
|---|---|---|
| A. **MinerU 3.x pipeline backend** | Best balance: tables 84.9, equations native, 2-col fix, CPU-OK, Apache. 20 GB on disk. | ⭐ |
| B. **marker** | Best on arXiv (83.8); fast on GPU. GPL-3 + OpenRAIL-M $2M cap. | Only if v1 is OSS |
| C. **Azure Document Intelligence** | Excellent, no install, billable per page. Cloud. | If local-first isn't sacred |

### D3 — Translation packaging 🟠

| Option | Trade-off | Recommendation |
|---|---|---|
| A. **Bundle BabelDOC + assets in installer.** | Slick UX, big installer (~500 MB). | If installer size doesn't matter |
| B. **First-run on-demand download.** | Slim installer, one-time "Preparing engine…" step. | ⭐ (matches Reor/LM Studio/Ollama pattern) |
| C. **User-installs-themselves plug-in.** | Cleanest for the AGPL boundary in D1-B. | If D1 = B |

### D4 — Promote vs Crystallize 🟠

| Option | Trade-off | Recommendation |
|---|---|---|
| A. **Drop auto-promote, use manual `/crystallize`** (paper-curator's discipline). | Stronger anti-hallucination guard; user owns synthesis loop. | ⭐ (research consensus) |
| B. **Keep OpenSciReader-style auto-promote candidates → user approves → merged.** | Closer to the OpenSciReader UX you saw. | If continuity with OpenSciReader matters |
| C. **Both.** Auto-extract candidates + manual `/crystallize`. | More features, more surface area. | Only if you have headroom |

### D5 — UI shell sequencing 🟡

| Option | Trade-off | Recommendation |
|---|---|---|
| A. **FastAPI + browser tab for first 4-6 weeks → Electron later.** | Fastest iteration on agent quality; defer signing/installer pain. | ⭐ |
| B. **Electron from day 1.** | Native feel from the start; slower iteration. | If "feels native" is required for early demos |
| C. **Tauri 2 from day 1.** | 10–20 MB shell vs 80–100 MB; WebKitGTK on Linux is the weak link. | Only if you commit to Linux QA |

### D6 — Platform timeline 🟡

| Option | Trade-off | Recommendation |
|---|---|---|
| A. **Windows v1; macOS v1.5; Linux v2.** | Lowest QA cost; matches user OS. | ⭐ |
| B. **Windows + macOS v1; Linux v2.** | Researchers often Mac. Verify BabelDOC's `hyperscan` story first. | If you have an M-series box for QA |
| C. **All three v1.** | High QA cost; WebKitGTK pain on Linux. | Not recommended |

### D7 — LLM provider strategy 🟢

| Option | Trade-off | Recommendation |
|---|---|---|
| A. **OpenAI-compat first, plus Anthropic + Gemini + Ollama.** | Broadest user reach. | ⭐ |
| B. **Anthropic-first.** | Best models for long-context + code-like editing. | If quality > breadth |
| C. **Local-only via Ollama.** | Privacy-first niche. | If targeting privacy-conscious users |

### D8 — Vector tier in v1? 🟢

| Option | Trade-off | Recommendation |
|---|---|---|
| A. **No vector tier in v1.** Add when users complain. | Lean MVP; pure agentic to ~300 papers. | ⭐ |
| B. **sqlite-vec + FTS5 in v1 as opt-in tool.** | Future-proofs scale; some build cost. | If you expect >300 papers early |
| C. **External `qmd` via MCP.** | Karpathy-blessed; Node/Bun runtime. | If you don't mind a Bun dep |

### D9 — MCP exposure 🟢

| Option | Trade-off | Recommendation |
|---|---|---|
| A. **Yes — XReadAgent ships an MCP server alongside the UI.** | Reaches the Karpathy/Claude-Code-Skill audience for free. | ⭐ |
| B. **No — strictly an app.** | Smaller surface area; one less thing to maintain. | If MCP isn't on the user roadmap |

### D10 — Telemetry & observability 🟢

| Option | Trade-off | Recommendation |
|---|---|---|
| A. **Off by default; opt-in LangSmith or Pydantic Logfire.** | Local-first sacrament. | ⭐ |
| B. **On by default with self-hosted OTel.** | Better debugging out of the box. | If users are developers |

---

## 9. Implementation roadmap (proposed)

**Phase 0 — Skeleton (week 1)**
- Repo + Trellis spec layers (backend python / frontend react)
- LLMGateway abstraction + Pydantic 2 base schemas
- Wiki directory contract + path validation + slug helpers (port from OpenSciReader)
- FastAPI skeleton with `/healthz` + `/ws/events`
- Stub Electron loader (deferred from interactive use)

**Phase 1 — Wiki MVP (weeks 2–4)**
- markitdown integration for non-PDF (smoke test on `.docx`, `.html`)
- MinerU integration for PDF (gate on first-run model download)
- Ingest sub-agent on `deepagents` (single-pass structured output → wiki diffs)
- `index.md` regenerator + `log.md` append
- Paper + Concept page templates
- Query sub-agent with `queries/` isolation
- React UI: workspace browser, paper page view, ask-bar, citations panel

**Phase 2 — Translation + Reader (weeks 5–7)**
- BabelDOC subprocess wrapper + WS streaming
- Dual-column PDF reader (PDF.js, page-replace as chunks finish)
- mono + dual export
- First-run translation-engine download flow

**Phase 3 — Polish + production shell (weeks 8–10)**
- Lint sub-agent + `lint_scan.py`
- `/crystallize` workflow
- Electron wrapper + `electron-builder` config + auto-updater
- Windows code signing (Azure Trusted Signing)
- Optional GROBID Docker side-car

**Phase 4 — Optional extensions (later)**
- Tier-2 embedding (sqlite-vec + FTS5)
- MCP server
- macOS / Apple Silicon support (after `hyperscan` verified)
- Plugin system for custom skills
- Zotero importer

---

## 10. Out of scope (locked unless you reopen)

- Multi-user collaboration / real-time editing
- Cloud sync (designed sync-friendly but no service)
- Mobile apps
- Plugin marketplace
- Citation graph generation across the open web
- Web-search auto-ingest (`paper-curator` has it; we defer)

---

## 11. Decision log (ADR-lite)

Locked 2026-05-22 in brainstorm session.

### D1 — License model
- **Context**: BabelDOC is AGPL-3.0; commercial SaaS distribution is legally ambiguous to blocked.
- **Decision**: **XReadAgent ships as AGPL-3.0 / GPL-compatible open source.**
- **Consequences**: We can `import babeldoc` directly with zero legal review. No commercial license procurement needed. Closes the door on closed-source SaaS commercialization — future commercialization would require either re-licensing the codebase (only possible if all contributors agree) or buying out funstory-ai for a commercial BabelDOC license. License files (`LICENSE` + NOTICE) and SPDX headers get added in Phase 0.

### D2 — PDF engine default
- **Context**: markitdown fails on scientific PDFs; multiple credible alternatives.
- **Decision**: **MinerU 3.x pipeline backend** as the PDF default; markitdown limited to DOCX/PPTX/XLSX/HTML; GROBID optional for citation enrichment.
- **Consequences**: ~20 GB model footprint deferred to first-run download (combines with D3). Best-balanced scientific PDF parsing (OmniDocBench 86.2, tables 84.9). MinerU OSS License (Apache-derived, 2026-04 re-license) is AGPL-compatible.

### D3 — Translation packaging
- **Context**: BabelDOC + MinerU together are 1–3 GB on disk.
- **Decision**: **First-run on-demand download** for both translation and PDF engine assets, with "Preparing engine…" UX. Matches Reor / LM Studio / Ollama pattern.
- **Consequences**: Slim installer (~200 MB) ships fast; first ingest / first translation has a one-time download step.

### D4 — Promote vs Crystallize
- **Context**: OpenSciReader's auto-promote can trigger hallucination feedback loops (paper-curator's documented anti-pattern).
- **Decision**: **Drop OpenSciReader-style auto-promote.** Use paper-curator's manual `/crystallize` command + `queries/` isolation discipline.
- **Consequences**: Q&A archives never auto-feed back to `papers/` or `concepts/`. User explicitly invokes `/crystallize` to promote a query into the wiki. Simpler UI (no review queue); stronger correctness guarantee.

### D5 — UI shell sequencing
- **Context**: Electron from day 1 adds signing/installer pain to early iteration.
- **Decision**: **Weeks 1–6: FastAPI + React/Vite/shadcn served in browser tab.** Weeks 7+: Electron wrapper, code signing, auto-updater.
- **Consequences**: Faster agent-quality iteration. Defer HSM cert procurement (~$10/mo Azure Trusted Signing) to Phase 3.

### D6 — Platform timeline
- **Decision**: **Windows v1.** macOS deferred to v1.5 (after BabelDOC `hyperscan` verified on Apple Silicon). Linux deferred to v2.
- **Consequences**: Lowest QA cost; matches developer machine. macOS verification is a tracked task before any cross-platform marketing.

### D7 — LLM provider strategy
- **Decision**: **All four major providers in v1**: OpenAI-compat (lingua franca), Anthropic, Gemini, Ollama.
- **Consequences**: LLMGateway must abstract over four SDKs. `langchain-ai/deepagents` handles the provider switch via single string; our gateway adds budget/rate-limit/cache/retry on top. Settings UI needs provider config per provider.

### D8 — Vector tier in v1
- **Decision (default)**: **No vector tier in v1.** Pure-agentic `index.md` drilldown ships first. Tier 2 (`sqlite-vec` + FTS5) added when a user hits navigation limits (typically ~300 papers).
- **Consequences**: Smaller dependency footprint v1. Faster to ship. Embedding tier becomes a feature-flagged add-on in Phase 4.

### D9 — MCP exposure
- **Decision (default)**: **Yes — XReadAgent ships an MCP server alongside the UI** in Phase 4 (not blocking v1). Wiki tools (`read_wiki_page`, `write_wiki_page`, `ingest_source`, `query_wiki`, `crystallize`) exposed via FastMCP.
- **Consequences**: Power users can drive XReadAgent's wiki engine from Claude Code / Codex / Cursor. Captures the Karpathy/Claude-Code-Skills audience for free. Maintenance cost: one extra entry point per tool change.

### D10 — Telemetry & observability
- **Decision (default)**: **Off by default. Opt-in to LangSmith free tier or Pydantic Logfire** via env vars. No silent telemetry. Local-first sacrament.
- **Consequences**: Users explicitly enable tracing for debugging. No default outbound data flow except LLM API calls (already user-configured).

---

## 12. Sources

See `research/agent-framework.md`, `research/desktop-shell.md`, `research/layout-translation.md`, `research/llm-wiki-prior-art.md`, `research/pdf-pipeline.md`.
