# Research: MCP (Model Context Protocol) for XReadAgent

- **Query**: What is MCP, how does it work, how to build an MCP server in Python, what should XReadAgent expose, how does it integrate with the existing FastAPI sidecar, what security considerations apply?
- **Scope**: mixed (internal codebase analysis + external MCP SDK/API inspection)
- **Date**: 2026-05-29

---

## 1. MCP Protocol Overview

### What is MCP?

MCP (Model Context Protocol) is an open protocol by Anthropic that standardizes how AI models connect to external tools and data sources. It follows a client-server model where:

- **MCP Client** -- the AI application (Claude Desktop, Cursor, Windsurf, etc.)
- **MCP Server** -- a program that exposes **tools**, **resources**, and **prompts** to clients
- **Transport** -- how client and server communicate (stdio, SSE over HTTP, or Streamable HTTP)

The current protocol version is **2025-11-25**. The Python SDK version installed for inspection is **1.27.1**.

### Three Primitives

| Primitive | Purpose | Analogy |
|-----------|---------|---------|
| **Tools** | Functions the model can *call* to take actions or compute results | RPC / function calls |
| **Resources** | Data the model can *read* (files, records, live data) | GET endpoints / file handles |
| **Prompts** | Reusable prompt templates the model can *instantiate* | Prompt library / templates |

### Protocol Lifecycle

1. **Initialize**: Client sends `initialize` with its capabilities; server responds with its capabilities.
2. **Initialized**: Client sends `initialized` notification. Connection is live.
3. **Interaction**: Client calls tools, reads resources, gets prompts. Server responds.
4. **Shutdown**: Either side closes the connection.

### Transport Options

| Transport | Use Case | How it works |
|-----------|----------|-------------|
| **stdio** | Local CLI tools, Claude Desktop integration | Server reads JSON-RPC from stdin, writes to stdout. Client spawns the server process. |
| **SSE (Server-Sent Events)** | Remote/HTTP access, web apps | Client POSTs to `/messages/`, server streams responses via SSE on `/sse`. |
| **Streamable HTTP** | Modern HTTP transport (replaces SSE for new deployments) | Single `/mcp` endpoint; client POSTs JSON-RPC, server responds with JSON or SSE stream. Supports resumability via event IDs. |

### Server Capabilities

A server advertises what it supports via `ServerCapabilities`:

```
tools          -- can the server provide tools?
resources      -- can the server provide resources?
prompts        -- can the server provide prompt templates?
logging        -- can the server emit log messages?
completions    -- can the server provide argument completions?
tasks          -- can the server manage long-running tasks? (newer feature)
```

---

## 2. Python SDK (mcp 1.27.1)

### Package: `mcp`

**Installation**: `pip install mcp` (pulls in httpx, pydantic>=2.11, starlette, uvicorn, sse-starlette, jsonschema, pydantic-settings, pyjwt)

**Compatibility with XReadAgent**: The SDK's dependencies overlap with XReadAgent's existing stack:
- `pydantic>=2.11` -- XReadAgent uses `pydantic>=2.8` (compatible)
- `httpx>=0.27.1` -- XReadAgent uses `httpx>=0.27` (compatible)
- `uvicorn>=0.31.1` -- XReadAgent uses `uvicorn>=0.32` (compatible)
- `starlette>=0.27` -- comes with FastAPI (compatible)
- `python-multipart>=0.0.9` -- XReadAgent uses `>=0.0.12` (compatible)

No dependency conflicts detected.

### FastMCP Server Class

`FastMCP` is the high-level server API in `mcp.server.fastmcp.server`:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="xreadagent-mcp",
    instructions="XReadAgent scientific research agent",
    host="127.0.0.1",
    port=8000,
)
```

Constructor parameters of note:
- `name` -- server name shown to clients
- `instructions` -- description shown to the AI model (appears in system prompt)
- `host` / `port` -- for HTTP transports (default: `127.0.0.1:8000`)
- `lifespan` -- async context manager for startup/shutdown (same pattern as FastAPI)
- `auth` / `auth_server_provider` / `token_verifier` -- OAuth 2.1 support
- `transport_security` -- `TransportSecuritySettings` for DNS rebinding protection
- `sse_path` -- path for SSE endpoint (default: `/sse`)
- `streamable_http_path` -- path for Streamable HTTP endpoint (default: `/mcp`)
- `json_response` -- if True, use JSON responses instead of SSE (simpler, no streaming)
- `stateless_http` -- if True, no session management (each request is independent)

### Tool Registration

```python
@mcp.tool()
def hello(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_papers() -> list[dict]:
    """List all papers in the workspace."""
    return [...]

@mcp.tool(structured_output=True)
def get_paper(slug: str) -> PaperResult:  # Must return a Pydantic model
    """Get paper details by slug."""
    return PaperResult(slug=slug, title="...")
```

Key points:
- **Async functions are supported** (`async def` works)
- **Context parameter**: add `ctx: Context` to get access to `ctx.info()`, `ctx.report_progress()`, `ctx.read_resource()`, `ctx.elicit()`
- **ToolAnnotations** control model behavior: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`
- **structured_output=True** requires a Pydantic model return type (not raw `dict`)

### Resource Registration

```python
@mcp.resource("wiki://papers")
def list_papers() -> str:
    """List all papers in the workspace."""
    return "..."

@mcp.resource("wiki://papers/{slug}")
def read_paper(slug: str) -> str:
    """Read a specific paper page."""
    return "..."
```

Resources are URI-addressed data. They are **read-only** by definition. URI templates (`{slug}`) allow parameterized resources.

### Prompt Registration

```python
@mcp.prompt()
def summarize_paper(title: str) -> str:
    """Generate a prompt to summarize a paper."""
    return f"Please summarize the paper titled: {title}"
```

Prompts return a string that the AI model will use as part of its context.

### Running the Server

Three transport modes:

```python
# 1. stdio -- for Claude Desktop / local CLI integration
await mcp.run_stdio_async()

# 2. SSE -- HTTP + Server-Sent Events
await mcp.run_sse_async()

# 3. Streamable HTTP -- modern HTTP transport
await mcp.run_streamable_http_async()
```

For stdio, the typical Claude Desktop configuration looks like:

```json
{
  "mcpServers": {
    "xreadagent": {
      "command": "python",
      "args": ["-m", "xreadagent.mcp"],
      "env": {
        "XREAD_AGENT_WORKSPACE": "/path/to/workspace"
      }
    }
  }
}
```

### ASGI App Integration (Critical Finding)

`FastMCP.sse_app()` returns a **Starlette** app. `FastMCP.streamable_http_app()` also returns a **Starlette** app. Both can be **mounted into an existing FastAPI app**:

```python
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

api = FastAPI(title="XReadAgent sidecar")
mcp = FastMCP("xreadagent-mcp")

# Mount MCP SSE transport under /mcp
api.mount("/mcp", mcp.sse_app())

# Or mount the Streamable HTTP transport
api.mount("/mcp", mcp.streamable_http_app())
```

**Verified**: This works with FastAPI. The MCP server shares the same ASGI process as the existing sidecar.

### Context Object Methods

When a tool accepts `ctx: Context`, it gains access to:

| Method | Purpose |
|--------|---------|
| `ctx.info(message)` | Send info log to client |
| `ctx.warning(message)` | Send warning log to client |
| `ctx.error(message)` | Send error log to client |
| `ctx.debug(message)` | Send debug log to client |
| `ctx.report_progress(current, total)` | Report progress for long operations |
| `ctx.read_resource(uri)` | Read an MCP resource from within a tool |
| `ctx.elicit(message, schema)` | Ask the human user for input/confirmation (new feature) |
| `ctx.elicit_url(message, url)` | Redirect user to a URL for action |
| `ctx.close_sse_stream()` | Close SSE stream |
| `ctx.session` | Access the underlying MCP session |
| `ctx.request_id` | Current request ID |
| `ctx.fastmcp` | Access the parent FastMCP server |

The **elicit** feature is particularly relevant for XReadAgent: before ingesting a large paper or performing a destructive operation, the tool can ask the user to confirm via the MCP client's UI.

### TransportSecuritySettings

```python
TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1"],
    allowed_origins=["http://localhost:*"],
)
```

Prevents DNS rebinding attacks on HTTP transports. Defaults are safe for local-only use.

### AuthSettings (OAuth 2.1)

```python
AuthSettings(
    issuer_url=...,
    resource_server_url=...,
    required_scopes=["xreadagent:read", "xreadagent:write"],
)
```

For Phase 4 local-first use, OAuth is likely overkill. The Electron app binds to `127.0.0.1` only. But if the MCP server is exposed over a network, OAuth 2.1 is available in the SDK.

---

## 3. MCP Server Patterns for XReadAgent

### Architecture Decision: Tools vs Resources vs Prompts

| XReadAgent Capability | MCP Primitive | Rationale |
|-----------------------|---------------|-----------|
| **Ingest a paper** (convert + LLM analysis + write wiki) | **Tool** | Side-effect: creates files, calls LLM, takes time |
| **Query the wiki** (ask a question, get an answer) | **Tool** | Side-effect: writes query archive page, calls LLM |
| **Translate a PDF** | **Tool** | Side-effect: spawns BabelDOC subprocess, writes translations/ |
| **List papers** | **Tool** (or **Resource**) | Read-only; could be either. Tool is simpler for structured JSON output. |
| **Read paper page** | **Resource** (`wiki://papers/{slug}`) | Read-only data, URI-addressable |
| **Read concept page** | **Resource** (`wiki://concepts/{slug}`) | Read-only data, URI-addressable |
| **Read query page** | **Resource** (`wiki://queries/{topic}/{slug}`) | Read-only data, URI-addressable |
| **Read wiki index** | **Resource** (`wiki://index`) | Read-only data |
| **Read wiki overview** | **Resource** (`wiki://overview`) | Read-only data |
| **Summarize paper** | **Prompt** | Template for generating a summarization prompt |
| **Compare papers** | **Prompt** | Template for comparative analysis |
| **Get paper summary** | **Tool** | Calls LLM for on-demand summary generation |

### Proposed MCP Tool Definitions

```python
mcp = FastMCP("xreadagent", instructions="XReadAgent: scientific research agent with LLM-Wiki memory")

# --- Tools (actions the model can take) ---

@mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True))
async def ingest_paper(
    file_path: str,
    workspace_path: str,
    title: str | None = None,
    model: str | None = None,
    ctx: Context = None,
) -> dict:
    """Ingest a scientific paper into the workspace wiki.

    Converts the document to markdown, runs the LLM ingest agent,
    and creates paper + concept wiki pages. Returns the paper slug
    and list of files created.

    Idempotent: re-ingesting an unchanged file is a no-op (cache hit).
    """
    ...

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def query_wiki(
    question: str,
    workspace_path: str,
    topic: str | None = None,
    model: str | None = None,
) -> dict:
    """Ask a question against the workspace knowledge base.

    Returns the answer, confidence level, and sources cited.
    The answer is also archived under wiki/queries/.
    """
    ...

@mcp.tool(annotations=ToolAnnotations(destructiveHint=False))
async def translate_pdf(
    source_path: str,
    workspace_path: str,
    model: str,
    target_lang: str = "zh",
    source_lang: str = "en",
) -> dict:
    """Translate a PDF document while preserving layout.

    Starts a translation job. Returns a job_id for tracking progress.
    """
    ...

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_papers(workspace_path: str) -> list[dict]:
    """List all ingested papers in the workspace."""
    ...

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_concepts(workspace_path: str) -> list[dict]:
    """List all concepts in the workspace."""
    ...

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_queries(workspace_path: str) -> list[dict]:
    """List all archived queries in the workspace."""
    ...

# --- Resources (read-only data) ---

@mcp.resource("wiki://papers/{slug}")
def read_paper_page(slug: str) -> str:
    """Read the full markdown content of a paper page."""
    ...

@mcp.resource("wiki://concepts/{slug}")
def read_concept_page(slug: str) -> str:
    """Read the full markdown content of a concept page."""
    ...

@mcp.resource("wiki://index")
def read_wiki_index() -> str:
    """Read the workspace index page."""
    ...

@mcp.resource("wiki://overview")
def read_wiki_overview() -> str:
    """Read the workspace overview page."""
    ...

# --- Prompts (reusable templates) ---

@mcp.prompt()
def summarize_paper(title: str) -> str:
    """Generate a prompt to summarize a scientific paper."""
    return (
        f"Summarize the scientific paper '{title}'. "
        "Focus on the key contributions, methodology, and main findings. "
        "Use the `read_paper_page` resource to read the full paper content."
    )

@mcp.prompt()
def compare_papers(paper_a: str, paper_b: str) -> str:
    """Generate a prompt to compare two papers."""
    return (
        f"Compare and contrast the papers '{paper_a}' and '{paper_b}'. "
        "Use `read_paper_page` to read both papers, then analyze "
        "their approaches, findings, and how they relate to each other."
    )
```

---

## 4. Integration with Existing FastAPI Sidecar

### Current Architecture

The existing sidecar is a FastAPI app at `backend/src/xreadagent/api/main.py`:

- Binds to `127.0.0.1:<random_port>`
- Prints `SIDECAR_READY port=<N>` on stdout for Electron to discover
- Routes: `/healthz`, `/api/translate`, `/api/ingest`, `/api/query`, `/api/wiki/*`, `/ws/jobs/{id}`, `/ws/events`, `/api/settings`
- The Electron main process spawns `python -m xreadagent.api --port 0` via `SidecarManager`

### Integration Options

**Option A: Mount MCP into the existing FastAPI app (RECOMMENDED)**

The MCP server's ASGI app (SSE or Streamable HTTP) can be mounted as a sub-app:

```python
# In api/main.py
from mcp.server.fastmcp import FastMCP

mcp_server = FastMCP("xreadagent", instructions="...")

# Register tools, resources, prompts on mcp_server
# ...

app = create_app(...)

# Mount the MCP transport at /mcp
app.mount("/mcp", mcp_server.streamable_http_app())
```

Pros:
- Single process, single port. Electron sidecar management unchanged.
- MCP tools can share the same `Workspace` instances and service objects already on `app.state`.
- No new process lifecycle to manage.
- The `SIDECAR_READY` contract stays the same.

Cons:
- The MCP server is only available when the sidecar HTTP transport is running (not via stdio).
- Need to ensure CORS and security settings apply to `/mcp` paths too.

**Option B: Separate MCP process (stdio transport)**

A new entry point `python -m xreadagent.mcp` runs the MCP server via stdio. This is how Claude Desktop expects MCP servers:

```python
# backend/src/xreadagent/mcp/__main__.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("xreadagent")
# Register tools, resources, prompts
mcp.run_stdio_async()  # or mcp.run()
```

Claude Desktop configuration:
```json
{
  "mcpServers": {
    "xreadagent": {
      "command": "python",
      "args": ["-m", "xreadagent.mcp"],
      "env": { "XREAD_AGENT_WORKSPACE": "/path/to/workspace" }
    }
  }
}
```

Pros:
- Standard MCP integration pattern. Works with Claude Desktop, Cursor, etc.
- Independent of the Electron app. Can be used standalone.
- stdio transport has zero network surface area.

Cons:
- Separate process to manage. Electron must spawn it too (or not -- it's for external AI apps).
- Cannot share `app.state` objects with the FastAPI sidecar.
- Duplicate Workspace initialization logic.

**Option C: Both (HTTP mount + stdio entry point)**

Provide both integration paths:
1. HTTP mount in the FastAPI sidecar for in-app use (Electron renderer, browser-based tools).
2. stdio entry point for external AI apps (Claude Desktop, Cursor).

The tool/resource/prompt registration code would be in a shared module (e.g., `xreadagent.mcp.server`) that both the HTTP mount and the stdio entry point import.

### Recommendation

**Option C** is the most flexible. The shared registration module avoids duplication, and both access patterns are supported. The HTTP mount is essentially free since `FastMCP.sse_app()` / `FastMCP.streamable_http_app()` returns a mountable Starlette app.

---

## 5. How XReadAgent Capabilities Map to the Existing Codebase

### Files that implement the capabilities

| Capability | Implementation File | Key Function/Class |
|------------|-------------------|-------------------|
| Ingest paper | `agents/orchestrator.py:ingest_source()` | `IngestAgent.ingest()` + `apply_plan()` |
| Query wiki | `agents/query_orchestrator.py:answer_query()` | `QueryAgent.answer()` |
| Translate PDF | `translation/service.py:TranslationService.start_translation()` | `TranslationService.event_stream()` |
| List papers | `wiki/frontmatter_utils.py:list_papers()` | Reads `wiki/papers/*.md` frontmatter |
| List concepts | `wiki/frontmatter_utils.py:list_concepts()` | Reads `wiki/concepts/*.md` frontmatter |
| List queries | `wiki/frontmatter_utils.py:list_queries()` | Reads `wiki/queries/**/*.md` frontmatter |
| Read paper page | `wiki/frontmatter_utils.py:read_page_content()` | Reads markdown body after frontmatter |
| Read concept page | Same as above | Same |
| Read query page | Same as above | Same |
| Wiki index | `wiki/index_regen.py` / `wiki/workspace.py:index_md_path` | Reads `wiki/index.md` |
| Wiki overview | `wiki/workspace.py:overview_md_path` | Reads `wiki/overview.md` |
| Pipeline convert | `pipeline/router.py:convert_source()` | Routes to MinerU or markitdown |
| Workspace init | `wiki/workspace.py:Workspace.init_empty()` | Creates directory layout + seed files |

### Existing LangChain tools (already built, can be reused for MCP)

The project already has LangChain tool wrappers that wrap the same wiki primitives:

| File | Tools |
|------|-------|
| `agents/tools.py` | `read_extract`, `list_papers`, `list_concepts`, `list_sources`, `read_paper_page`, `read_concept_page`, `search_extracts` |
| `agents/query_tools.py` | All ingest tools + `read_distillation`, `list_recent_logs` |

These LangChain tools wrap the same `xreadagent.wiki.*` primitives that the MCP tools would wrap. The MCP tools would be **thin adapters** over the same underlying functions, not calling the LangChain tools directly (layering rule: `wiki/` must not depend on `agents/`).

---

## 6. Security Considerations

### Current Security Posture

The existing FastAPI sidecar:
- Binds to `127.0.0.1` only (not externally accessible)
- CORS restricted to `localhost` / `127.0.0.1` origins
- File serving restricted to `translations/`, `raw/`, `extracts/` only (`_FILE_ALLOWLIST` in `main.py`)
- `state/` and `wiki/` directories are NOT served over HTTP (intentional data protection)
- Path traversal attacks prevented in `_resolve_workspace_file()`

### New MCP Attack Surface

Adding MCP tools exposes new capabilities:

1. **Read access to wiki/** and **state/** directories**: MCP tools like `read_paper_page` and `list_papers` read from directories that the HTTP sidecar currently does NOT serve. An MCP client could read conversation logs, distillation data, and all wiki content.

2. **Write access via ingest/query tools**: The `ingest_paper` tool creates files, calls LLMs, and modifies the wiki. The `query_wiki` tool archives Q&A. Both have cost implications (LLM API calls) and file system side effects.

3. **LLM cost exposure**: `ingest_paper` and `query_wiki` make LLM API calls. An external AI app calling these tools repeatedly could rack up significant API costs.

4. **Translation cost + compute**: `translate_pdf` spawns a BabelDOC subprocess (CPU + memory intensive) and makes LLM calls per page.

5. **Workspace path injection**: Tools that accept `workspace_path` could be pointed at arbitrary directories. Current validation checks that the path exists and is a directory, but does not verify it's a legitimate XReadAgent workspace.

6. **File path injection**: `ingest_paper` accepts `file_path`. If not validated, an MCP client could attempt to read arbitrary files.

### Guardrails

1. **ToolAnnotations**: Use `readOnlyHint=True` on read-only tools, `destructiveHint=False` on non-destructive write tools, `idempotentHint=True` where applicable. AI models use these hints to decide when to ask for user confirmation.

2. **Elicit for confirmation**: Use `ctx.elicit()` before expensive or destructive operations:
   ```python
   @mcp.tool()
   async def ingest_paper(file_path: str, ctx: Context) -> dict:
       result = await ctx.elicit(
           f"About to ingest '{file_path}'. This will call an LLM and create wiki pages. Proceed?",
           schema=ConfirmationSchema,
       )
       if not result.action:
           return {"status": "cancelled"}
       ...
   ```

3. **Workspace allowlist**: Validate that `workspace_path` points to an initialized XReadAgent workspace (check for `wiki/index.md` existence).

4. **File path validation**: For `ingest_paper`, validate that `file_path` is a real file and restrict to allowed extensions (`.pdf`, `.docx`, `.html`, `.epub`, etc.).

5. **Rate limiting**: Consider adding per-session rate limits for expensive operations (ingest, query, translate). The MCP SDK does not provide this built-in; it would need custom middleware.

6. **Transport security**: For HTTP transport, enable `TransportSecuritySettings` with DNS rebinding protection and restrict `allowed_hosts` to `127.0.0.1`.

7. **No state/ directory exposure as Resources**: The `state/` directory (conversation log, distillation JSON) should NOT be exposed as MCP Resources. Only `wiki/` content should be readable as Resources.

8. **OAuth for network access**: If the MCP server is ever exposed beyond localhost, use `AuthSettings` with OAuth 2.1 and scoped tokens (`xreadagent:read`, `xreadagent:write`, `xreadagent:admin`).

---

## 7. Claude Desktop / Cursor Configuration

For local stdio transport, the MCP server would be configured in the AI app's settings:

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "xreadagent": {
      "command": "/path/to/python",
      "args": ["-m", "xreadagent.mcp"],
      "env": {
        "XREAD_AGENT_WORKSPACE": "/Users/user/XReadAgent-Workspace"
      }
    }
  }
}
```

**Cursor** (`.cursor/mcp.json` in project root):

```json
{
  "mcpServers": {
    "xreadagent": {
      "command": "python",
      "args": ["-m", "xreadagent.mcp"],
      "env": {
        "XREAD_AGENT_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}
```

---

## 8. Implementation Sketch

### Proposed New Module Structure

```
backend/src/xreadagent/
├── mcp/                        NEW -- MCP server module
│   ├── __init__.py             Re-exports
│   ├── __main__.py             stdio entry point: python -m xreadagent.mcp
│   ├── server.py              FastMCP instance + tool/resource/prompt registration
│   └── security.py            Workspace validation, rate limiting, path sanitization
```

### server.py Pattern

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations

mcp = FastMCP(
    name="xreadagent",
    instructions="Scientific research agent with LLM-Wiki memory and PDF translation.",
)


def _resolve_workspace(workspace_path: str | None = None) -> Workspace:
    """Resolve workspace from arg, env var, or raise."""
    path = workspace_path or os.environ.get("XREAD_AGENT_WORKSPACE", "")
    if not path:
        raise ValueError("workspace_path is required (or set XREAD_AGENT_WORKSPACE env)")
    workspace = Workspace.at(Path(path))
    if not workspace.is_initialized():
        raise ValueError(f"Not an initialized workspace: {path}")
    return workspace


# --- Tools ---

@mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True))
async def ingest_paper(
    file_path: str,
    workspace_path: str | None = None,
    title: str | None = None,
    model: str | None = None,
) -> dict:
    """Ingest a scientific paper into the workspace wiki."""
    from xreadagent.agents.ingest import IngestAgent
    from xreadagent.agents.orchestrator import ingest_source
    workspace = _resolve_workspace(workspace_path)
    # ... delegate to existing orchestrator


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def query_wiki(
    question: str,
    workspace_path: str | None = None,
    topic: str | None = None,
    model: str | None = None,
) -> dict:
    """Answer a question using the workspace knowledge base."""
    from xreadagent.agents.query import QueryAgent
    from xreadagent.agents.query_orchestrator import answer_query
    workspace = _resolve_workspace(workspace_path)
    # ... delegate to existing orchestrator


# --- Resources ---

@mcp.resource("wiki://papers/{slug}")
def read_paper_page(slug: str, workspace_path: str | None = None) -> str:
    """Read a paper page from the wiki."""
    from xreadagent.wiki.frontmatter_utils import read_page_content
    workspace = _resolve_workspace(workspace_path)
    path = workspace.papers_dir / f"{slug}.md"
    return read_page_content(path)


# --- Prompts ---

@mcp.prompt()
def summarize_paper(title: str) -> str:
    """Generate a prompt to summarize a scientific paper."""
    return f"Summarize the paper '{title}'. Use `read_paper_page` to read it."
```

### __main__.py (stdio entry point)

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
from xreadagent.mcp.server import mcp

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
```

### HTTP Mount (in api/main.py)

```python
from xreadagent.mcp.server import mcp as mcp_server

# In create_app():
app.mount("/mcp", mcp_server.streamable_http_app())
```

---

## 9. Key Findings Summary

1. **MCP Python SDK v1.27.1** is available, well-maintained, and compatible with XReadAgent's existing dependencies. No dependency conflicts.

2. **FastMCP** provides a high-level API with decorators for tools, resources, and prompts. Async tools with `Context` parameter are fully supported.

3. **HTTP mount is trivial**: `FastMCP.streamable_http_app()` returns a Starlette app that mounts into FastAPI via `app.mount("/mcp", ...)`. This means the MCP server can run in the **same process** as the existing sidecar.

4. **stdio transport** is also available for Claude Desktop / Cursor integration via `python -m xreadagent.mcp`. This would be a **separate process** but uses the same shared registration module.

5. **The existing LangChain tools** in `agents/tools.py` and `agents/query_tools.py` wrap the same wiki primitives. MCP tools should NOT import from `agents/` (layering rule); they should call `wiki/` primitives directly, mirroring what the LangChain tools do.

6. **ToolAnnotations** provide important hints to AI models about which tools are safe vs. destructive vs. read-only. Use them.

7. **The `elicit` feature** on `Context` allows tools to ask for human confirmation before expensive operations. This is the primary safety mechanism for MCP-exposed tools.

8. **Security boundary**: MCP tools would expose read access to `wiki/` content that the HTTP sidecar currently does NOT serve. This is intentional (wiki is human-readable), but `state/` should remain private.

9. **Workspace resolution** needs a consistent strategy: either pass `workspace_path` as a parameter to every tool, or use `XREAD_AGENT_WORKSPACE` env var, or use a lifespan context.

10. **No new infrastructure needed**: MCP adds no databases, no new processes (for HTTP mount), no new ports. It wraps existing functionality.

---

## 10. Caveats / Not Found

- **MCP protocol version `2025-11-25`** was verified from the SDK. The official specification document at spec.modelcontextprotocol.io was not fetched directly (would require web access), but the SDK implements this version.
- **No existing MCP code** exists in the XReadAgent codebase. The references in `agents/ingest.py:505` ("Build tools eagerly so callers that want to expose them via MCP have a handle") and `agents/query.py:117` ("callers wiring MCP / a deepagents loop in a future iteration have a handle") confirm this is planned but not yet implemented.
- **Translation job progress** via MCP: The current translation API uses WebSocket (`/ws/jobs/{job_id}`) for streaming events. MCP tools return a single result. For long-running translations, the MCP tool could return a `job_id` and provide a separate `check_translation_status` tool, or use `ctx.report_progress()` for progress reporting.
- **Multi-workspace support**: The current MCP tool signatures above use `workspace_path` as a parameter. An alternative design could use the MCP session lifespan to bind a workspace once at connection time. This needs design decision.
- **The `tasks` capability** in `ServerCapabilities` is a newer MCP feature for long-running operations. It was not deeply explored but could be relevant for ingest/query operations that take minutes.