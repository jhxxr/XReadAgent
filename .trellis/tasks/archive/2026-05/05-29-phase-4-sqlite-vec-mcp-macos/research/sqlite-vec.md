# Research: sqlite-vec for XReadAgent Vector Search

- **Query**: sqlite-vec for XReadAgent's vector search needs (Phase 4)
- **Scope**: Mixed (internal codebase analysis + external library/API testing)
- **Date**: 2026-05-29

## Findings

### 1. sqlite-vec Overview

**sqlite-vec** is a SQLite extension for vector similarity search, created by Alex Garcia (asg017). It provides a `vec0` virtual table module that stores float32 or int8 vectors directly in SQLite and supports KNN queries via the `MATCH` operator.

- **Current stable version**: 0.1.9 (PyPI: `sqlite-vec`)
- **Available versions on PyPI**: 0.1.0 through 0.1.9
- **Python package**: `sqlite_vec` (underscore, not hyphen)
- **Wheel size**: ~292 KB (Windows amd64), platform-specific wheels available for Linux, macOS (both x86_64 and arm64)
- **License**: MIT
- **GitHub**: https://github.com/asg017/sqlite-vec

**Key API patterns (verified by testing)**:

```python
import sqlite3
import sqlite_vec
import struct

conn = sqlite3.connect("state/vec.sqlite")
conn.enable_load_extension(True)
sqlite_vec.load(conn)
conn.enable_load_extension(False)

# Create a vec0 virtual table with float32 vectors
conn.execute("CREATE VIRTUAL TABLE embeddings USING vec0(vec float[384])")

# Insert: rowid + blob (struct-packed float32 array)
vector = [0.1, 0.2, 0.3]  # ... 384 floats
blob = struct.pack(f"{len(vector)}f", *vector)
conn.execute("INSERT INTO embeddings(rowid, vec) VALUES (?, ?)", (1, blob))

# KNN query: MATCH + k=? parameter (both required)
query_blob = struct.pack(f"{384}f", *query_vector)
cursor = conn.execute(
    "SELECT rowid, distance FROM embeddings WHERE vec MATCH ? AND k = 10",
    (query_blob,)
)
```

**Critical API constraint**: The `k = ?` parameter is **required** on all KNN queries. A bare `LIMIT` clause is insufficient -- the query will fail with `sqlite3.OperationalError: A LIMIT or 'k = ?' constraint is required on vec0 knn queries.` This is a breaking difference from typical SQL patterns.

### 2. sqlite-vec vs Alternatives Comparison

| Store | Format | ANN Support | BM25 Built-in | Best For | Risk |
|---|---|---|---|---|---|
| **sqlite-vec** | SQLite extension (single file) | Brute-force (flat); DiskANN planned | No -- pair with FTS5 | Minimal-deps, single-file, zero-daemon | No ANN at >1M vectors; brute-force OK for <100k |
| **sqlite-vss** | SQLite extension (deprecated) | HNSW via Faiss | No | Predecessor to sqlite-vec | **Deprecated** by author in favor of sqlite-vec |
| **LanceDB** | Columnar `.lance` dir | IVF_PQ, HNSW | Yes (Tantivy) | Scale, multimodal, mature SDK | Larger binary; separate dir (not single file) |
| **Chroma** | SQLite + parquet | HNSW | No | Quick start, popular | Heavy dep tree; daemon mode default |
| **Qdrant local** | Native binary | HNSW | No | Production, fast | Overkill for local-first; server-oriented |
| **FAISS** | In-memory index | IVF, HNSW, PQ | No | Raw performance | In-memory only; no persistence; C++ build |
| **DuckDB VSS** | DuckDB columnar | HNSW (experimental) | Yes (FTS ext) | If already using DuckDB | VSS extension still experimental |

**Prior project decision (plan.md D8)**: sqlite-vec + FTS5 is the chosen backend. The database-guidelines spec at `.trellis/spec/backend/database-guidelines.md` line 180-188 confirms: `{workspace}/state/vec.sqlite` is the target path, treated as a regenerable cache.

**Why sqlite-vec wins for XReadAgent**:
1. Single binary file -- fits the "wiki is a git repo of markdown" aesthetic
2. FTS5 ships in Python's stdlib (verified: Python 3.13 ships SQLite 3.51.0 with FTS5 enabled)
3. ~292 KB Python wheel -- minimal dependency footprint
4. Works with `os.replace` atomic pattern (single file, no directories)
5. Regenerable cache -- `state/sources.json` remains canonical; vec index can be rebuilt
6. Awareness-Local and echovault (real users) prove the pattern at the same use case

### 3. FTS5 Hybrid Search

SQLite's FTS5 (Full-Text Search 5) is available out of the box with Python's bundled sqlite3. It provides BM25 ranking and is the natural complement to sqlite-vec's vector search.

**Verified working pattern**:

```python
# Create FTS5 table alongside vec0
conn.execute("CREATE VIRTUAL TABLE pages_fts USING fts5(title, content)")

# Lexical search with BM25 ranking
cursor = conn.execute(
    "SELECT rowid, rank FROM pages_fts WHERE pages_fts MATCH ? ORDER BY rank LIMIT 10",
    ("attention transformer",)
)
```

**Hybrid RRF (Reciprocal Rank Fusion)**: The recommended integration pattern combines vector and lexical results:

```python
# 1. Vector search
vec_results = {}  # {rowid: rank}
cur = conn.execute(
    "SELECT rowid, distance FROM vec_pages WHERE embedding MATCH ? AND k = 10",
    (query_blob,)
)
for rank, (rowid, dist) in enumerate(cur.fetchall(), 1):
    vec_results[rowid] = rank

# 2. FTS5 search
fts_results = {}  # {rowid: rank}
cur = conn.execute(
    "SELECT rowid, rank FROM pages_fts WHERE pages_fts MATCH ? ORDER BY rank LIMIT 10",
    (query_terms,)
)
for rank, (rowid, _) in enumerate(cur.fetchall(), 1):
    fts_results[rowid] = rank

# 3. RRF merge (k=60 is standard)
k_rrf = 60
all_ids = set(vec_results) | set(fts_results)
rrf_scores = {}
for pid in all_ids:
    score = 0
    if pid in vec_results: score += 1 / (k_rrf + vec_results[pid])
    if pid in fts_results: score += 1 / (k_rrf + fts_results[pid])
    rrf_scores[pid] = score

sorted_results = sorted(rrf_scores.items(), key=lambda x: -x[1])
```

**Verified RRF results** (from test with 5 wiki pages, query "How does the attention mechanism work in transformers?"):
- Self-Attention Mechanism (concept): RRF=0.03252, vec_rank=1, fts_rank=2
- Transformer Architecture (concept): RRF=0.03227, vec_rank=3, fts_rank=1
- Attention Is All You Need (paper): RRF=0.03200, vec_rank=2, fts_rank=3
- BERT (paper): RRF=0.01562, vec_rank=4 (not in FTS5)
- AlphaFold (paper): RRF=0.01538, vec_rank=5 (not in FTS5)

The hybrid approach correctly surfaces all 3 relevant pages at the top, with semantic and lexical signals reinforcing each other.

### 4. Embedding Model Strategy

#### Local Models (ONNX Runtime -- preferred for XReadAgent)

The project already ships `onnxruntime` (1.20.1, pulled transitively by BabelDOC). The `sentence-transformers` library supports `backend='onnx'` which routes inference through onnxruntime instead of PyTorch, avoiding the torch runtime dependency.

**Verified working**: `SentenceTransformer('all-MiniLM-L6-v2', backend='onnx')` -- encodes 4 texts in 0.042s, no torch needed at inference time.

| Model | Dim | Disk Size | Speed | Quality | ONNX Support | Notes |
|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 384 | ~282 MB (cache) | 0.04s/4 texts | Good | Yes (pre-built ONNX in repo) | Best speed/size tradeoff; pre-quantized variants available |
| BAAI/bge-small-en-v1.5 | 384 | ~130 MB | Fast | Good (MTEB top) | Yes | Strong benchmark performer |
| allenai/specter2_base | 768 | ~840 MB (cache) | 0.07s/3 texts | Excellent (scientific) | Yes (auto-export on first use) | SOTA for scientific document similarity; larger footprint |
| BAAI/bge-base-en-v1.5 | 768 | ~420 MB | Medium | Very good | Yes | MTEB top for base category |

**ONNX quantized variants**: The all-MiniLM-L6-v2 repo ships multiple pre-quantized ONNX files:
- `onnx/model.onnx` -- baseline
- `onnx/model_qint8_avx512.onnx` -- INT8 quantized for AVX512 CPUs
- `onnx/model_qint8_arm64.onnx` -- INT8 quantized for ARM64 (macOS Apple Silicon)
- `onnx/model_quint8_avx2.onnx` -- UINT8 quantized for AVX2

**Selection for macOS/Apple Silicon**: The `model_qint8_arm64.onnx` variant would be used on macOS arm64. This is important for the Phase 4 macOS support requirement.

**Recommendation for XReadAgent**: `all-MiniLM-L6-v2` with ONNX backend and platform-appropriate quantized variant. Rationale:
- 384 dimensions keeps vec.sqlite compact (1 vector = 384*4 = 1.5KB raw)
- Pre-built quantized ONNX for arm64 (macOS), avx512, avx2
- No torch at runtime (project constraint: avoids torch at runtime)
- Fast enough for interactive use (<50ms for a query embedding)
- If scientific domain quality is insufficient, `allenai/specter2_base` (768d) can be swapped in

#### API-Based Models (optional fallback)

| API | Model | Dim | Cost | Notes |
|---|---|---|---|---|
| OpenAI | text-embedding-3-small | 1536 | $0.02/1M tokens | Good quality; requires network; not local-first |
| OpenAI | text-embedding-3-large | 3072 | $0.13/1M tokens | Best quality; expensive for bulk embedding |
| Anthropic | (none available) | -- | -- | No embeddings API as of 2026-05 |

API-based embeddings violate the local-first constraint (R-LOCAL-FIRST) and should be an **opt-in fallback only**, not the default.

### 5. Integration Pattern with Existing Wiki Structure

#### Current Wiki Architecture (from codebase analysis)

The wiki has three page types, each with a fixed section skeleton:

| Page Type | File Pattern | Sections | Directory |
|---|---|---|---|
| Paper | `wiki/papers/{slug}.md` | Background, Challenges, Solution, Positioning, Key Concepts, Experiments, Open Questions | `workspace.papers_dir` |
| Concept | `wiki/concepts/{slug}.md` | Summary, Related Papers, Related Claims, Open Questions | `workspace.concepts_dir` |
| Query | `wiki/queries/{topic}/{date}-{slug}.md` | Question, Answer, Sources | `workspace.queries_dir` |

Each page has YAML frontmatter followed by markdown body. The `read_page_frontmatter` function (in `wiki/pages.py:135-157`) extracts frontmatter cheaply. The `read_page_content` function (in `wiki/frontmatter_utils.py:27-44`) extracts the body after frontmatter.

#### What to Embed

**Option A: Embed entire wiki pages (page-level)** -- Recommended for Tier 2.

- Each paper page and concept page gets one embedding
- The embedded text is the full markdown body (all sections concatenated)
- Rowid in vec0 maps to a unique page identifier (could use a hash or a sequential ID)
- Advantage: simple, one row per page, aligns with the wiki abstraction
- Disadvantage: section-specific queries are less precise

**Option B: Embed each section separately (section-level)**

- Each of the 7 paper sections and 4 concept sections gets its own embedding
- More granular retrieval: "which section of which paper is relevant?"
- Disadvantage: 7-11x more vectors per paper, more complex join logic, harder to maintain consistency

**Option C: Hybrid (page embedding + section embeddings)**

- Page-level embedding for top-k retrieval, section-level for fine-grained evidence
- Most flexible but most complex

**Verified test results** (section vs page embedding similarity):
- Full page embedding vs mean-pooled section embeddings: 0.9147 cosine similarity (very similar)
- For the query "How does the transformer handle long sequences?":
  - Page-level similarity: 0.4831
  - Best section (Positioning): 0.5060
  - Worst section (Key Concepts): 0.2326

Section-level retrieval is ~5% more precise for targeted queries but adds significant complexity. For Phase 4 Tier 2, **page-level embedding** is the right starting point.

#### Embedding Timing

**Recommended: Embed during ingest** (in `apply_plan`)

- When `write_paper_page` or `write_concept_page` creates/updates a page, also compute its embedding and insert into vec0
- The `apply_plan` function (`agents/ingest.py:98-216`) already handles all post-planner persistence
- Adding a `VectorIndex.update(page_slug, embedding_blob)` call fits the existing pattern
- Advantage: embeddings are always in sync with wiki content
- Disadvantage: adds ~50ms per ingest for the embedding computation

**Alternative: Lazy embed on first vector query** -- more complex, risk of stale embeddings.

#### Database Schema Design

```sql
-- In {workspace}/state/vec.sqlite

-- Vector table: one row per wiki page (paper + concept + query)
CREATE VIRTUAL TABLE vec_pages USING vec0(embedding float[384]);

-- Metadata table: stores page identity + content hash for cache invalidation
CREATE TABLE pages(
    id INTEGER PRIMARY KEY,       -- rowid shared with vec_pages
    slug TEXT NOT NULL UNIQUE,     -- e.g. "attention-is-all-you-need-a1b2c3"
    page_type TEXT NOT NULL,       -- "paper" | "concept" | "query"
    content_hash TEXT NOT NULL,    -- sha256 of the embedded text (for stale detection)
    created_at TEXT NOT NULL,      -- ISO 8601 UTC
    updated_at TEXT NOT NULL       -- ISO 8601 UTC
);

-- FTS5 table: full-text search over page titles + content
CREATE VIRTUAL TABLE pages_fts USING fts5(
    title,
    content,
    content=pages,
    content_rowid=id
);
```

**Note on FTS5 content= syntax**: The `content=pages` option makes FTS5 an external-content table that reads from the `pages` table, avoiding data duplication. However, this requires manual `INSERT INTO pages_fts(rowid, title, content) VALUES (...)` on every write and `INSERT INTO pages_fts(pages_fts, rowid, title, content) VALUES ('delete', ...)` on deletes. A simpler approach is an independent FTS5 table (no content=), at the cost of storing content twice. Given that wiki pages are typically <10KB each and the workspace targets <300 papers (~3MB total), the duplication is acceptable.

#### Integration Points in Existing Code

| File | Current Role | Vector Integration Point |
|---|---|---|
| `wiki/pages.py:write_paper_page` | Writes paper .md files | Call `VectorIndex.upsert(slug, "paper", text)` after write |
| `wiki/pages.py:write_concept_page` | Writes concept .md files | Call `VectorIndex.upsert(slug, "concept", text)` after write |
| `wiki/pages.py:write_query_page` | Writes query .md files | Call `VectorIndex.upsert(slug, "query", text)` after write |
| `agents/ingest.py:apply_plan` | Orchestrates all post-planner writes | Add VectorIndex initialization + upserts alongside wiki writes |
| `agents/tools.py:build_ingest_tools` | 7 tools for ingest agent | Add `semantic_search(query, k=10)` tool |
| `agents/query_tools.py:build_query_tools` | 9 tools for query agent | Add `semantic_search(query, k=10)` tool |
| `wiki/index_regen.py:regenerate_index` | Rebuilds wiki/index.md | Pattern reference for index rebuild |
| `wiki/workspace.py:Workspace` | Path accessor hub | Add `vec_sqlite_path` accessor returning `self.state_dir / "vec.sqlite"` |

#### New Module: `wiki/vector.py`

Following the existing wiki module patterns (single owner, atomic writes, lazy load):

```python
# wiki/vector.py -- proposed shape
class VectorIndex:
    """Manages {workspace}/state/vec.sqlite: embeddings + FTS5 for wiki pages."""

    def __init__(self, workspace: Workspace, *, embedding_dim: int = 384): ...

    @classmethod
    def load(cls, workspace: Workspace) -> VectorIndex: ...

    def upsert(self, slug: str, page_type: str, text: str) -> None: ...
    def delete(self, slug: str) -> None: ...
    def search(self, query: str, *, k: int = 10, page_type: str | None = None) -> list[dict]: ...
    def search_fts(self, query: str, *, k: int = 10) -> list[dict]: ...
    def search_hybrid(self, query: str, *, k: int = 10) -> list[dict]: ...
    def rebuild(self) -> None: ...  # Re-embed all wiki pages from disk
    def is_stale(self, slug: str, content_hash: str) -> bool: ...
```

This follows the existing single-owner-per-file pattern from database-guidelines.md.

#### Embedding Service

The embedding computation should live in a separate module that can be lazy-imported (following the existing "lazy import of heavy deps" pattern from quality-guidelines.md):

```python
# wiki/embedder.py -- proposed shape
class WikiEmbedder:
    """Embeds text using a local ONNX model. Lazy-loads on first use."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"): ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, query: str) -> list[float]: ...

    @property
    def dimension(self) -> int: ...
```

Lazy import pattern ensures `import xreadagent` stays near-instant even when sentence-transformers is installed.

### 6. vec.sqlite as Regenerable Cache

Per database-guidelines.md line 185-188:

> Single-file SQLite, no daemon, gitignored. Treated as a regenerable cache -- `state/sources.json` remains the canonical source of truth and the vector index can be rebuilt from `extracts/` + wiki pages.

This means:
- `vec.sqlite` should be added to `.gitignore` (like other `state/` files)
- A `rebuild` command should re-embed all wiki pages from disk
- The index is NOT a source of truth -- if it's deleted or corrupted, it can be recreated
- `content_hash` in the `pages` table enables stale detection (compare against file sha256)

### 7. macOS / Apple Silicon Considerations

The task title includes "macOS 支持". Key findings:

- **sqlite-vec**: Ships arm64 wheels for macOS. The `sqlite_vec.load(conn)` pattern works identically on arm64.
- **ONNX Runtime**: Already working on macOS (BabelDOC uses it). The `onnxruntime` package ships native arm64 wheels.
- **ONNX model quantization**: The `all-MiniLM-L6-v2` repo includes `model_qint8_arm64.onnx` specifically for ARM64 inference.
- **hyperscan**: BabelDOC transitively depends on hyperscan which is x86-only. This is a separate concern (already tracked in macos-electron.md research).
- **sqlite-vec on-disk size**: 1,613,824 bytes (1.54 MB) for a database with 1 vector. With 100 pages at 384d, expect ~3-5 MB total.

### 8. Performance Characteristics

**Embedding speed** (verified on Windows, ONNX backend, all-MiniLM-L6-v2):
- Model load: ~45s (cold cache), ~0s (warm cache after first load)
- Encode 4 texts: 0.042s (10.5ms per text)
- Encode 1 query: <15ms

**sqlite-vec query speed** (in-memory, 5 vectors, 384d):
- KNN with k=3: <1ms
- KNN + join with metadata: <1ms
- FTS5 query: <1ms

**Scaling estimates for XReadAgent workspace**:
- 100 papers x 384d float32 = ~150KB raw vectors
- 300 papers x 384d float32 = ~450KB raw vectors
- SQLite overhead: ~1.5MB base + ~5KB per vector
- Total vec.sqlite for 300 papers: ~3-5 MB
- Brute-force KNN on 300 vectors: <5ms (well within interactive limits)

### Files Found

| File Path | Description |
|---|---|
| `backend/src/xreadagent/wiki/__init__.py` | Wiki module public API, re-exports all wiki primitives |
| `backend/src/xreadagent/wiki/pages.py` | Page writers: `write_paper_page`, `write_concept_page`, `write_query_page`; also `read_page_frontmatter` |
| `backend/src/xreadagent/wiki/workspace.py` | `Workspace` dataclass with path accessors; `init_empty` creates seed files |
| `backend/src/xreadagent/wiki/paths.py` | `WORKSPACE_LAYOUT` dict, slug helpers, path validation |
| `backend/src/xreadagent/wiki/index_regen.py` | Deterministic `wiki/index.md` regeneration (pattern reference for vec index rebuild) |
| `backend/src/xreadagent/wiki/sources.py` | `SourcesIndex` + `compute_content_hash` (pattern reference: lazy-load, idempotent) |
| `backend/src/xreadagent/wiki/distillation.py` | `DistillationPayload` per-paper JSON (pattern reference: save/load) |
| `backend/src/xreadagent/wiki/atomic.py` | `atomic_write_text`, `atomic_write_bytes`, `append_text_locked` |
| `backend/src/xreadagent/wiki/frontmatter_utils.py` | `read_page_content`, `list_papers`, `list_concepts`, `list_queries` |
| `backend/src/xreadagent/wiki/log.py` | `WikiLog` (markdown) + `WikiConversationLog` (JSONL) |
| `backend/src/xreadagent/agents/ingest.py` | `IngestAgent` + `apply_plan` (primary integration point for embed-on-ingest) |
| `backend/src/xreadagent/agents/tools.py` | 7 ingest tools including `search_wiki` (keyword grep -- vector search adds to this) |
| `backend/src/xreadagent/agents/query.py` | `QueryAgent` (receives vector search as a new tool) |
| `backend/src/xreadagent/agents/query_tools.py` | 9 query tools (vector search adds to this) |
| `backend/src/xreadagent/agents/orchestrator.py` | Ingest orchestrator (calls `apply_plan`) |
| `backend/src/xreadagent/agents/query_orchestrator.py` | Query orchestrator |
| `.trellis/spec/backend/database-guidelines.md` | Spec: vec.sqlite path, regenerable cache contract, Phase 4 gate |
| `.trellis/spec/backend/quality-guidelines.md` | Spec: D8 no-vector-in-v1 rule (to be lifted in Phase 4), atomic writes, layering rules |
| `.trellis/spec/backend/directory-structure.md` | Spec: workspace layout, layering rules, page section skeletons |
| `.trellis/spec/backend/index.md` | Backend spec index; references Phase 4 sqlite-vec + MCP |
| `pyproject.toml` | Dependencies: no vector/embed deps yet; onnxruntime transitively via babeldoc==0.6.2 |
| `backend/src/xreadagent/translation/babeldoc_adapter.py` | BabelDOC ONNX usage reference (lazy import pattern, arm64 considerations) |

### Related Specs

- `.trellis/spec/backend/database-guidelines.md` -- vec.sqlite path and regenerable cache contract
- `.trellis/spec/backend/quality-guidelines.md` -- D8 rule (no vector in v1), layering rules, forbidden patterns
- `.trellis/spec/backend/directory-structure.md` -- Workspace layout, page section skeletons, layering rule
- `.trellis/spec/backend/index.md` -- Phase 4 status tracking
- `.trellis/tasks/archive/2026-05/05-22-build-sciresearch-agent-literature-reading-knowledge-base/plan.md` -- D8 decision (no vector in v1), Phase 4 roadmap
- `.trellis/tasks/archive/2026-05/05-22-build-sciresearch-agent-literature-reading-knowledge-base/research/llm-wiki-prior-art.md` -- Original vector store comparison table, hybrid query design

### External References

- [sqlite-vec GitHub](https://github.com/asg017/sqlite-vec) -- Official repo, docs, API reference
- [sqlite-vec PyPI](https://pypi.org/project/sqlite-vec/) -- Python package, version 0.1.9
- [sentence-transformers docs](https://www.sbert.net/) -- Embedding model library, ONNX backend support
- [all-MiniLM-L6-v2 on HuggingFace](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) -- Recommended model, pre-built ONNX variants
- [allenai/specter2_base on HuggingFace](https://huggingface.co/allenai/specter2_base) -- Scientific domain model, 768d
- [BAAI/bge-small-en-v1.5 on HuggingFace](https://huggingface.co/BAAI/bge-small-en-v1.5) -- MTEB top performer, 384d
- [SQLite FTS5 docs](https://www.sqlite.org/fts5.html) -- Full-text search extension reference

## Caveats / Not Found

- **sqlite-vec ANN support**: No approximate nearest neighbor (HNSW, IVF) yet. Brute-force is fine for <100k vectors (XReadAgent targets <300 papers = ~600 page vectors). DiskANN is mentioned in sqlite-vec docs as planned but not yet available in v0.1.9.
- **torch dependency for model download**: While inference uses ONNX Runtime (no torch), the first-time model download via `sentence-transformers` may pull torch as a transitive dependency. The `[onnx]` extra (`pip install sentence-transformers[onnx]`) installs `optimum` + `onnxruntime` but the base `sentence-transformers` package still lists `torch` as a dependency. This needs investigation: either use `optimum` directly (without sentence-transformers) or accept torch as a download-time-only dep.
- **BabelDOC hyperscan on macOS**: The `hyperscan` library (x86-only) is a transitive BabelDOC dependency. This blocks macOS support for translation but does NOT block vector search. Already tracked in `macos-electron.md` research file.
- **FTS5 content= external content tables**: The `content=` option for FTS5 requires manual re-indexing on every write/delete. The simpler independent FTS5 table approach (storing content twice) is recommended for Phase 4 simplicity. If content size becomes an issue, migrate to external content tables later.
- **vec.sqlite concurrency**: The Phase 1 single-sidecar assumption means only one process writes to vec.sqlite. If a future translation worker also reads it, file locking (`portalocker`) may be needed. Out of scope for Phase 4.
- **Query page embedding**: Whether to embed query archive pages is debatable. They are isolated (never modify synthesis zone) and are typically user-specific Q&A rather than research knowledge. Recommend NOT embedding queries in Phase 4; add if users request it.