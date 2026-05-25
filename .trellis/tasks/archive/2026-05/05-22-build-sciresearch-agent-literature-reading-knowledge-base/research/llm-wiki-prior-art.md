# Research: LLM-Wiki Prior Art + Retrieval Architecture (pure-wiki vs hybrid-with-vector-store)

- **Query**: LLM-Wiki prior art + retrieval architecture — pure-wiki vs hybrid-with-vector-store
- **Scope**: mixed (internal: OpenSciReader workspace knowledge layer; external: Karpathy gist + GitHub implementations + vector stores)
- **Date**: 2026-05-22

---

## Summary (recommended architecture in 3 bullets)

1. **Default to pure-wiki / agentic navigation for retrieval. Add a vector index ONLY as a second-tier "search" tool, never as the primary memory layer.** At MVP (<100 papers) `index.md` + recursive grep is sufficient — confirmed by Karpathy's gist, `llm-wiki-skills`, `claude-obsidian`, and `obsidian-paper-curator` who all ship this way. Embeddings are an optimization triggered when the agent says "I cannot navigate this size" — typically only past ~300–500 documents.
2. **Adopt OpenSciReader's distillation model (entities / claims / relations / tasks per-source, then compile to wiki/) but flatten it to a single wiki-writing pass** instead of a two-stage `by-source/*.json` → `wiki/*.md` pipeline. The two-stage design is correct in spirit (it gives idempotent recompile from immutable per-source records) but doubles the LLM cost. For a Python agent we keep the per-source JSON as the audit/recompile substrate, but only generate it lazily.
3. **Keep four wiki page types** — `index.md`, `log.md`, `papers/<slug>.md` (per-source), `concepts/<slug>.md` (per-entity), plus `open-questions.md` aggregation — directly inherited from OpenSciReader's `internal/desktop/workspace_knowledge_files.go:516-534`. Add **`queries/<topic>/<date>-<slug>.md`** as a fifth, isolated type (from `obsidian-paper-curator`) so that Q&A archives never pollute the synthesis layer.

---

## Prior art landscape

### Direct Karpathy-inspired implementations

| Tool | Lang/Platform | Stars | Wiki structure | Retrieval | Distinguishing trait |
|---|---|---|---|---|---|
| **claude-obsidian** (AgriciDaniel) | Claude Code plugin + Obsidian | 1k+ class | `wiki/{index,log,hot,overview}.md` + entity/concept folders + 11 skills | Hot-cache → `index.md` → drill into pages → optional Obsidian Local REST API MCP | Adds `hot.md` (session-handoff cache), `/save`, `/autoresearch`, "DragonScale Memory" extension with semantic tiling lint |
| **llm-wiki-skills** (vanillaflava) | Cross-agent (Claude/Gemini/Codex/Copilot) skills | 35 | `wiki-config.md` + `wiki-schema.md` + 13 page templates + `raw/` (queue) → `ingested/` (commit) | Pure agentic: read index → drill | Three-layer instruction model (permanent + project + domain home). `/crystallize` files chat back as wiki page. `source:` + `reliability:` (high/medium/low) frontmatter + `## Pending Review` for low-confidence claims. **Closest to what XReadAgent should be.** |
| **obsidian-paper-curator** (zzzlxhhh) | Kimi CLI + Obsidian + 3 skills | 8 | `papers/<topic>/` + `concepts/` + `queries/<topic>/` + `Clippings/` (raw) + `Clippings/_processed/` (archived) | **4-layer hierarchical retrieval** (L1 semantic overview via index.md+grep → L2 read structured pages → L3 raw clippings → L4 web fallback) | Most directly relevant to XReadAgent. Distinguishes **paper-injest** (Background/Challenges/Solution/Positioning/Concepts/Experiments) from **paper-query** (which archives Q&A to `queries/` but **explicitly does NOT feed answers back into wiki/index/log** to avoid hallucination loops) from **paper-lint** with a Python `lint_scan.py` graph scanner |
| **obsidian-wiki** (MykytaMorachovEpam) | Obsidian + LLM | 10 | Karpathy-faithful: `wiki/`, `raw/`, schema doc | Pure agentic | Smaller scope, generic |
| **hermes-second-brain** / **hermes-memos** | Obsidian + LLM | 3 / 0 | Standard | Pure agentic | Renders wiki to static site |
| **wiki-forge** (avdiam) | Generic agent | 0 | "Knowledge compiler" framing | — | Emphasizes compounding |
| **ai-memex-cli** (zelixag) | CLI + git | 6 | Markdown KB + git versioning | — | Frames the wiki as compounding interest |
| **Granite** (The-Vibe-Company) | CLI + MCP server | 23 | Plain markdown | Local-first agentic | Explicitly cites Karpathy's vision |
| **llm-wiki** (Ac-spider) | Obsidian | 1 | Multi-agent pipeline, ~1k AI/ML concept pages | — | Concrete proof at scale |

### Adjacent / cousin tools

| Tool | Lang | Stars | Pattern | Lesson for XReadAgent |
|---|---|---|---|---|
| **qmd** (Tobi Lütke, [github.com/tobi/qmd](https://github.com/tobi/qmd)) | Node/Bun + node-llama-cpp + sqlite | high | **Hybrid local search**: BM25 + vector + LLM rerank over markdown vault. CLI + MCP server. Explicitly the tool Karpathy recommends in the gist when the wiki outgrows `index.md`. | This is the canonical "Tier 2" upgrade path. If/when XReadAgent needs an embedding index, shell out to qmd via MCP rather than reinventing it. **sqlite-based, single file, no daemon.** Note: Node/Bun runtime — if Python-only is required, replicate the BM25+vector+rerank pattern with `sqlite-vec` + `BM25S` + a local reranker. |
| **PaperQA2** (Future-House, 8.5k stars) | Python | 8.5k | **Agentic RAG, NOT wiki**. Per-paper chunks → embedding index (default: NumpyVectorStore in-memory, or external Qdrant/Chroma) → LLM agent issues `paper_search` / `gather_evidence` / `gen_answer` tool calls. **Re-derives synthesis every query.** Has document-metadata-aware embeddings and contextual summarization. | Useful for the **evidence-retrieval** sub-problem (cite exact paper passages with page numbers), NOT for the wiki itself. Borrow their `Docs` index abstraction and contextual-summarization prompt. Do NOT borrow their re-derive-every-query architecture as the primary path — Karpathy's whole critique applies. |
| **Obsidian Smart Connections** (brianpetro) | Obsidian plugin | 3k+ class | Embedding index over note chunks, "similar notes" sidebar, chat-with-vault. **Reconciliation**: never modifies markdown; just shows nearest-neighbor links. | The "embed, don't mutate" stance. For XReadAgent we go further — embedding is *additive*, the wiki remains the canonical synthesis. |
| **Reor** (reorproject) | Electron + Ollama + LanceDB | 7k+ class | Local-first AI note app. Embeddings via LanceDB, LLM via Ollama. Auto-creates connections between notes via similarity. | Reference impl of **LanceDB as the local-first embedding store for markdown**. Single-file, Rust core, zero daemon, columnar — best fit for our optional Tier 2. |
| **Logseq AI** / **Reor** | Various | — | Local markdown + embeddings | Same pattern: embed, suggest, never mutate without user OK |
| **Awareness-Local** (edwin-hao-ai) | CLI for Claude Code/Cursor/Windsurf | 217 | **Markdown + SQLite FTS5 + embeddings** giving coding agents persistent memory | Proves the FTS5+vector hybrid pattern is the production-grade choice for "give an agent local memory." Borrow architecture. |
| **echovault** (mraza007) | Coding agent memory | 143 | Markdown + FTS5 + optional semantic, "no RAM overhead at idle" | Same pattern. **Lazy index loading** matters at scale. |
| **mem.ai** (proprietary) | Web app | — | Proprietary AI-organized notes. Closed source. No public algorithm disclosed beyond marketing. | Not actionable. Skip. |
| **Tolkien Gateway / fan wikis** (Karpathy's analogy) | MediaWiki | — | Manually curated, ~thousands of pages, dense backlinks | Aspirational target shape, not implementation. |
| **OpenSciReader workspace_knowledge** (our own prior project, G:/0JHX-code/Project/OpenSciReader/) | Go + Wails | — | Per-source JSON distillation → aggregate state → wiki pages. Entities + claims + relations + tasks. | See dedicated section below. |

### Verdict

There is a **dense, fast-growing prior-art landscape** (most of these repos are <12 months old as of 2026-05). The pattern crystallized in late 2025 with Karpathy's gist as the canonical reference. **Convergent design choices across implementations** (which we should adopt):

- `wiki/`, `raw/`, `ingested/` directory split (raw = immutable inbox, ingested = archived sources, wiki = LLM-owned synthesis).
- `index.md` (content catalog, regenerated on ingest) + `log.md` (append-only chronological).
- A `paper-injest` / `paper-query` / `paper-lint` triad of skills.
- Entity/concept pages with wikilinks `[[...]]` (Obsidian-style) preferred over markdown `[..](..)` links.
- Queries archived to a *separate* `queries/` folder, with strong guidance NOT to feed query answers back into the wiki automatically — this is `obsidian-paper-curator`'s critical anti-hallucination discipline.

---

## Recommended wiki schema

### Directory layout

```
{workspace_root}/
├── raw/                     # Immutable. Original PDFs, HTML clippings, markdown sources.
│   └── _processed/          # After ingest, sources move here. Presence = "ingested".
├── extracts/                # markitdown/marker/PyMuPDF output. One .md per raw source.
│   └── {slug}.md
├── state/                   # Machine-readable distillation (see "OpenSciReader lessons").
│   ├── sources.json         # Manifest of all sources, with contentHash for idempotent re-scan.
│   ├── by-source/
│   │   └── {slug}.json      # Per-paper {entities, claims, relations, tasks} payload.
│   ├── entities.json        # Aggregated.
│   ├── claims.json
│   ├── relations.json
│   ├── tasks.json
│   ├── compile-summary.json # Bookkeeping for "is wiki dirty?"
│   └── conversation-log.jsonl # Append-only query/promotion log.
└── wiki/                    # Human-readable. LLM-owned. The compounding artifact.
    ├── index.md             # Catalog. Auto-regenerated on ingest.
    ├── log.md               # Chronological, append-only.
    ├── overview.md          # Workspace-level executive summary.
    ├── open-questions.md    # Aggregated task list (from state/tasks.json).
    ├── hot.md               # OPTIONAL: session-handoff cache (claude-obsidian innovation).
    ├── papers/              # One page per ingested source.
    │   └── {slug}.md
    ├── concepts/            # One page per canonical entity.
    │   └── {slug}.md
    └── queries/             # Archived Q&A. ISOLATED from index/log.
        └── {topic}/
            └── {YYYY-MM-DD}-{short-slug}.md
```

### Page types

| Type | Path | Frontmatter | Body sections | Owner |
|---|---|---|---|---|
| `paper` | `wiki/papers/{slug}.md` | `title, source, doi, year, authors, topics[], reliability, source_hash, page_type: paper` | Background / Challenges / Solution / Positioning / Key Concepts / Experiments / Open Questions (the `obsidian-paper-curator` template) | `ingest` |
| `concept` | `wiki/concepts/{slug}.md` | `title, aliases[], type, page_type: concept` | Summary / Related Papers / Related Claims / Open Questions | `ingest`, updated on every relevant ingest |
| `index` | `wiki/index.md` | none | Documents list + Concepts list + Open Questions count | auto-regenerated on ingest |
| `log` | `wiki/log.md` | none | `## [YYYY-MM-DDTHH:MM:SSZ] {op} \| {subject}` entries | append-only |
| `overview` | `wiki/overview.md` | `page_type: overview` | High-level synthesis, evolving thesis | `ingest` + `crystallize` |
| `open-questions` | `wiki/open-questions.md` | none | bulleted list with source citations | auto-regenerated |
| `query` | `wiki/queries/{topic}/{date}-{slug}.md` | `question, layers_used[], date, sources_cited[], page_type: query` | Question / Answer / Sources | `query` skill only; never read by `ingest` |
| `hot` (optional) | `wiki/hot.md` | none | Recent context summary, refreshed at end of session | `crystallize` |

### Naming conventions

- **Files**: kebab-case slug, ASCII-only, with stable hash suffix for disambiguation. Inherited from OpenSciReader (`internal/desktop/workspace_wiki_service.go:1227-1240`):
  - `workspaceKnowledgeStableSourceSlug(baseSlug, sourceKey)` produces `attention-is-all-you-need-a1b2c3d4e5f6` — base slug (from title) + sha256-truncated-12 hash of stable key (documentID or relative path). **This solves "two papers named 'attention'" without losing readability.**
  - For concepts: `workspaceKnowledgeSlug(title)` then disambiguation counter (`gpt`, `gpt-2`, `gpt-3` if collisions). See `workspace_knowledge_compile.go:634-647`.
- **Path validation**: forbid `<>:"/\|?*`, no absolute paths, no `..` traversal. See `workspace_knowledge_files.go:709-723`.

### Entity disambiguation

The "two papers mention 'GPT'" question: **the OpenSciReader pattern is correct — entities have stable IDs (`entity:gpt`) plus an `aliases[]` array**, and the LLM is prompted to merge same-concept-different-name into one page with all aliases listed (`workspace_knowledge_types.go:40-53`). For papers, **always use source_hash + stable slug, never title alone** — two papers with similar titles get different `-{hash12}` suffixes.

### Cross-reference syntax

**Use Obsidian-style wikilinks `[[concepts/transformer|Transformer]]`** as the primary form, with markdown `[Transformer](../concepts/transformer.md)` as a fallback when the renderer is not Obsidian-aware. OpenSciReader does both:
- `index.md` uses wikilinks: `- [[concepts/transformer|Transformer]]` (`workspace_knowledge_compile.go:356-372`).
- `overview.md` uses markdown links: `- [Transformer](concepts/transformer.md)` (`workspace_knowledge_compile.go:404-420`).

For XReadAgent: prefer wikilinks since Obsidian is the assumed reader (per Karpathy's gist).

### `index.md` maintenance

**Auto-generated**, not hand-curated. Karpathy says "The LLM updates it on every ingest." OpenSciReader regenerates the entire `index.md` deterministically from the snapshot on every compile (`workspace_knowledge_compile.go:340-378`). This is correct: hand-curation creates merge conflicts and stale links. Cost is bounded by O(sources + concepts), and the file fits in context until ~10k entries.

### `log.md` schema

Append-only, parseable with `grep "^## \[" log.md | tail -5`. Karpathy-recommended format:

```
## [2026-05-22T14:23:00Z] ingest | Attention Is All You Need
- source: raw/attention-is-all-you-need.pdf
- slug: attention-is-all-you-need-a1b2c3d4e5f6
- touched: papers/attention-is-all-you-need-a1b2c3d4e5f6.md, concepts/transformer.md, concepts/self-attention.md, index.md
- new_concepts: 2 (transformer, multi-head-attention)
- claims_added: 5

## [2026-05-22T14:31:00Z] query | what is the difference between GRPO and PPO
- evidence_ids: [paper:grpo-..., paper:ppo-..., concept:policy-gradient]
- archived: queries/reinforcement-learning/2026-05-22-grpo-vs-ppo.md

## [2026-05-22T15:00:00Z] lint | scheduled
- orphans_fixed: 1
- dead_links: 0
- report: state/lint-reports/2026-05-22T150000.md
```

Use ISO-8601 UTC timestamps (matches OpenSciReader's `nowRFC3339()`). Three operation types: `ingest`, `query`, `lint` — match Karpathy's three operations exactly.

---

## Retrieval strategy: pure-agentic vs hybrid embedding

### The scaling question, examined

Karpathy: *"This works surprisingly well at moderate scale (~100 sources, ~hundreds of pages) and avoids the need for embedding-based RAG infrastructure."* He explicitly puts the threshold at ~100 sources where `index.md` reading + drill-down still works.

Empirically from the prior-art survey:

| Pattern | Scale where it works | Pattern fails when |
|---|---|---|
| Pure-agentic (`index.md` + grep + drill) | <300 sources (anecdotal: vanillaflava, claude-obsidian, paper-curator authors operate at 50–200 papers) | `index.md` > LLM context budget (~10k entries with one-liners ≈ 200KB ≈ 50k tokens — fits in modern long-context models but kills latency and cache) |
| Hierarchical (sub-indexes per topic) | <1000 sources | Cross-topic queries thrash |
| Hybrid (vector first-pass + agentic drill) | 1000–100,000 sources | Below ~300, embeddings add complexity for no benefit |
| Pure RAG | Doesn't compound. PaperQA2 is the only well-engineered example. | Never accumulates synthesis — Karpathy's whole critique. |

### Recommendation for XReadAgent

**Tiered, lazy escalation.** Start with Tier 1, only build Tier 2 when the user hits Tier-1 pain.

**Tier 1 — Pure-agentic (MVP, <300 papers)**

The retrieval algorithm for `query`, ported from `obsidian-paper-curator`'s 4-layer model:

1. **L1 — semantic overview**: read `wiki/index.md` (always small, regenerated). LLM picks candidate pages. For nav-style questions ("what RLHF papers do we have?"), L1 answers directly.
2. **L2 — structured pages**: read full text of candidate `papers/*.md` and `concepts/*.md`. Follow wikilinks transitively (1-hop is usually enough). Most concept/definition/comparison queries answer here.
3. **L3 — raw evidence**: read `extracts/{slug}.md` for exact passages, numbers, tables. Only triggered when L2 summary is insufficient.
4. **L4 — external**: only if user requests. Annotate as `[External: <url>]`.

This is also OpenSciReader's pattern, but **slightly different and worse than paper-curator's**: in `workspace_knowledge_query.go:449-476`, OpenSciReader uses `retrieveWorkspaceKnowledgeEvidence` which tries `wiki` → `state` → `input` (extracts) in sequence and stops at the first non-empty hit. Its scoring is a simple **BM25-ish term-overlap** (`workspace_knowledge_query.go:771-799`, `workspaceKnowledgeHitScore`), which is fine as a deterministic shortlister but is **not** agentic. **For XReadAgent we want the LLM to drive layer escalation, not a fixed-order fallback chain.**

**Tier 2 — Optional embedding tool (>300 papers, or when user complains about latency)**

Add an `evidence_search` MCP tool that returns top-k chunks by cosine similarity. **Critical design constraints:**

- **Embed wiki PAGES, not raw chunks**, for the wiki retrieval. Page-level embeddings keep us in the wiki layer (cite `concepts/transformer`, not "chunk 47 of paper X"). Pages are short, semantically coherent, already-distilled by the LLM. This is `qmd`'s page-level design.
- **Also embed raw paper chunks** for **evidence retrieval** (Tier 3) — when the user asks "show me the exact passage where PaperQA2 reports 86.3% accuracy", we need chunk-level granularity. This is a *separate* index from the wiki index. Borrow PaperQA2's chunking + embedding approach.
- **Hybrid query**: BM25 (lexical) + vector (semantic) + LLM rerank, RRF-fused. Matches qmd, awareness-local, echovault. Pure-vector retrieval is fragile on technical terminology ("GRPO" misspelled as "GPRO" fails on vector, succeeds on BM25).
- **The agent decides when to use it**: expose as a tool, do not auto-invoke. If the LLM can answer from L1+L2, it shouldn't pay for embeddings.

### Local-first Python vector store comparison

| Store | Format | Embedding storage | BM25 builtin | Best for | Risk |
|---|---|---|---|---|---|
| **LanceDB** | Single columnar `.lance` dir | Native ANN (IVF_PQ, HNSW) | Yes (full-text via Tantivy) | **Recommended.** Single-file, zero-daemon, Rust core, multimodal-ready, mature Python SDK. Reor uses it for the same use case. | Newer (2023+); larger binary footprint than sqlite-vec |
| **sqlite-vec** (asg017) | SQLite extension | float32/int8 + brute-force or DiskANN | No — pair with FTS5 (also in sqlite) | **Best minimal-deps option.** One file, no daemon, FTS5 already in stdlib. Awareness-Local + echovault use exactly this. | No native ANN at very large scale (>1M vectors); brute force OK for 100k |
| **Chroma** | SQLite + parquet | HNSW | No (lexical via separate hook) | Easy quickstart, popular | Heavy dependency tree, opinionated client API, daemon mode by default |
| **Qdrant local** | Native binary store | HNSW | No | Production-ready, fast | Designed as a server; embedded mode less polished; overkill |
| **DuckDB VSS** | DuckDB columnar | HNSW (experimental ext) | Yes (FTS ext) | If we already use DuckDB for analytics | VSS extension still experimental as of 2026 |
| **NumpyVectorStore** (PaperQA2 default) | Pickled numpy | Brute-force cosine | No | Prototype / <10k chunks | Won't scale |

**Recommendation**: **sqlite-vec + FTS5** for MVP-Tier-2 (when needed), with a clean abstraction layer so we can swap to **LanceDB** if/when we hit >100k chunks or want multimodal. Rationale:

1. **Single binary file** — fits the "wiki is a git repo of markdown" Karpathy aesthetic. No daemon, no separate process.
2. **FTS5 is in stdlib** — BM25 for free, no extra dependency.
3. **Python `sqlite-vec`** integrates as a SQLite extension load, ~3MB.
4. **Awareness-Local and echovault (both >100 stars, real users) prove the pattern at the exact same use case** (giving coding agents local memory).
5. The wiki itself is what compounds — the vector index is *recomputable from wiki pages*, so its format is not load-bearing for users.

If we want zero-second-thought: just shell out to **`qmd`** via MCP. It's already the BM25+vector+rerank black box Karpathy points at. The only cost is a Node/Bun runtime dependency (which most developers running Claude Code already have).

---

## Lint operation design

Karpathy: *"contradictions between pages, stale claims that newer sources have superseded, orphan pages with no inbound links, important concepts mentioned but lacking their own page, missing cross-references, data gaps."*

### Trigger model

Three triggers, in priority order:

1. **On-ingest lite check** (synchronous, cheap): every `ingest` runs a small lint pass on touched pages only — verify wikilinks resolve, check `index.md` is updated, ensure new entities don't collide. Borrowed from `claude-obsidian`'s ingest flow.
2. **User-triggered full lint** (manual, expensive): `/lint` command runs full graph scan + LLM passes. Same as `obsidian-paper-curator`'s `paper-lint`.
3. **Periodic background** (scheduled, optional): cron-style daily or weekly. Off by default — opt-in.

### Detection signals

Adapted from `obsidian-paper-curator`'s `lint_scan.py` model + Karpathy's enumeration:

| Signal | How to detect | Tool used | Cost |
|---|---|---|---|
| **Orphan pages** | Graph traversal: build adjacency from wikilinks, find nodes with `in-degree == 0` (except `index.md`, `overview.md`, `log.md`). | Python script (deterministic). | O(pages) — cheap |
| **Dead/broken links** | Parse all `[[...]]` and `[..](..)`, check target exists. | Python script. | O(links) — cheap |
| **Missing index entries** | Diff `index.md` against actual files in `wiki/papers/` and `wiki/concepts/`. | Python script. | Cheap |
| **High-frequency missing concepts** | Count plain-text mentions of capitalized n-grams across all pages; if ≥3 mentions and no page exists, flag for creation. paper-curator's heuristic. | Python script. | Cheap |
| **Missing cross-references** | For each existing concept page, scan all other pages for plain-text mentions of `title` or `aliases[]`, and flag where they are *not* wikilinked. | Python script. | Cheap |
| **Contradictions** | LLM diff over claim pairs from `state/claims.json` that share an `entityId`. Pairwise prompt: "do these two claims contradict?" | LLM. | O(n_claims^2) within entity — bounded |
| **Stale claims** | Compare claim `updatedAt` to source `lastSuccessAt`; if source has been re-ingested but claim wasn't refreshed, flag. | Deterministic. | Cheap |
| **Data gaps / open questions** | Read `state/tasks.json` (Open Questions accumulated by ingest); LLM suggests "you could search the web for X". | LLM. | Cheap (single call) |

### Implementation — borrow from OpenSciReader + paper-curator

- Python `lint_scan.py` produces a JSON graph (nodes + edges + per-node degree). Hard-coded deterministic checks emit a candidate-issues list.
- LLM gets the candidate list + relevant page contents and proposes **fixes**, not just findings. Fixes go through a confirm-or-auto-apply flow.
- Every lint run writes a **timestamped report** to `state/lint-reports/{YYYY-MM-DDTHHMMSS}.md` with a unified `+/-` diff per modified file. paper-curator's `LintLog/` pattern.
- **Idempotency check**: running lint twice consecutively on an unchanged wiki must report 0 new issues. Paper-curator codifies this — borrow it as a contract test.

---

## OpenSciReader code reuse / lessons

The OpenSciReader workspace knowledge layer (at `G:/0JHX-code/Project/OpenSciReader/internal/desktop/workspace_knowledge_*.go` and `workspace_wiki_service.go`) is a **mostly correct, sometimes over-engineered** prior implementation of this exact pattern in Go. Here's what to reuse and what to drop, with citations.

### Reuse (port to Python)

1. **Per-source JSON distillation as the audit substrate.**
   `workspace_knowledge_types.go:100-106` defines `WorkspaceKnowledgeBySourcePayload {Source, Entities, Claims, Relations, Tasks}`. One JSON per ingested paper at `state/by-source/{slug}.json`. **Critical insight**: this makes the wiki **deterministically recompilable** from the per-source records. If the wiki rendering changes (new template, new field), we just recompile from `by-source/*.json` without re-LLM'ing every paper. **Port this.** OpenSciReader's `CompileWorkspaceKnowledge` in `workspace_knowledge_compile.go:46-72` is the recompile entry point.

2. **The 4-category schema: Entities, Claims, Relations, Tasks.**
   - `WorkspaceKnowledgeEntity` (`types.go:40-53`): `{id, title, type, summary, aliases[], sourceRefs[], origin, status, confidence, createdAt, updatedAt}`. Maps to `concepts/{slug}.md`.
   - `WorkspaceKnowledgeClaim` (`types.go:55-68`): `{id, title, type, summary, entityIds[], sourceRefs[], origin, status, confidence, ...}`. Per-fact assertions with provenance. Not surfaced as standalone pages — aggregated under each concept's "Related Claims".
   - `WorkspaceKnowledgeRelation` (`types.go:70-83`): typed edges `{type, fromId, toId, summary, sourceRefs[]}`. Powers graph traversal and "see also" generation.
   - `WorkspaceKnowledgeTask` (`types.go:85-98`): open questions with priority. Aggregated into `open-questions.md`.

   This four-fold decomposition is **directly portable** and matches `paper-curator`'s implicit per-paper structure (Background/Challenges/Solution/Positioning/Concepts/Experiments — concepts→Entities, "experiments report X" claims→Claims, "X improves over Y"→Relations, future-work→Tasks).

3. **`sourceRefs[]` with `{sourceId, pageStart, pageEnd, excerpt}` on every entity/claim/relation/task.**
   `types.go:33-38`. **This is the citation contract.** Every assertion in the wiki must trace to a page range and short excerpt in the source. Port verbatim. Karpathy doesn't specify citation format; OpenSciReader's is rigorous.

4. **Stable slug = base + sha256-truncated-12.**
   `workspace_wiki_service.go:1216-1240`. Solves entity/source name collisions. Port verbatim:
   ```python
   def stable_slug(base: str, source_key: str) -> str:
       h = hashlib.sha256(source_key.encode()).hexdigest()[:12]
       return f"{kebab(base)}-{h}" if h else kebab(base)
   ```

5. **Content-hash idempotent rescan.**
   `workspace_wiki_service.go:815-837` — `shouldSkipSource` skips re-ingest if `contentHash` matches AND status is `ready` AND artifacts exist. Saves re-LLMing on unchanged PDFs. Port.

6. **Compile-summary "dirty" tracking.**
   `WorkspaceKnowledgeCompileSummary` (`types.go:22-31`) tracks `CompileDirty` / `WikiDirty` flags. Lets a UI know "the wiki is out of sync with state". Port for the optional UI layer.

7. **Conversation log as JSONL with `EvidenceIDs` and `PromotedClaimIDs`.**
   `workspace_knowledge_query.go:29-40`. Append-only, structured, machine-grep-able. Better than free-form `log.md` for audit. **Recommendation: keep `log.md` for human reading AND `conversation-log.jsonl` for machine processing.** Both written on every operation.

8. **Path segment validation** to defeat traversal/Windows-invalid chars.
   `workspace_knowledge_files.go:709-723`. Port verbatim.

9. **Slug deduplication for concepts** with counter suffix.
   `workspace_knowledge_compile.go:634-647`. `gpt`, `gpt-2`, `gpt-3` if title collisions. Port.

10. **The wiki-write-plan validation step.**
    `workspace_knowledge_compile.go:238-263` — `validateWorkspaceKnowledgeWikiWritePlan` checks for duplicate output paths and existing directories-where-file-expected *before* writing anything. Prevents partial corruption. Port.

### Drop / change

1. **Drop: separate `state/{entities,claims,relations,tasks}.json` aggregates.**
   OpenSciReader writes both `state/by-source/{slug}.json` AND `state/entities.json` (the aggregate of all per-source entities). The aggregates are derivable on-the-fly; pre-materializing them was for Wails IPC performance. In Python, just compute on read. Saves a write step in `writeWorkspaceKnowledgeAggregates` (`workspace_knowledge_compile.go:104-138`).

2. **Drop: legacy-path fallback machinery.**
   The `legacyBySourceDir`, `legacySchemaDir` etc. (`workspace_knowledge_files.go:589-671`) exist for backward compatibility with an earlier layout. Greenfield project — skip.

3. **Change: ingest LLM prompt should produce wiki markdown directly, not just JSON.**
   OpenSciReader uses a **two-LLM-call** pattern: (1) `GenerateWorkspaceKnowledgeBySource` produces JSON (`workspace_knowledge_prompts.go:8-58`), (2) compile step deterministically renders that JSON into markdown (`workspace_knowledge_compile.go:489-567`). This is **robust** (idempotent recompile) but **costly** and **lossy** — the markdown is mechanical, not synthesized.

   `obsidian-paper-curator` and `llm-wiki-skills` instead have the LLM **write the markdown directly** with template guidance — much richer prose, better at "Positioning" (which OpenSciReader's mechanical render can't do).

   **Synthesis for XReadAgent**: have the LLM produce **both**: a JSON `by-source` payload AND the markdown wiki page, in a single structured-output call. Cost is one LLM call per paper. Json stays for recompile/audit; markdown is the human-readable artifact.

4. **Change: drop the `Wails IPC` and `configStore` boilerplate.**
   `workspaceWikiService` (`workspace_wiki_service.go:25-47`) carries Wails desktop runtime bookkeeping (job cancellation, plugin checks). For a Python CLI/agent, replace with a simple async function + `asyncio.CancelledError` handling.

5. **Change: extend with `queries/` isolation.**
   OpenSciReader has a Promote workflow (see below) but no separate query-archive directory. Adopt `paper-curator`'s `queries/<topic>/{date}-{slug}.md` and the discipline that queries do NOT update `index.md`, `log.md` (well, log records the operation but not the answer content), or create new wiki pages.

6. **Change: simpler promote.**
   OpenSciReader's `Promote` (`workspace_knowledge_query.go:109-202`) is sophisticated — canonical claim ID hashing, ambiguous-match detection, semantic claim matching (`findWorkspaceKnowledgeClaimForCandidate`, `canonicalWorkspaceKnowledgeClaimID` at `query.go:880-951`). Powerful but heavy. **MVP recommendation**: drop the auto-promote entirely. Per `paper-curator`'s discipline, queries never auto-write back. Instead, expose a `/crystallize` (from `claude-obsidian` / `llm-wiki-skills`) explicit user command: "this Q&A was valuable, file it as a wiki page" — *user-driven*, not auto. Add the OpenSciReader-style canonical-ID matching later if duplicate-claim issues emerge.

### Specific code references

| File | Lines | What it does | Action |
|---|---|---|---|
| `workspace_knowledge_types.go` | 3-117 | Type definitions: Source, Entity, Claim, Relation, Task, SourceRef, BySourcePayload, ScanRun, CompileSummary | **Port verbatim** as Python pydantic models |
| `workspace_knowledge_files.go` | 22-34, 503-535, 709-723 | Directory layout (`EnsureLayout`, `layoutDirs`), path validation | **Port verbatim** (adapt paths to `pathlib`) |
| `workspace_knowledge_files.go` | 56-129 | Path accessors: `ExtractPath`, `BySourcePath`, `IndexPath`, etc. | **Port pattern** |
| `workspace_knowledge_prompts.go` | 8-58 | The ingest prompt template producing JSON | **Replace** — use a richer template that produces markdown + JSON (see "Change 3" above) |
| `workspace_wiki_service.go` | 49-105, 199-349 | Scan orchestration: queue, walk, hash, extract markdown, prompt LLM, write by-source, compile | **Port the algorithm**, drop Wails plumbing |
| `workspace_wiki_service.go` | 815-837 | `shouldSkipSource` idempotency check | **Port verbatim** |
| `workspace_wiki_service.go` | 1216-1240 | `workspaceKnowledgeStableSourceKey` + `workspaceKnowledgeStableSourceSlug` | **Port verbatim** |
| `workspace_wiki_service.go` | 1258-1323 | Prompt-budget binary search (`buildWorkspaceKnowledgeBySourcePromptWithinBudget`, `trimWorkspaceKnowledgePromptMarkdown`) — adaptively fit the source markdown to model context | **Port** — this is non-obvious and saves us from re-deriving |
| `workspace_knowledge_compile.go` | 46-72 | `CompileWorkspaceKnowledge` entry point | **Port** as `compile_wiki()` |
| `workspace_knowledge_compile.go` | 340-454 | `buildIndexWikiPage`, `buildOverviewWikiPage`, `buildLogWikiPage`, `buildOpenQuestionsPage` | **Reference for layout**; replace with template-driven render |
| `workspace_knowledge_compile.go` | 634-647 | `buildConceptSlugs` with collision-counter disambiguation | **Port verbatim** |
| `workspace_knowledge_compile.go` | 816-843 | `workspaceKnowledgeSlug` kebab-case + ASCII-only slug | **Port verbatim** |
| `workspace_knowledge_query.go` | 449-476 | `retrieveWorkspaceKnowledgeEvidence` — wiki → state → input fallback chain | **Reference**; replace with LLM-driven 4-layer escalation (paper-curator model) |
| `workspace_knowledge_query.go` | 716-799 | Term-overlap scoring (`selectRelevantWorkspaceKnowledgeHits`, `workspaceKnowledgeHitScore`) | **Drop** — we use the LLM to pick relevance, not a hand-tuned BM25 |
| `workspace_knowledge_query.go` | 834-863 | JSONL conversation log append (`appendWorkspaceKnowledgeConversationLog`) | **Port verbatim** |
| `workspace_knowledge_query.go` | 109-202 | `Promote` claim promotion workflow | **Drop for MVP**, see "Change 6" |

---

## The "Promote" workflow — keep or drop?

OpenSciReader's promote (`workspace_knowledge_query.go:109-202`) lets the user mark candidate claims from a Q&A result as "promote to formal knowledge" → merged into `state/claims.json` with canonical-ID dedup and semantic matching.

**Pros**: turns ad-hoc Q&A discoveries into compounding knowledge — addresses Karpathy's "good answers can be filed back."

**Cons**:
- Risk of hallucination contamination — `paper-curator` *explicitly forbids* this for that reason. Query answers are LLM synthesis on top of LLM synthesis; promoting them adds a layer of unverified claims to the knowledge base.
- OpenSciReader's canonical-ID matching is complex (`canonicalWorkspaceKnowledgeClaimID`, `findWorkspaceKnowledgeClaimForCandidate`) — many edge cases (ambiguous match errors, etc.).
- The same effect can be achieved more safely by **re-ingesting** the conversation as a `raw/` source — then it goes through the full ingest pipeline with normal source-attribution.

**Recommendation for XReadAgent**: **skip Promote-as-auto-write**. Replace with the `/crystallize` pattern (from `llm-wiki-skills`, `claude-obsidian`):

- User says "this Q&A was valuable, save it" → agent writes a markdown file to `wiki/queries/{topic}/{date}-{slug}.md` with `source: query` frontmatter.
- These query archives are **readable** by future queries (so the agent can find "I answered this before") but **not** by `ingest`. They do NOT update `index.md` or concept pages.
- If the user later says "promote that Q&A to a real wiki concept," they explicitly re-ingest by dropping the relevant claim into `raw/` with a manually-cited source — going through the normal ingest pipeline with proper provenance.

This is more disciplined than OpenSciReader's auto-promote and avoids the hallucination-feedback problem.

---

## Open questions

1. **Two-LLM-call vs single-LLM-call ingest?** OpenSciReader does JSON-then-render; paper-curator does markdown-directly. We proposed structured-output single-call (both JSON and markdown together). **Validate empirically**: is the markdown quality from a JSON-then-render pipeline actually worse, or just a Go-template artifact? A Python Jinja render with a good template might be just as good.

2. **Should `extracts/{slug}.md` (markitdown output) be the **only** chunk source for the Tier-2 evidence index, or also embed the wiki pages themselves?** Probably both — page embeddings answer "which wiki page is most relevant" and chunk embeddings answer "show me the passage."

3. **Concept-page granularity**: when does "Transformer" stop being one page and become a hub with sub-pages (`transformer/attention`, `transformer/encoder-decoder`)? Need a heuristic — perhaps "split when page > 8KB or > 12 distinct related claims". Not addressed by any prior art.

4. **Handling figures/tables**: Karpathy mentions image-download tricks for Obsidian, but multi-modal LLM ingest of figures from papers (which are often the *most information-dense parts*) is unsolved across all prior art surveyed. PaperQA2 has experimental multimodal support — investigate separately.

5. **Cost model**: at 500 papers × ~30K chars/paper × structured-output LLM call ≈ 15M input tokens for full ingest. At Claude Sonnet pricing that's ~$45 one-time. Acceptable, but worth confirming. Worth caching aggressively.

6. **Versioning**: the wiki is a git repo (Karpathy's tip). Should commits be auto-generated per-ingest or per-session? `llm-wiki-skills` leaves to user; `claude-obsidian` doesn't auto-commit. Probably manual is right — agents shouldn't write to git without consent.

7. **MCP integration**: should XReadAgent's wiki tools be exposed via MCP server (like `qmd mcp`) so multiple agents (Claude Code, Cursor, Codex) can share one wiki? `claude-obsidian` does this via Obsidian Local REST API + MCP. Strong yes for v1.

8. **Do we need a `relations` graph at all for MVP?** OpenSciReader has rich typed relations but they're not very visibly used in the rendered wiki. `paper-curator` skips explicit relations and just uses wikilinks. Probably **defer relations to v2** unless graph queries become a clear use case.

---

## Sources

### Primary

- **Andrej Karpathy, "LLM Wiki" gist** — https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f (fetched 2026-05-22). The canonical pattern description.

### Direct Karpathy-pattern implementations (GitHub, ranked by relevance)

- **AgriciDaniel/claude-obsidian** — https://github.com/AgriciDaniel/claude-obsidian. Claude Code plugin + Obsidian, 11 skills, DragonScale Memory extension, blog: https://agricidaniel.com/blog/claude-obsidian-ai-second-brain.
- **vanillaflava/llm-wiki-skills** — https://github.com/vanillaflava/llm-wiki-skills. Cross-agent skills (Claude/Gemini/Codex/Copilot), 13 page templates, `/crystallize`, `source:`+`reliability:` frontmatter discipline. **The closest fit to XReadAgent's needs.**
- **zzzlxhhh/obsidian-paper-curator** — https://github.com/zzzlxhhh/obsidian-paper-curator. Kimi CLI + Obsidian, 3 skills (paper-injest / paper-query / paper-lint), 4-layer hierarchical retrieval, `queries/` isolation discipline, Python `lint_scan.py`. **Direct prior art for the paper-reading use case.**
- **MykytaMorachovEpam/obsidian-wiki** — https://github.com/MykytaMorachovEpam/obsidian-wiki. Karpathy-faithful Obsidian implementation.
- **Burgunthy/hermes-second-brain** — https://github.com/Burgunthy/hermes-second-brain. AI-powered compound knowledge system.
- **Ac-spider/llm-wiki** — https://github.com/Ac-spider/llm-wiki. ~1,000+ AI/ML concept pages, multi-agent pipeline.
- **avdiam/wiki-forge** — https://github.com/avdiam/wiki-forge.
- **The-Vibe-Company/Granite** — https://github.com/The-Vibe-Company/Granite. Local-first markdown + CLI + MCP.
- **chenhunghan/llm-wiki-skill** and **Coreycore123/llm-wiki-operating-model-skill** — cross-agent skills.

### Tooling

- **Tobi Lütke, qmd** — https://github.com/tobi/qmd. On-device markdown search engine (BM25 + vector + LLM rerank), CLI + MCP server. The canonical "Tier 2 search" Karpathy recommends.
- **Future-House, PaperQA2** — https://github.com/Future-House/paper-qa. State-of-the-art agentic RAG for scientific papers, 8.5k stars. Reference for evidence-retrieval tier.
- **edwin-hao-ai/Awareness-Local** — https://github.com/edwin-hao-ai/Awareness-Local. Markdown + SQLite FTS5 + embeddings for agent memory. Reference architecture for Tier-2.
- **mraza007/echovault** — https://github.com/mraza007/echovault. Markdown + FTS5 + optional semantic. Similar pattern.

### Vector store references

- **asg017/sqlite-vec** — https://github.com/asg017/sqlite-vec. SQLite extension for vectors. Recommended for MVP-Tier-2.
- **lancedb/lancedb** — https://github.com/lancedb/lancedb. Single-file columnar vector store. Recommended for scale.
- **reorproject/reor** — https://github.com/reorproject/reor. Reference implementation of LanceDB + Ollama for local-first markdown AI notes.
- **brianpetro/obsidian-smart-connections** — Obsidian plugin with embedding-based similar-note suggestions. Reference for "embed without mutating" pattern.

### Internal — OpenSciReader (G:/0JHX-code/Project/OpenSciReader/)

- `internal/desktop/workspace_knowledge_types.go` — type model for Sources / Entities / Claims / Relations / Tasks.
- `internal/desktop/workspace_knowledge_files.go` — directory layout, path accessors, validation.
- `internal/desktop/workspace_knowledge_prompts.go` — ingest LLM prompt.
- `internal/desktop/workspace_knowledge_compile.go` — JSON-to-wiki-markdown rendering.
- `internal/desktop/workspace_knowledge_query.go` — query, evidence retrieval, promote.
- `internal/desktop/workspace_wiki_service.go` — scan orchestrator (file walk, hash, extract, prompt, compile).
