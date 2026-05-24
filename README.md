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
