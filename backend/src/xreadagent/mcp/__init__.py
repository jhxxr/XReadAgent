# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP (Model Context Protocol) server for XReadAgent.

Exposes XReadAgent capabilities (ingest, query, translate, wiki browsing)
as MCP tools and resources so external AI tools (Claude Desktop, Cursor, etc.)
can interact with XReadAgent workspaces.

Transport options:

- **HTTP mount**: mount into the existing FastAPI sidecar via
  ``app.mount("/mcp", create_mcp_app())``.
- **stdio**: run via ``python -m xreadagent.mcp`` for Claude Desktop integration.
"""

from __future__ import annotations

from xreadagent.mcp.server import create_mcp_app, mcp

__all__ = ["create_mcp_app", "mcp"]
