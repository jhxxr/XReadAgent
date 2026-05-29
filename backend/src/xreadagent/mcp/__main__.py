# SPDX-License-Identifier: AGPL-3.0-or-later
"""``python -m xreadagent.mcp`` — stdio entry point for MCP server.

Runs the FastMCP server using stdio transport, which is how Claude Desktop
and similar AI tools expect to communicate with MCP servers.

Configuration example (Claude Desktop ``claude_desktop_config.json``):

.. code-block:: json

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
"""

from __future__ import annotations

from xreadagent.mcp.server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
