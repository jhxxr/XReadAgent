# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only tool wrappers for the query agent.

The query agent navigates the wiki without ever writing back to it. Most
tools are reused from ``agents.tools`` (the ingest tool set is already
read-only); we add ``read_distillation`` and ``list_recent_logs`` which the
query agent needs but the ingest agent does not.

ALL tools defined here MUST be read-only. The ``test_query_isolation`` test
verifies that running a query never mutates the synthesis-zone files.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool, tool

from xreadagent.agents.tools import build_ingest_tools
from xreadagent.wiki.workspace import Workspace

_MAX_RECENT_LOG_ENTRIES = 50


def build_query_tools(workspace: Workspace) -> list[BaseTool]:
    """Build the ten read-only tools the query agent uses."""
    base_tools = build_ingest_tools(workspace)

    @tool
    def read_distillation(slug: str) -> dict[str, Any]:
        """Return ``state/by-source/{slug}.json`` parsed as a dict (empty if absent)."""
        clean = slug.strip()
        if not clean:
            return {}
        path = workspace.state_by_source_dir / f"{clean}.json"
        if not path.exists():
            return {}
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return {}
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return parsed

    @tool
    def list_recent_logs(n: int = 10) -> list[str]:
        """Return the last ``n`` entries from ``wiki/log.md`` (each a ``## [...]`` block)."""
        if n <= 0:
            return []
        capped = min(n, _MAX_RECENT_LOG_ENTRIES)
        path = workspace.log_md_path
        if not path.exists():
            return []
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []

        # Split on '## [' headings; the file's preamble is everything before the first.
        entries: list[str] = []
        current: list[str] = []
        for line in body.splitlines():
            if line.startswith("## ["):
                if current:
                    entries.append("\n".join(current).rstrip())
                current = [line]
            elif current:
                current.append(line)
        if current:
            entries.append("\n".join(current).rstrip())
        return entries[-capped:]

    tools: list[BaseTool] = [*base_tools, read_distillation, list_recent_logs]
    return tools


__all__ = ["build_query_tools"]
