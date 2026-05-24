# Logging Guidelines

> Two-stream logging model in XReadAgent.

---

## Overview

XReadAgent has **two distinct log streams**, by design:

| Stream | Path | Format | Audience | What gets logged |
|---|---|---|---|---|
| **Synthesis log** | `wiki/log.md` | Markdown, append-only | Human (the researcher) | Synthesis ops only: ingest / crystallize / lint |
| **Conversation log** | `state/conversation-log.jsonl` | JSONL, append-only | Machine (audit, debug) | Every event: ingest_started / ingest_complete / query / crystallize / lint / errors |

Plus **stdlib `logging`** for runtime diagnostics that don't belong in either of the above (rare — see §runtime-logging below).

**Hard rule**: a `query` op writes to `state/conversation-log.jsonl` only — **never** to `wiki/log.md`. The synthesis log is reserved for ops that modify the wiki's synthesis zone. Queries don't, and shouldn't pollute the human-facing changelog.

---

## Stream 1 — Synthesis Log (`wiki/log.md`)

### Format

```markdown
## [2026-05-22T10:34:17Z] ingest | attention-is-all-you-need-a1b2c3d4e5f6
- files: wiki/papers/attention-is-all-you-need-a1b2c3d4e5f6.md, wiki/concepts/transformer.md, wiki/index.md

## [2026-05-22T11:02:08Z] crystallize | promoted RLHF insights from queries/rl/2026-05-22-what-is-rlhf
- files: wiki/papers/instruct-gpt-1234567890ab.md, wiki/concepts/rlhf.md
```

### When to append

| Operation | Append? |
|---|---|
| Ingest succeeds | Yes — `op="ingest"`, subject = `paper_slug`, files = touched wiki paths |
| Ingest cache-hit (re-drop of same paper) | No — nothing changed |
| Crystallize applied | Yes — `op="crystallize"`, subject = one-line rationale, files = touched paths |
| Lint runs (Phase 3) | Yes — `op="lint"`, subject = summary, files may be empty (lint reports, doesn't write) |
| Query answered | **No — see Conversation Log** |
| Translation done | No — translation doesn't touch the wiki |
| Conversion only (no ingest) | No — converter output is regenerable cache, not synthesis |

### API

```python
from xreadagent.wiki.log import WikiLog
log = WikiLog(workspace)
log.append("ingest", "attention-is-all-you-need-a1b2c3d4e5f6",
           files_touched=["wiki/papers/...", "wiki/concepts/..."])
```

`WikiLog.append` is locked (process-wide `threading.Lock`) and uses `append_text_locked` from `wiki/atomic.py`.

### Timestamp format

**Always UTC ISO 8601 with `Z` suffix**: `2026-05-22T10:34:17Z`. Local timezones are forbidden in any persisted artifact — the wiki is portable across machines.

---

## Stream 2 — Conversation Log (`state/conversation-log.jsonl`)

### Format

One JSON object per line. Required fields: `ts`, `event`. Event-specific payload follows.

```jsonl
{"ts":"2026-05-22T10:34:17Z","event":"ingest_started","source_id":"src-...","slug":"attention-..."}
{"ts":"2026-05-22T10:34:51Z","event":"ingest_complete","slug":"attention-...","tokens_used":{"input":12345,"output":2345,"total":14690},"duration_s":34.2,"files_touched":[...]}
{"ts":"2026-05-22T10:55:02Z","event":"query","question":"What's RLHF?","topic":"rl","archive_path":"wiki/queries/rl/...","tokens_used":{...},"confidence":"high"}
{"ts":"2026-05-22T11:02:08Z","event":"crystallize","query_archive_path":"wiki/queries/rl/...","rationale":"...","files_touched":[...]}
```

### When to append

Every domain event. The conversation log is the **full audit trail** — given just this file plus `raw/`, you can reconstruct everything that happened.

### API

```python
from xreadagent.wiki.log import WikiConversationLog
clog = WikiConversationLog(workspace)
clog.append({"event": "query", "question": q, "topic": topic, ...})  # ts auto-injected if absent
```

### What to log per event

| Event | Required payload fields |
|---|---|
| `ingest_started` | `source_id`, `slug` |
| `ingest_complete` | `slug`, `tokens_used`, `duration_s`, `files_touched` |
| `ingest_failed` | `slug`, `error_type`, `error_message`, `duration_s` |
| `query` | `question`, `topic`, `archive_path`, `tokens_used`, `confidence`, `layers_used` |
| `crystallize` | `query_archive_path`, `rationale`, `files_touched`, `tokens_used` |
| `lint` | `summary`, `orphans`, `contradictions`, `stale_claims` (Phase 3) |
| `translation_complete` | `source_id`, `mono_path`, `dual_path`, `duration_s` (Phase 2) |

---

## Stream 3 — Runtime Logging (stdlib `logging`)

For diagnostics that don't belong in either persisted log: subprocess stdout, retry attempts, dev-time progress, etc.

```python
import logging
log = logging.getLogger(__name__)
log.debug("markitdown converter starting on %s", input_path)
log.warning("MinerU subprocess exited %d on retry %d", code, attempt)
```

### Levels

| Level | When to use |
|---|---|
| `DEBUG` | Per-step tracing useful only when investigating. Off by default. |
| `INFO` | Lifecycle events: sidecar startup, model download progress. |
| `WARNING` | Recovered failures, retries, deprecated config. |
| `ERROR` | Unrecovered failures the user needs to see. |
| `CRITICAL` | Sidecar can't continue. Rare. |

### Configuration

- Default level: `INFO` in production, `DEBUG` when `XREADAGENT_LOG_DEBUG=1`.
- Format: plain text to stderr in dev; structured JSON to file (path TBD) in packaged builds. Phase 2 pins the packaged format.
- No third-party logging library (no loguru, no structlog) until/unless we have a concrete need. stdlib `logging` is fine.

---

## What NOT to Log

### Never persist:
- **API keys** for any LLM provider — neither in `wiki/log.md`, `conversation-log.jsonl`, nor stdout logs. They live in `LLMGatewayConfig` (in-memory, loaded from env / settings).
- **Full PDF text** — keep raw content in `raw/` and extracts in `extracts/`; do not duplicate into log streams.
- **Full LLM responses** — `tokens_used` summary is enough. The full response is the wiki content itself.
- **User-typed search queries with PII intent** — record the question text, but do not enrich with user identity, IP, etc. We don't collect those.

### Optional outbound (off by default per D10):

- **LangSmith traces** — opt-in via `LANGSMITH_TRACING=true` env var.
- **Pydantic Logfire** — opt-in via `LOGFIRE_TOKEN` env var.

Both go to third parties — surface this clearly in settings UI so users understand the trade-off.

---

## Common Mistakes

### Mistake: Appending query archives to `wiki/log.md`

**Symptom**: After a query, `wiki/log.md` contains a `## [...] query | what is rlhf?` entry.

**Cause**: copy-pasted ingest's logging code into the query orchestrator.

**Fix**: queries go to `state/conversation-log.jsonl` only. The query archive itself lives at `wiki/queries/{topic}/{date}-{slug}.md` and is discoverable by the wiki browser, not by `log.md`.

**Prevention**: `test_query_isolation` includes a byte-digest assertion on `wiki/log.md`.

---

### Mistake: Using local timezones in timestamps

**Symptom**: Two contributors' wikis show timestamps off by 8 hours.

**Cause**: someone used `datetime.now()` instead of `datetime.now(UTC)`.

**Fix**: use `datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")`. Or use the helper in `wiki/log.py`.

**Prevention**: code review checklist + grep for `datetime.now(` outside `wiki/log.py`.

---

### Mistake: Logging into both streams "to be safe"

**Symptom**: Every ingest writes to `wiki/log.md` AND a duplicate `event: ingest_complete` row in `conversation-log.jsonl`.

**Cause**: defensive duplication.

**Fix**: synthesis ops write to BOTH — `wiki/log.md` for humans, `conversation-log.jsonl` for machines. They carry different fields and serve different audiences. This is intentional. (The mistake is *only* when a non-synthesis op like query writes to both.)

---

## Examples

- `wiki/log.py:WikiLog.append` — the canonical synthesis-log writer.
- `wiki/log.py:WikiConversationLog.append` — the canonical conversation-log writer.
- `agents/orchestrator.py` — example call site that writes both (synthesis op).
- `agents/query_orchestrator.py` — example call site that writes **only** the conversation log (non-synthesis op).
