# Logging Guidelines

## Two Log Surfaces

The backend uses workspace logs as product/audit state more than Python logging.

- `wiki/log.md` is the human-readable synthesis ledger for operations that change wiki state, such as conversion/ingest/crystallize.
- `state/conversation-log.jsonl` is the audit trail for agent interactions, queries, translation events, and failures.

Reference files: `backend/src/xreadagent/wiki/log.py`, `backend/src/xreadagent/pipeline/router.py`, `backend/src/xreadagent/agents/query_orchestrator.py`, `backend/src/xreadagent/translation/service.py`.

## What To Log

Log durable events that help users or future agents understand workspace history:

- Source conversion: subject/title and files touched.
- Query archive: question, topic, archive path, sources cited, layers used, confidence, token usage.
- Translation finish/cache/error: job id, source slug/hash, target language, model, output paths, duration, cached flag.
- Ingest failures: job id, file path, model, active stage, message.

## What Not To Log

- API keys or provider credentials.
- Full request headers that may contain secrets.
- Large document bodies or full LLM prompts unless a dedicated audit format exists.
- Unbounded tracebacks or binary data.

## Append Discipline

Append-only logs should go through `WikiLog`, `WikiConversationLog`, or `append_text_locked`. These helpers keep formatting and fsync behavior consistent.

## Operation-Specific Rules

- Query operations should not append to `wiki/log.md`; they archive under `wiki/queries` and append to the conversation log.
- Translation cache hits append only to the conversation log because no wiki state changed.
- Translation finishes also avoid `wiki/log.md`; translations are isolated under `translations/`.
- Conversion appends to `wiki/log.md` because it changes the source/extract substrate used by synthesis.

## Anti-Patterns

- Do not use ad hoc print statements as durable product logs.
- Do not create a second log format for a new job type if `WikiConversationLog` can represent it.
- Do not record secrets from settings providers or per-request model credentials.
