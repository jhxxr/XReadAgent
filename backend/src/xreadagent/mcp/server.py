# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastMCP server instance and factory.

Creates the :class:`FastMCP` server with all tools and resources registered,
and provides :func:`create_mcp_app` that returns the mountable Starlette app
for FastAPI integration.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from xreadagent.mcp.resources import register_resources
from xreadagent.mcp.tools import register_tools

mcp = FastMCP(
    name="xreadagent",
    instructions=(
        "XReadAgent: scientific research agent with LLM-Wiki memory. "
        "Ingest papers, query the knowledge base, translate PDFs, "
        "and browse wiki content."
    ),
)

register_tools(mcp)
register_resources(mcp)


def create_mcp_app() -> FastMCP:
    """Return the :class:`FastMCP` instance (for mounting or stdio transport)."""
    return mcp


__all__ = ["create_mcp_app", "mcp"]
