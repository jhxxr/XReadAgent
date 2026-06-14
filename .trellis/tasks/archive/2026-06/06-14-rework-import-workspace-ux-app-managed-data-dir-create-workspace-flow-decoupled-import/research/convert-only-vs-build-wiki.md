# Research: convert-only (register) vs build-wiki separation

## Conclusion

The backend **already** cleanly separates "register a document" from "build the wiki",
so decoupled import needs no new conversion logic — only a new entry point that stops
after convert.

## Evidence

- `backend/src/xreadagent/pipeline/router.py` → `convert_source(workspace, input_path, ...)`
  does the full **register** step and NOTHING LLM-related:
  1. content hash + stable slug, 2. idempotency short-circuit on `sources.json` + extract,
  3. route by suffix (PDF→MinerU, office/web→markitdown), 4. write `extracts/{slug}.md`,
  5. archive raw under `raw/_processed/{slug}.{ext}`, 6. record `Source` in `SourcesIndex`
  + append `convert` row to `wiki/log.md`. Returns `(ConvertResult, Source)`.

- `backend/src/xreadagent/agents/orchestrator.py` → `ingest_source(...)` is literally
  `convert_source(...)` **then** `agent.ingest(...)` (the LLM analyze+write). It already:
  - emits `on_phase("converting")` before convert, `on_phase("analyzing")` before LLM;
  - short-circuits (cache_hit, no LLM) when `wiki/papers/{slug}.md` already exists.

## Design implication

- **Register (import)** = call `convert_source` only (no agent). Idempotent re-import is free.
- **Build Wiki** = run `ingest_source` / `agent.ingest` on an already-registered source.
  The convert step inside will hit the idempotency short-circuit (extract already on disk),
  then run the LLM and write `wiki/papers/{slug}.md` + concept pages.
- The existing `IngestJobService` (`api/ingest_jobs.py`) is the model for a job; add a
  `mode` (`register` | `wiki`) or a second lightweight job that runs convert-only and
  emits just the `converting` stage. Translation is already its own job
  (`translation/service.py`) and stays independent.
