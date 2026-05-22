# Research: Agent framework selection for XReadAgent (LLM-Wiki + scientific paper agent)

- **Query**: Compare LangChain / LangGraph / LlamaIndex / CrewAI / AutoGen / PydanticAI / DSPy / custom-thin-layer for an LLM-Wiki maintainer (Karpathy pattern) that ingests papers via markitdown, performs multi-hop Q&A, summarization, lint.
- **Scope**: external (frameworks + ecosystem), with quick survey of public Karpathy-style implementations.
- **Date**: 2026-05-22

---

## Summary (TL;DR)

1. **The dominant 2026 pattern for "agent maintains a folder of markdown" is an *agent harness*, not a chain or workflow.** LangChain's `deepagents` (23k stars, May 2026) explicitly clones the Claude Code design — planning tool + virtual filesystem + subagents + skills — and is the most aligned commercial OSS framework for what XReadAgent needs. It sits on top of `langchain.create_agent` (LangChain 1.x) which in turn sits on LangGraph 1.x. The three layers compose cleanly.
2. **The "wiki implementation" space has already converged on Claude Code Skills**, not on LangChain. Every popular Karpathy-style implementation in 2026 (SamurAIGPT/llm-wiki-agent 2.7k★, AgriciDaniel/claude-obsidian 5.3k★, lucasastorian/llmwiki 951★, moonlarry/awesome-llm-paper-wiki — the closest analog to XReadAgent) is shipped as a *Claude Code / Codex / Gemini CLI skill* with a CLAUDE.md/AGENTS.md contract. Only `lucasastorian/llmwiki` builds its own server (FastAPI + MCP), and even that exposes the wiki to Claude rather than driving the LLM itself. This is a critical product-design signal: the field has decided that the agent harness is a commodity and the value is in the wiki schema/contract.
3. **Recommendation for XReadAgent**: build the core wiki engine + tools (`Ingest` / `Query` / `Lint`) as **plain Python modules with a provider-agnostic LLM gateway**, and choose the orchestration layer per use case:
   - **Primary**: `deepagents` (LangChain) for the interactive Ingest/Query loop — gives us filesystem semantics, planning, subagents, streaming, LangSmith tracing, multi-provider support out of the box.
   - **Fallback / extension**: expose the same tools over **MCP** so users can also drive the wiki from Claude Code / Codex / Cursor (this matches where the OSS community already is and is essentially free with FastMCP / `deepagents` MCP integration).
   - **Type layer**: use **Pydantic 2 + Pydantic AI types** for tool schemas and structured output validation (everyone, including LangChain, depends on Pydantic anyway). Optionally use Pydantic AI standalone for narrow internal pipelines (translation worker, metadata extractor) where type safety > orchestration features.

Avoid CrewAI (role play tax), AutoGen (maintenance mode — superseded by Microsoft Agent Framework), DSPy (wrong abstraction — for prompt optimization, not file-editing loops), and Microsoft Agent Framework (.NET-first, Azure-leaning, no real fit for personal-research / local-first).

---

## Per-framework comparison table

| Framework | Latest stable (2026-05-22) | Stars | License | Provider-agnostic | File-editing fit | Type safety | Observability | Lock-in | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| LangChain (core) | `langchain==1.3.1`, `langchain-core==1.4.0` (2026-05) | 137k | MIT | Yes (100+) | Medium (via `create_agent` + tools) | Pydantic-based | LangSmith (free tier) | Medium | Foundation layer — keep |
| **LangGraph** | `1.2.1` (2026-05-21) | n/a sep repo | MIT | Yes (inherited) | Medium (custom graphs) | Pydantic | LangSmith | Medium | Use only if `deepagents` graph is wrong shape |
| **deepagents** | latest (`uv add deepagents`, May 2026) | **23.2k** | MIT | Yes | **High** — built-in FS, subagents, planning | Pydantic | LangSmith | Medium | **PRIMARY** |
| LlamaIndex | `v0.14.22` (2026-05-14) | 36k+ | MIT | Yes | Medium (Workflows + AgentWorkflow) | Pydantic | Custom + Arize/LangFuse | Low | RAG-leaning, doesn't fit wiki-mutation pattern |
| CrewAI | `1.14.5` (2026-05-18) | 30k+ | MIT | Yes | Low (role/task model, not file-editing) | Pydantic | Native + AgentOps | Medium | Wrong abstraction for solo file-edit loop |
| Microsoft AutoGen | `python-v0.7.5` (2025-09-30) — **maintenance mode** | 40k+ | MIT | Yes | Low | Pydantic | OTel | High (move-on cost) | **Avoid** — superseded |
| Microsoft Agent Framework (MAF) | `1.0` (2025/2026 GA) | growing | MIT | Yes (focus Foundry/Azure) | Medium | C#-first, Python second | OTel | High (Azure-leaning) | Skip — wrong audience |
| **Pydantic AI** | `v1.101.0` (2026-05-22), v2.0.0b2 same day | 9k+ | MIT | Yes (every major provider) | Medium (tools + durable exec) | **Best in class** | Pydantic Logfire / OTel | Low | **Secondary / type layer** |
| DSPy | `3.2.1` (2026-05-05) | 22k+ | MIT | Yes | Low (prompt-as-code, not loop control) | Type-loose | MLflow/Logfire | Low | Out of scope for our loop |
| Custom thin layer | — | — | — | Yes | Highest control | Whatever you write | Roll your own | None | **Use under deepagents for hot paths** |

Notes:
- LangChain v1.0 stable shipped in **late April / early May 2026** (release tag `langchain==1.0.0` precedes the `1.2.18 → 1.3.0` line we see in releases). `langchain-core` followed with 1.4.0 on 2026-05-11. This is the *first* major LangChain release that promises API stability — historically the biggest objection to LangChain.
- LangGraph hit 1.0 in late 2025 (graph checkpointing, durable execution stable) and is now at 1.2.1.
- AutoGen's README explicitly says: *"AutoGen is now in maintenance mode. It will not receive new features... New users should start with Microsoft Agent Framework."*
- Pydantic AI 1.0 GA happened earlier in 2026; **2.0 beta started 2026-05-21**. Watch the 1.x → 2.x story.

---

## Per-framework deep dive

### 1. LangChain 1.x + `create_agent`

**How it fits our case.** LangChain 1.x retired the old `AgentExecutor` / chains-everywhere model in favor of a single `create_agent(model, tools, system_prompt)` factory. It's a *thin* harness — you bring your own tools (file I/O, markitdown, embedding, vector store) and pick any of 100+ models. The agent loop, streaming, retries, and tool-call serialization are provided. It's the minimum we need to build the LLM-Wiki ingest/query loop.

**Pros.**
- Provider-agnostic: `openai:gpt-5.4` / `anthropic:claude-sonnet-4-6` / `google_genai:...` / `openrouter:...` / `ollama:...` all work with one string.
- Built on LangGraph runtime, so durable execution + streaming + checkpoint come along.
- Pydantic-typed tools and structured outputs.
- LangSmith tracing is one env var (`LANGSMITH_TRACING=true`).
- Largest ecosystem of integrations (loaders, vector stores, retrievers) — but we mostly don't need RAG.

**Cons.**
- The historical "churn tax" — 0.x → 0.3 → 1.0 was painful. 1.x just stabilized; we'd be early but not bleeding-edge.
- Still leaks `langchain-core` types into user code (Message, BaseTool) → some surface area to learn.
- For "agent that edits files in a folder", the built-in tools are minimal; you'd reach for `deepagents` anyway.

**Code sketch.**
```python
from langchain.agents import create_agent
from langchain_core.tools import tool

@tool
def read_wiki_page(path: str) -> str:
    """Read a wiki page from disk."""
    return (WIKI / path).read_text(encoding="utf-8")

@tool
def write_wiki_page(path: str, content: str) -> str:
    """Write/overwrite a wiki page."""
    (WIKI / path).write_text(content, encoding="utf-8")
    return f"wrote {path}"

agent = create_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[read_wiki_page, write_wiki_page, list_wiki, search_wiki, ingest_source],
    system_prompt=open(".trellis/spec/wiki-schema.md").read(),
)
result = agent.invoke({"messages": [{"role": "user", "content": "Ingest raw/papers/attention.md"}]})
```

### 2. LangGraph

**How it fits.** Lower-level than `create_agent`. You define a `StateGraph` with nodes (LLM call, tool call, route) and edges. Useful when the agent loop *isn't* the right shape — e.g., a deterministic ingest pipeline ("convert PDF → extract metadata → propose wiki diffs → human review → apply diffs") where we want explicit stages with checkpoints.

**Pros.** Durable execution (PostgreSQL/SQLite checkpointing), time-travel debugging, human-in-the-loop natively, parallel branches.

**Cons.** Boilerplate for what is essentially a tool-calling loop. We'd lose the file-system + planning middleware that `deepagents` already provides.

**Use case in XReadAgent.** The batch ingest pipeline (when the user drops 50 PDFs at once and we want resumability) can be a LangGraph subgraph beneath a Deep Agents top loop.

**Code sketch.**
```python
from langgraph.graph import StateGraph, START, END

g = StateGraph(IngestState)
g.add_node("convert_pdf", convert_with_markitdown)
g.add_node("propose_diff", llm_propose_wiki_diff)
g.add_node("apply_diff", write_wiki_pages)
g.add_edge(START, "convert_pdf"); g.add_edge("convert_pdf", "propose_diff")
g.add_edge("propose_diff", "apply_diff"); g.add_edge("apply_diff", END)
ingest_graph = g.compile(checkpointer=SqliteSaver(...))
```

### 3. `deepagents` (LangChain) — PRIMARY RECOMMENDATION

**How it fits.** `deepagents` is *explicitly* designed for the workload XReadAgent is doing. From the README: *"Inspired by Claude Code: an attempt to identify what makes it general-purpose, and push that further."* Built-in features that map 1:1 to LLM-Wiki ops:

| Need | deepagents primitive |
|---|---|
| Ingest a paper that touches 10-15 wiki pages | `write_file` / `edit_file` / `read_file` over pluggable filesystem backend |
| Plan multi-step work | built-in `write_todos` planning tool |
| Multi-hop Q&A spanning many wiki pages | sub-agent spawn with isolated context, summarize back |
| Long-context manageability | offload large search/tool outputs to disk; main loop reads via fs tools |
| Lint pass that reads everything and edits some | same fs tools, optionally run as a scheduled sub-agent |
| Cross-session memory | pluggable state + store backends; LangGraph checkpoints |
| Streaming UI | LangGraph streaming; works with React/Vue frontends via Agent Client Protocol (ACP) |

It is **model-agnostic** (any tool-calling chat model), **MIT licensed**, and **production-grade** (used by OpenSWE and LangSmith Fleet per official docs).

**Pros.**
- *Exactly* the agent-as-file-editor shape we need; no need to invent the planning/fs middleware.
- Pluggable filesystem backends — local (default), virtual (for tests), sandboxed, or remote — including S3 / Postgres / Azure Blob via the community `deepagents-backends` package.
- Composable: any LangGraph subgraph can be wired in as a sub-agent.
- Public precedent for our use case: **`AgentTeam-TaichuAI/ScienceClaw`** (505 ★) — a personal research assistant explicitly built with LangChain DeepAgents + sandboxed tools; runs offline in Docker; closest analog to XReadAgent.
- `langgraph build` produces a self-contained Docker image; "managed" deployment via LangSmith optional.
- Deep Agents Code (the bundled coding agent CLI) is a strong reference impl of "agent maintains a folder."

**Cons.**
- Implicitly pulls in the LangChain stack (langchain-core, langgraph, langsmith client). Not minimal.
- Defaults are "Claude Code-ish" — opinionated about tools (`write_todos`, etc.) — which we want, but worth knowing.
- LangSmith is a paid SaaS at higher tiers; free tier exists, OTel export is available, and Logfire/Arize/Phoenix work as alternatives.

**Code sketch.**
```python
from deepagents import create_deep_agent
from xreadagent.tools import ingest_source, query_wiki, lint_wiki, run_markitdown
from xreadagent.backends import WikiFilesystemBackend

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",   # or "openai:gpt-5.4", "ollama:qwen3:32b"
    tools=[ingest_source, query_wiki, lint_wiki, run_markitdown],
    system_prompt=open(".trellis/spec/wiki-schema.md").read(),
    backend=WikiFilesystemBackend(root="~/research-vault"),
    subagents=[
        {"name": "translator", "system_prompt": "...", "tools": [translate_layout]},
        {"name": "metadata_extractor", "system_prompt": "...", "tools": [extract_meta]},
    ],
)

# Streaming UI
for event in agent.astream({"messages": [{"role": "user", "content": "Ingest raw/papers/attention.md"}]}):
    yield_to_ui(event)
```

### 4. LlamaIndex

**How it fits.** LlamaIndex is RAG-first. Their `AgentWorkflow` and Property Graph features (knowledge-graph extraction) are nice for the "build a graph of papers" extension, but the *primary* loop in XReadAgent is *write markdown files*, not *query a vector store*. We'd end up using LlamaIndex's loaders/parsers (which are excellent) and ignoring its agent layer.

**Pros.**
- Best-in-class document loaders, chunkers, parsers; first-class PDF support via LlamaParse (paid) or open-source equivalents.
- Property graph store useful if we ever go beyond markdown to a graph DB.

**Cons.**
- Agent abstractions feel bolted on; the loop control isn't as clean as `deepagents` or LangGraph.
- More opinionated toward retrieval-augmented patterns — exactly the pattern Karpathy says LLM-Wiki *replaces*.

**Verdict.** Don't use as the orchestration layer. Optionally borrow loaders. We've already chosen `markitdown` for PDF→MD, so even the loader value is muted.

**Code sketch (loader only).**
```python
from llama_index.readers.file import PDFReader  # if markitdown ever falls short
docs = PDFReader().load_data(file=Path("paper.pdf"))
```

### 5. CrewAI

**How it fits.** CrewAI is built around "roles" (Researcher, Writer, Reviewer) collaborating. That's a poor abstraction for our problem: there's *one* agent maintaining *one* wiki. Crews shine in marketing/sales automations where you actually want multiple personas.

**Pros.** Quick onboarding, good for prototypes where the user is genuinely modeling a team. Sequential / hierarchical processes. Pydantic outputs.

**Cons.**
- Role-play overhead and prompt bloat for a solo-agent loop.
- Less mature file-editing primitives than `deepagents`.
- Heavy on "Enterprise" CrewAI features (paid), which we don't need.
- Provider-agnostic, but observability requires AgentOps (vendor SaaS) for the polished story.

**Verdict.** Skip. CrewAI is the right tool when the *team metaphor* genuinely fits the work; ours doesn't.

### 6. Microsoft AutoGen

**How it fits.** Doesn't. As of 2026, AutoGen's README ships a giant maintenance-mode banner: *"New users should start with Microsoft Agent Framework."* Last release `python-v0.7.5` (2025-09-30). Repo is community-maintained going forward.

**Verdict.** **Avoid.** Migration tax to the successor (MAF) within months is guaranteed.

### 7. Microsoft Agent Framework (MAF) — AutoGen successor

**How it fits.** MAF is the "enterprise" production framework: graph-based workflows, OTel, declarative YAML, Foundry-hosted deployment. Strong .NET story, Python is second-class.

**Pros.** Real productionization story, OpenTelemetry, durable workflows. Good if your target is Azure Foundry.

**Cons.** Wrong audience. We're building a local-first personal-research tool, not an Azure enterprise agent fleet. The "agent edits markdown in `~/research`" use case isn't a documented pattern in MAF.

**Verdict.** Skip.

### 8. Pydantic AI

**How it fits.** Pydantic AI's pitch is "FastAPI for agents": type-safe `Agent` class, model-agnostic, Logfire OTel for observability, declarative YAML/JSON agent specs, Pydantic Evals. v1.x is GA, **v2.0 beta started 2026-05-21** (move fast — but the v1.x API has 1.0 stability guarantees per their version policy).

**Pros.**
- *Best-in-class* type safety; tools and outputs validate at write-time.
- Strong observability via Logfire (Pydantic's own OTel platform) — alternative to LangSmith.
- Durable execution with Temporal / DBOS / Prefect / Restate backends — much more options than LangGraph's checkpointers.
- MCP client + server + sampling first-class.
- "Define agents entirely in YAML/JSON" — declarative specs match Trellis spec-first ethos.
- No LangChain dependency tree.

**Cons.**
- Agent abstraction is one level up from `create_agent` (closer to a typed assistant than a Claude Code-style harness). No built-in planning/fs/subagent tools — you build them.
- The "agent edits 15 files in a row, with planning and context offload" pattern is *not* a built-in. You can reach it, but you write the middleware.
- v2.0 beta is in flight — same kind of churn risk that hurt early LangChain.

**Verdict.** **Use as the type layer + as the runtime for *narrow* internal pipelines** (translation worker, metadata extractor, citation parser) where strong typing on tool I/O matters more than file-editing affordances. Don't use it as the main wiki-maintenance loop.

**Code sketch (narrow pipeline).**
```python
from pydantic_ai import Agent
from pydantic import BaseModel

class PaperMeta(BaseModel):
    title: str
    authors: list[str]
    year: int
    venue: str | None
    abstract: str

extractor = Agent(
    "anthropic:claude-sonnet-4-6",
    output_type=PaperMeta,
    instructions="Extract paper metadata from the provided markdown. Be precise; if a field is absent, set to None.",
)

result = extractor.run_sync(markdown_text)
meta: PaperMeta = result.output   # IDE-typed, runtime-validated
```

### 9. DSPy

**How it fits.** DSPy is for *optimizing prompts as code*: you define a signature (typed input → typed output), DSPy compiles/optimizes the underlying prompts via metric-driven search (GEPA, MIPRO, etc.). It's not an agent harness.

**Pros.** If we had a hard accuracy metric (e.g., "extracted entities F1") and a labeled eval set, DSPy could *measurably* improve a single sub-step like "extract entity pages from a paper."

**Cons.** Wrong layer of abstraction for the wiki loop. We don't have labeled eval data on day one. DSPy modules don't naturally orchestrate "edit 15 files."

**Verdict.** Out of scope for v1. Re-evaluate post-MVP if we want to optimize the metadata-extraction sub-step.

### 10. Custom thin layer over OpenAI/Anthropic SDK

**How it fits.** Skip the framework, write `~300 LOC` glue: a provider-agnostic chat function, a tool loop, JSON-mode for structured output, a streaming wrapper. Many production agent products do this.

**Pros.**
- Zero dependency footprint outside the SDKs.
- Full control over loop semantics (retries, cancellation, token-budget guardrails).
- No churn risk from someone else's API changes.
- Easy to read and debug.

**Cons.**
- We re-implement `write_file` / `read_file` / planning middleware / subagent spawn / streaming UI / checkpointing — every wheel `deepagents` already polished.
- No tracing UI for free — we'd build a span recorder + viewer or wire up OTel ourselves.
- Worse hiring story (newcomers know LangChain, not our DSL).

**Verdict.** **Use as a *layer beneath* deepagents** — the LLM-gateway module (provider routing, retry, rate-limit, cancellation) is worth owning ourselves so we can swap models without LangChain knowing. But don't use it as the main loop.

**Code sketch (gateway).**
```python
# xreadagent/llm_gateway.py
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

class LLMGateway:
    """Provider-agnostic chat with built-in retry, streaming, cancellation."""
    async def chat(self, model: str, messages, tools=None, stream=False):
        provider, name = model.split(":", 1)
        if provider == "anthropic":
            ...
        elif provider == "openai":
            ...
```
Then expose this gateway to deepagents via the standard LangChain chat-model interface (or just use `init_chat_model` directly).

---

## Karpathy-style LLM Wiki: public implementations (2025-2026)

Direct evidence of how the community is solving this problem. **Almost none use LangChain/LangGraph** — most are Claude Code Skills.

| Repo | ★ | Stack | Notes |
|---|---|---|---|
| `AgriciDaniel/claude-obsidian` | 5,339 | Claude Code Skill + Obsidian | `/wiki /save /autoresearch` commands; persistent compounding vault |
| `SamurAIGPT/llm-wiki-agent` | 2,712 | Agnostic Skill (Claude/Codex/Gemini CLI) | Plain CLAUDE.md/AGENTS.md/GEMINI.md contract; markitdown for non-md inputs; vis.js graph; **lint** built-in |
| `sdyckjq-lab/llm-wiki-skill` | 1,613 | Skill | Multi-platform |
| `Ar9av/obsidian-wiki` | 1,439 | Framework for AI agents on Obsidian | Open-ended |
| `atomicstrata/llm-wiki-compiler` | 1,256 | "Knowledge compiler", raw→wiki | |
| `lucasastorian/llmwiki` | **951** | **FastAPI + MCP + Python + Next.js** | Karpathy's open-source impl; MCP server exposes wiki to Claude; SQLite index; **no LangChain** |
| `Astro-Han/karpathy-llm-wiki` | 893 | Skill | Claude Code / Cursor / Codex |
| `skyllwt/OmegaWiki` | 759 | Claude Code wiki-centric research platform | |
| `kytmanov/obsidian-llm-wiki-local` | 639 | Local-only with Ollama + Obsidian | 100% local — closest "privacy" play |
| `moonlarry/awesome-llm-paper-wiki` | 52 (new but **closest analog**) | Skill (paper-wiki for Claude/Codex) | **LLM Agent-driven local markdown literature library with 25 workflows: ingest, scan-organize, tag, journal-report, direction-report, idea-discover, submission-recommend, paper-review-loop, direction-review… **This is essentially the feature set of XReadAgent.** Implemented as a Skill, not a framework. |

**The deer-flow (ByteDance) reference (69k ★)** is the only large-scale LangChain/LangGraph-based research agent harness — but it's a *super-agent harness* (research + code + create), not a wiki-maintainer per se. Worth borrowing patterns from (config.yaml model registry, sandbox modes, CLI provider wrapping for Claude Code/Codex OAuth).

**Key takeaway.** The Karpathy LLM-Wiki community has consolidated around a *Claude-Code-as-runtime* design. They publish the *wiki contract* (schema + slash commands) and let the user bring their agent. XReadAgent has a richer product surface (PDF translation, polished UI, multi-user later) so we *do* need our own agent runtime — but we can adopt the same wiki contract format so users can also drive our wiki from external agents over MCP.

---

## Risk analysis

### Lock-in

| Framework | LLM lock-in | Infra lock-in | Code lock-in |
|---|---|---|---|
| deepagents | None (any tool-calling model) | None (any host) | Medium — `langchain` imports across codebase |
| LangChain core | None | None | Medium |
| Pydantic AI | None | None | Low — clean type-first surface |
| CrewAI | None | Low (Enterprise CrewAI optional) | Medium |
| MAF | None nominally; Azure-leaning in practice | Medium (Foundry hosting promoted) | High (C#-first) |
| Custom | None | None | None |
| LangSmith (obs) | n/a | SaaS, but OTel export available | Low if you only use traces |

Mitigation: keep all model calls behind one `LLMGateway` module, all wiki I/O behind one `WikiBackend` interface, all tools as plain functions registered to both `deepagents` and an MCP server. This way the *core* is portable and the *harness* is replaceable.

### Churn

- **LangChain**: just hit 1.x stable (April-May 2026). The "API churn" objection is materially weaker than in 2023-2024. Still on a brisk cadence (1.2 → 1.3 in 3 weeks).
- **LangGraph**: 1.x; weekly point releases of subpackages.
- **deepagents**: actively evolving (still pre-1.0 SDK semantics per docs, though production-used).
- **Pydantic AI**: 1.x stable + 2.x beta running concurrent — same risk pattern as LangChain.
- **AutoGen**: maintenance mode, *guaranteed* churn (migration to MAF).
- **MAF**: 1.0 — but tied to MS's product direction.
- **DSPy / CrewAI / LlamaIndex**: still moving fast.

Mitigation: pin versions in `pyproject.toml`, update on a quarterly cadence, run a regression eval before each bump.

### Observability

| Option | Cost | OSS / self-host | Fits us? |
|---|---|---|---|
| **LangSmith** | Free tier (5k traces/mo), paid above | SaaS only (LangSmith Self-Hosted exists, enterprise) | Yes if we deepagent |
| **Pydantic Logfire** | Free tier, paid above | SaaS; OTel export | Yes for narrow PydanticAI pipelines |
| **Arize Phoenix** | Free + paid | OSS self-host | Yes — provider-neutral |
| **OpenTelemetry + Grafana/Tempo/Loki** | Free | OSS self-host | Yes — full DIY |
| **MLflow Tracing** | Free | OSS self-host | Yes — pairs with DSPy and is provider-neutral |

Recommendation: ship with **LangSmith free-tier as the default** (it's one env var with `deepagents`), and **OTel export** configured so users can point it at Phoenix / Logfire / Grafana / Langfuse self-host. Don't make it a hard dep.

---

## Final ranking

For XReadAgent specifically:

1. **`deepagents` (LangChain) — PRIMARY**
   *Rationale*: The only OSS framework that explicitly bundles "agent edits files in a folder" with planning + subagents + streaming + multi-provider + production references. Public analog exists (ScienceClaw). Lock-in is manageable behind our own `LLMGateway` and `WikiBackend` interfaces. Built-in LangSmith observability is a real win for debugging the multi-step ingest loop.

2. **LangGraph (when needed) — SECONDARY for batch pipelines**
   *Rationale*: Drop down to a raw `StateGraph` only for deterministic batch flows (e.g., "ingest 50 PDFs over the weekend with resumable checkpoints"). Otherwise let `deepagents` handle the loop.

3. **Pydantic AI — TYPING + NARROW PIPELINES**
   *Rationale*: Use the `Agent(..., output_type=PydanticModel)` pattern for any sub-step that produces structured data (metadata extraction, citation parsing, frontmatter generation). Best-in-class type safety. Use `pydantic_evals` for offline regression evals once we have labeled cases.

4. **Custom thin layer — LLM GATEWAY ONLY**
   *Rationale*: Owning a 200-LOC `LLMGateway` (provider routing, retry, streaming, cancellation, cost accounting) protects us from any single framework's API drift. Wrap it as a LangChain `BaseChatModel` for use inside `deepagents`.

5. **MCP server adapter — DISTRIBUTION**
   *Rationale*: Expose `ingest_source` / `query_wiki` / `lint_wiki` as an MCP server (via FastMCP or `deepagents`' built-in MCP support). Users on Claude Code / Codex / Cursor get the same wiki engine for free. This matches where the OSS community is.

**Skip / avoid**: AutoGen (maintenance), MAF (wrong audience), CrewAI (wrong shape), DSPy (wrong layer), LlamaIndex (RAG-leaning, doesn't fit wiki mutation).

---

## Recommended architecture (one paragraph)

> XReadAgent's Python backend has three layers. **(a) Core engine**: plain Python modules — `WikiBackend` (filesystem ops on `wiki/`), `IngestPipeline` (markitdown → metadata extraction → wiki diff proposal → apply), `Query`, `Lint`, plus an `LLMGateway` that abstracts OpenAI / Anthropic / Gemini / Ollama. All typed with Pydantic models. **(b) Agent harness**: `deepagents.create_deep_agent` wraps the engine's tools (`ingest_source`, `read_wiki`, `write_wiki`, `query_wiki`, `lint_wiki`, `translate_layout`), uses LangGraph durable execution for resumability, streams events to the frontend, and is observed via LangSmith (with OTel fallback). **(c) Distribution surface**: same tools exposed as an MCP server so the wiki can also be driven from Claude Code / Codex / Cursor by power users — matching where the LLM-Wiki community has converged. The Karpathy contract (`raw/` / `wiki/` / `schema/` + `index.md` + `log.md`) is the canonical on-disk format and is platform-agnostic.

---

## Open questions for the user

1. **Cloud observability tolerance.** Are you OK with LangSmith's SaaS for traces (free tier ~5k traces/month), or do you require fully local observability from day one (then we wire Phoenix/Langfuse self-host)?
2. **Provider priority.** Which is the *primary* model? If it's Claude (Anthropic), then the "expose as MCP to Claude Code" path doubles in value. If it's mostly local (Ollama qwen3 / DeepSeek-V3 self-hosted), some `deepagents` planning prompts may need tuning.
3. **MCP-first vs UI-first.** Should v1 ship a web/desktop UI driving our own `deepagents` runtime *or* ship the MCP server and let users drive it from Claude Code first (matches OSS community, faster MVP)? The full product wants both eventually — sequencing matters.
4. **Multi-agent sub-roles.** Do you want translator / metadata-extractor / lint as *named subagents* (visible in the UI as roles) or as opaque internal tools? Affects whether we use `deepagents`' subagent feature.
5. **License posture.** XReadAgent's own license? Most of the stack is MIT, so any choice works. (Worth noting for downstream packaging.)
6. **Wiki schema source.** Will the wiki schema (`.trellis/spec/wiki-schema.md` analog) be hand-written by you for the MVP, or do we generate a starter from the Karpathy gist + research-paper specialization?

---

## Sources

### Framework docs / blogs
- LangChain Python overview — https://docs.langchain.com/oss/python/langchain/overview (fetched 2026-05-22)
- LangChain `create_agent` quickstart — https://docs.langchain.com/oss/python/langchain/agents
- Deep Agents overview — https://docs.langchain.com/oss/python/deepagents/overview
- Deep Agents Quickstart — https://docs.langchain.com/oss/python/deepagents/quickstart
- Deep Agents vs Claude Agent SDK — https://docs.langchain.com/oss/python/deepagents/comparison (key comparison doc)
- Deep Agents GitHub README — https://github.com/langchain-ai/deepagents (raw README fetched 2026-05-22; 23.2k stars)
- LangGraph repo — https://github.com/langchain-ai/langgraph (1.2.1, 2026-05-21)
- Microsoft AutoGen README — https://github.com/microsoft/autogen (maintenance-mode banner)
- Microsoft Agent Framework README — https://github.com/microsoft/agent-framework (1.0 GA)
- AutoGen → MAF migration — https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/
- Pydantic AI docs — https://ai.pydantic.dev/
- Pydantic AI README — https://github.com/pydantic/pydantic-ai (v1.101.0 / v2.0.0b2, 2026-05-22)
- CrewAI docs — https://docs.crewai.com/ (v1.14.5)
- DSPy docs — https://dspy.ai/ (v3.2.1, 2026-05-05)
- LlamaIndex repo — https://github.com/run-llama/llama_index (v0.14.22, 2026-05-14)

### Karpathy LLM-Wiki references
- Karpathy gist — https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- SamurAIGPT/llm-wiki-agent — https://github.com/SamurAIGPT/llm-wiki-agent
- AgriciDaniel/claude-obsidian — https://github.com/AgriciDaniel/claude-obsidian
- lucasastorian/llmwiki (FastAPI+MCP, OSS impl) — https://github.com/lucasastorian/llmwiki
- moonlarry/awesome-llm-paper-wiki (closest analog) — https://github.com/moonlarry/awesome-llm-paper-wiki
- kytmanov/obsidian-llm-wiki-local (Ollama, fully local) — https://github.com/kytmanov/obsidian-llm-wiki-local
- skyllwt/OmegaWiki — https://github.com/skyllwt/OmegaWiki

### Research-agent precedents on LangChain DeepAgents
- AgentTeam-TaichuAI/ScienceClaw — https://github.com/AgentTeam-TaichuAI/ScienceClaw (LangChain DeepAgents + sandbox, personal research assistant)
- ByteDance deer-flow — https://github.com/bytedance/deer-flow (69k ★, LangChain/LangGraph super-agent harness)
- guy-hartstein/company-research-agent — https://github.com/guy-hartstein/company-research-agent (LangGraph + Tavily research example)
- tarun7r/deep-research-agent — https://github.com/tarun7r/deep-research-agent (multi-agent LangGraph)

### Observability
- LangSmith — https://docs.langchain.com/langsmith/home
- Pydantic Logfire — https://pydantic.dev/logfire
- Arize Phoenix (OSS) — https://github.com/Arize-ai/phoenix
- Langfuse (OSS self-host) — https://github.com/langfuse/langfuse

---

## Caveats / Not Found

- **No public Python wiki-maintainer built on `deepagents` exists yet** that exactly maps to "scientific paper ingest + Karpathy contract + UI" — ScienceClaw is the closest but uses DeepAgents for general research, not for a literature-vault contract. XReadAgent would be novel in this combination, but well-precedented in each piece.
- **LangChain 1.0 exact release date** for `langchain==1.0.0` couldn't be retrieved from GH releases due to API rate-limit; we observed `langchain==1.2.18` → `1.3.0` (2026-05-12) → `1.3.1` (2026-05-15), and `langchain-core==1.4.0` (2026-05-11), so 1.0 must have shipped some weeks earlier (likely March-April 2026). Verify on the official changelog at https://docs.langchain.com/oss/python/changelog before announcing.
- **MAF (Microsoft Agent Framework) exact Python stability** isn't deeply assessed here — Python is documented as supported but .NET seems to lead. If MS ecosystem matters later, re-evaluate.
- **`deepagents` v1.0 timing** — public README shows it as actively maintained, production-used, MIT — but doesn't show a 1.0 SDK marker. Worth double-checking on PyPI release history before pinning.
- **Pydantic AI v2.0 breaking changes** — v2.0 beta is days old (b1: 2026-05-21, b2: 2026-05-22). If we use Pydantic AI, pin to a 1.x line and watch the 2.x migration guide before bumping.
- **No empirical benchmark** here comparing tokens / latency / cost between frameworks for the wiki-edit workload. Worth running a small bake-off post-MVP if cost matters.
