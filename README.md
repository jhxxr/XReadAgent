# XReadAgent

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

A scientific research agent that turns the papers you read into a compounding,
navigable LLM-Wiki (Karpathy pattern) instead of a forgotten folder of PDFs.
Layout-preserving translation, agent-driven Q&A, and a markdown-native
knowledge base that stays portable across editors.

**Status:** Phase 0 (skeleton). The Python sidecar, schemas, wiki path
contract, and LLM gateway are wired; agent layer, PDF pipeline, translation
worker, and React UI land in later phases.

## Dev quickstart

```sh
uv sync
uv run pytest -xvs
uv run python -m xreadagent.api --port 0
```

The sidecar prints `SIDECAR_READY port=<N>` on stdout once uvicorn finishes
startup. Hit `http://127.0.0.1:<N>/healthz` to confirm.

## Smoke test (real LLM, end-to-end)

The `xreadagent` console script wraps the ingest / query / show flows so you
can verify the IngestAgent end-to-end with your own API key. No FastAPI, no
React UI — just the agent stack.

```sh
# 1. Configure an API key (copy .env.example -> .env.local and fill in)
cp .env.example .env.local

# 2. Initialize a workspace
uv run xreadagent init ./workspaces/scratch --title "Scratch Notes"

# 3. Drop the bundled sample paper into raw/
cp backend/scripts/samples/sample-paper.md ./workspaces/scratch/raw/

# 4. Ingest with a real LLM
uv run xreadagent ingest ./workspaces/scratch/raw/sample-paper.md \
    --workspace ./workspaces/scratch \
    --model anthropic:claude-sonnet-4-6

# 5. Inspect the result (the slug is printed by step 4)
uv run xreadagent show --workspace ./workspaces/scratch index
uv run xreadagent show --workspace ./workspaces/scratch paper <slug-from-step-4>
uv run xreadagent show --workspace ./workspaces/scratch log --tail 5

# 6. Ask a question
uv run xreadagent query "what compact-transformer trick recovers the most quality?" \
    --workspace ./workspaces/scratch \
    --model anthropic:claude-sonnet-4-6
```

Supported `--model` prefixes (one provider key required per prefix you use):

| Prefix          | Env var            | Example                          |
|-----------------|--------------------|----------------------------------|
| `openai:`       | `OPENAI_API_KEY`   | `openai:gpt-4o`                  |
| `anthropic:`    | `ANTHROPIC_API_KEY`| `anthropic:claude-sonnet-4-6`    |
| `google_genai:` | `GOOGLE_API_KEY`   | `google_genai:gemini-2.5-pro`    |
| `ollama:`       | (none)             | `ollama:llama3.1:70b`            |

The sample paper is a fake fixture for smoke testing only. Drop your own
PDFs into `workspaces/{ws}/raw/` once MinerU is installed; the router
selects markitdown / MinerU automatically based on suffix.

## Translation (Phase 2A)

Layout-preserving PDF translation is wired via `babeldoc==0.6.2` in a
subprocess-isolated worker. Outputs land under `workspaces/{ws}/translations/`
without touching the wiki or extracts (D4-style isolation).

```sh
# Translate a paper. Mono + dual PDFs land in translations/.
uv run xreadagent translate ./workspaces/scratch/raw/paper.pdf \
    --workspace ./workspaces/scratch \
    --model anthropic:claude-sonnet-4-6 \
    --target zh
```

The CLI prints stage events to stderr (`stage_start parsing`,
`stage_progress translation 42.5%`, etc.) and the final `key: value` summary
to stdout (`mono_path: translations/.../...mono.pdf`, `cached: false`).
Re-running with identical `(source_hash, target_lang, model)` short-circuits
to the cached PDFs without invoking BabelDOC.

The workspace gains a tenth top-level directory:

```
{workspace}/translations/
├── manifest.json              # version + entries[] keyed on (hash, lang, model)
├── {slug}.mono.pdf            # translated-only PDF
└── {slug}.dual.pdf            # alternating-page bilingual PDF
```

BabelDOC (AGPL-3.0) and PyMuPDF (AGPL-3.0) are bundled directly — see
[NOTICE](NOTICE) for the full attribution. This is aligned with XReadAgent's
own AGPL-3.0 license (decision D1 in the Phase 0+1 plan).

## Frontend

A React + Vite + Tailwind v4 + shadcn-style UI lives under
[`frontend/`](frontend/). It runs in browser tab during Phase 1–2 (dev mode)
and gets wrapped in Electron in Phase 3. See
[`frontend/README.md`](frontend/README.md) for the two-terminal dev
quickstart.

## Architecture

See [`.trellis/tasks/05-22-build-sciresearch-agent-literature-reading-knowledge-base/plan.md`](.trellis/tasks/05-22-build-sciresearch-agent-literature-reading-knowledge-base/plan.md)
for the full architecture, decision log (D1–D10), and phased roadmap.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
