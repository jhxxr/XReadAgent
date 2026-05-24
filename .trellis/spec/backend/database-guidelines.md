# Database Guidelines

> XReadAgent has no database. State lives in files. This doc explains why and how.

---

## Overview

XReadAgent is **local-first** (PRD requirement R-LOCAL-FIRST) and follows Karpathy's LLM-Wiki contract: all state is plain markdown + JSON on the user's disk. **No SQLite, no Postgres, no key-value store** lives in v1.

This isn't laziness — it's a hard product constraint. The wiki must be:
- Readable in any markdown viewer or Obsidian without our tooling.
- Syncable via syncthing / Dropbox / git without conflict-resolution headaches a binary DB would create.
- Portable across machines by `rsync` or copy-paste.

A database would break all three.

---

## The File-Based State Model

```
{workspace}/state/
├── sources.json               Manifest: list[Source] with contentHash for idempotency.
├── by-source/
│   └── {slug}.json            Per-paper distillation (entities/claims/relations/tasks).
├── compile-summary.json       Bookkeeping: is wiki dirty? last-compile-at?
└── conversation-log.jsonl     Append-only event log.
```

`wiki/` is the human-readable view; `state/` is the machine-readable substrate. Both are flat files. Loading a workspace = walking the file tree.

---

## Required Patterns

### Pattern: Atomic write triad (see also Quality Guidelines)

Every write to `state/*.json` or `state/by-source/*.json` routes through `xreadagent.wiki.atomic.atomic_write_text`:

1. Write content to `path.tmp`.
2. fsync the tmp file.
3. `os.replace(tmp, path)` — atomic on POSIX + Windows.

**Why**: a crash mid-write must never leave a half-written `sources.json` that future loads silently mis-parse.

### Pattern: Single-writer-per-file

Each state file has exactly one owner module:

| File | Owner |
|---|---|
| `state/sources.json` | `wiki/sources.py:SourcesIndex` |
| `state/by-source/{slug}.json` | `wiki/distillation.py` |
| `state/compile-summary.json` | `wiki/workspace.py` (created by `init_empty`); future agents update via dedicated helper |
| `state/conversation-log.jsonl` | `wiki/log.py:WikiConversationLog` |
| `wiki/log.md` | `wiki/log.py:WikiLog` |
| `wiki/index.md` | `wiki/index_regen.py` |
| `wiki/overview.md` | `wiki/workspace.py` (init only); future overview-regen agent (Phase 3) |
| `wiki/papers/{slug}.md` | `wiki/pages.py:write_paper_page` |
| `wiki/concepts/{slug}.md` | `wiki/pages.py:write_concept_page` + `agents/_merge.py:merge_concept_into_page` |
| `wiki/queries/{topic}/...` | `wiki/pages.py:write_query_page` (called only from `agents/query_orchestrator.py`) |

If you find yourself writing the same file from two places, **consolidate the writer** — don't duplicate.

### Pattern: Idempotent operations via contentHash

`compute_content_hash(path)` returns sha256 of raw bytes. Stored on `Source.contentHash`. Used for:

- **Re-ingest short-circuit**: same hash + extract exists → skip converter + skip LLM.
- **Audit**: detect when a source was edited outside XReadAgent (rare; we own `raw/`).
- **Future sync**: contentHash is the natural merge key for multi-machine wikis.

### Pattern: Lazy load, eager save

```python
# Load only when needed
sources = SourcesIndex.load(workspace)
existing = sources.find_by_hash(h)

# Save right after every mutation — don't batch
if sources.add_or_update(new_source):
    sources.save()
```

**Why**: no in-memory caching across requests. The next request loads fresh. Batched saves would defeat the atomicity guarantee.

---

## Schema Discipline

State JSON files use **camelCase** field names to stay wire-compatible with OpenSciReader's Go JSON tags. This means a user's `state/by-source/*.json` can be exchanged between OpenSciReader and XReadAgent.

```python
# wiki/sources.py
class Source(_Strict):
    sourceId: str
    title: str
    slug: str
    kind: Literal["pdf", "docx", "html", ...]
    sourcePath: str
    contentHash: str           # sha256 hex
    ingestedAt: str            # UTC ISO 8601 with Z
    pageCount: int
    extractPath: str
    lastError: str | None = None
```

camelCase here is **intentional and load-bearing** — don't "fix" it to snake_case. See `quality-guidelines.md` §"camelCase vs snake_case" for the full rule.

---

## Migrations

Phase 0 + 1A schemas are the v1 wire format. When we evolve a schema:

1. **Additive changes** (new optional field with a default) — no migration needed. Old files load fine because Pydantic strict mode allows missing optional fields with defaults.
2. **Breaking changes** (rename field, change type, remove field) — write a one-shot migration script under `backend/src/xreadagent/migrations/{date}_{description}.py` that:
   - Detects the old schema version (presence/absence of a field).
   - Rewrites the file via atomic write.
   - Logs to `state/migrations.log`.
3. **Migration is idempotent** — running it twice on already-migrated state is a no-op.

We avoid breaking changes when we can. Each one is reviewed in the relevant phase plan.

---

## Concurrency Model

Phase 1 assumes **a single FastAPI sidecar process** owns the workspace at any time. The Electron loader enforces this by spawning one sidecar per workspace.

Within the sidecar:
- All append-only writes (`wiki/log.md`, `state/conversation-log.jsonl`) use a module-level `threading.Lock`.
- Replace-style writes (`state/sources.json`, `wiki/papers/*.md`) rely on `os.replace` atomicity — last writer wins. This is acceptable because the SourcesIndex is single-writer per the table above; there is no concurrent reader-vs-writer race on a given path.

If we ever need **multi-process** safety (e.g., a separate translation worker also touching state), we'll move to file locks (`portalocker`) — gated on a real need, not speculation.

---

## Common Mistakes

### Mistake: Treating `extracts/` as part of state

**Symptom**: PR adds an `extract_hash` field to `Source` to detect when the extract was modified.

**Cause**: confused `extracts/` (regenerable cache) with `state/` (authoritative state).

**Fix**: `extracts/` is rebuildable from `raw/` via the pipeline. Don't make it a source of truth. The only metadata we keep about extracts is the path inside `Source.extractPath`.

**Prevention**: directory-structure.md is explicit about this.

---

### Mistake: Holding a SourcesIndex in memory across requests

**Symptom**: ingest of paper B doesn't see paper A that was just ingested in the parallel request — both copies of `SourcesIndex` have a stale view.

**Cause**: caching `SourcesIndex.load(...)` at module level.

**Fix**: `SourcesIndex.load(workspace)` per call. The hot path here is a JSON read of usually <100KB — fine.

**Prevention**: code review — no `_index_cache` module-level dict.

---

### Mistake: Writing JSON without `sort_keys=True` for state files

**Symptom**: git diff on `state/sources.json` shows reordered fields for no functional reason.

**Cause**: default Pydantic / json.dump field ordering is insertion-based.

**Fix**: `json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True)` — stable diffs.

**Prevention**: helper in `wiki/atomic.py` (Phase 2 — currently not enforced).

---

## When (Maybe) a Database

If/when we add an embedding tier (Phase 4, D8), **`sqlite-vec` + FTS5** is the chosen backend per `plan.md` §1. It lives at:

```
{workspace}/state/vec.sqlite
```

Single-file SQLite, no daemon, gitignored. Treated as a regenerable cache — `state/sources.json` remains the canonical source of truth and the vector index can be rebuilt from `extracts/` + wiki pages.

This is **not** a Phase 1 concern. Adding `sqlite-vec` in v1 is a **forbidden pattern** (see Quality Guidelines).
