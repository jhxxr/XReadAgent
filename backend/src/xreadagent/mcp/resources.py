# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP resource definitions for XReadAgent.

Resources are URI-addressed, read-only data that AI models can browse.
The URI scheme ``xread://`` is used for all XReadAgent resources.

Only wiki/ content is exposed as resources. The state/ directory (conversation
log, distillation JSON) is intentionally excluded per the security boundary
defined in the error-handling spec.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from xreadagent.mcp._helpers import resolve_workspace
from xreadagent.wiki.paths import validate_wiki_path

# ---------------------------------------------------------------------------
# Resource registration
# ---------------------------------------------------------------------------


def register_resources(mcp: FastMCP) -> None:
    """Register all MCP resources on the given FastMCP instance."""

    @mcp.resource("xread://papers")
    def papers_index() -> str:
        """List all ingested papers in the workspace."""
        workspace = resolve_workspace()
        from xreadagent.wiki.frontmatter_utils import list_papers

        papers = list_papers(workspace)
        if not papers:
            return "No papers ingested yet."
        lines = ["# Papers", ""]
        for p in papers:
            title = p.get("title", p.get("slug", "untitled"))
            slug = p.get("slug", "?")
            year = p.get("year", "")
            year_str = f" ({year})" if year else ""
            lines.append(f"- **{title}**{year_str} `xread://paper/{slug}`")
        return "\n".join(lines)

    @mcp.resource("xread://paper/{slug}")
    def paper_page(slug: str) -> str:
        """Read the full markdown content of a paper page."""
        workspace = resolve_workspace()
        path = workspace.papers_dir / f"{slug}.md"
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"paper not found: {slug}")
        from xreadagent.wiki.frontmatter_utils import read_page_content

        return read_page_content(path)

    @mcp.resource("xread://wiki/{path}")
    def wiki_page(path: str) -> str:
        """Read a wiki page by its relative path under the wiki/ directory."""
        workspace = resolve_workspace()
        resolved = validate_wiki_path(workspace.wiki_dir, path)
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"wiki page not found: {path}")
        from xreadagent.wiki.frontmatter_utils import read_page_content

        return read_page_content(resolved)


__all__ = ["register_resources"]
