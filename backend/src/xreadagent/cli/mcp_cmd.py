# SPDX-License-Identifier: AGPL-3.0-or-later
"""``xreadagent mcp`` subcommand — run the MCP server via stdio transport.

This is the CLI entry point for Claude Desktop / Cursor integration.
The MCP server communicates over stdin/stdout using JSON-RPC.

Configuration example (Claude Desktop ``claude_desktop_config.json``):

.. code-block:: json

    {
      "mcpServers": {
        "xreadagent": {
          "command": "xreadagent",
          "args": ["mcp"],
          "env": {
            "XREAD_AGENT_WORKSPACE": "/path/to/workspace"
          }
        }
      }
    }
"""

from __future__ import annotations

import argparse


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "mcp",
        help="Run the MCP server (stdio transport) for AI tool integration.",
        description=(
            "Start the XReadAgent MCP server using stdio transport. "
            "This is designed for integration with AI tools like Claude Desktop "
            "and Cursor that spawn MCP server processes. The server reads "
            "JSON-RPC from stdin and writes responses to stdout. Set "
            "XREAD_AGENT_WORKSPACE env var to specify the default workspace."
        ),
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    try:
        from xreadagent.mcp.server import mcp
    except ImportError as exc:
        print(f"Error: MCP SDK not installed. Install via: pip install mcp\n{exc}")
        return 1

    mcp.run()
    return 0


__all__ = ["add_parser", "run"]
