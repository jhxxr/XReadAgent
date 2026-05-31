# SPDX-License-Identifier: AGPL-3.0-or-later
"""Keyword (grep) search over the LLM-Wiki markdown pages.

The "memory" subsystem is a pure LLM-Wiki: markdown pages + ``index.md`` that
an agent navigates by reading the index, listing/reading pages, and grepping.
There is no embedding / vector index. These helpers provide the two grep
shapes the codebase needs:

- :func:`grep_wiki_lines` — line-level hits across ``wiki/*.md`` for the agent's
  ``search_wiki`` tool.
- :func:`search_wiki_pages` — page-level aggregation (one row per matching
  paper/concept page, scored by match count) for the MCP ``semantic_search``
  tool.

Matching is case-insensitive substring matching.
"""

from __future__ import annotations

from typing import Any

from xreadagent.wiki.frontmatter_utils import read_page_content
from xreadagent.wiki.pages import read_page_frontmatter
from xreadagent.wiki.workspace import Workspace


def grep_wiki_lines(
    workspace: Workspace, pattern: str, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Grep ``pattern`` (case-insensitive) across ``wiki/*.md``.

    Returns up to ``limit`` line-level hits as ``{"path", "line_no", "match"}``
    where ``path`` is relative to the wiki directory.
    """
    needle = pattern.strip().lower()
    if not needle:
        return []
    hits: list[dict[str, Any]] = []
    for path in sorted(workspace.wiki_dir.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(workspace.wiki_dir).as_posix()
        for line_no, line in enumerate(lines, start=1):
            if needle in line.lower():
                hits.append({"path": rel, "line_no": line_no, "match": line.strip()})
                if len(hits) >= limit:
                    return hits
    return hits


def search_wiki_pages(
    workspace: Workspace, query: str, *, top_k: int = 10
) -> list[dict[str, Any]]:
    """Aggregate case-insensitive matches per paper/concept page.

    Scans ``wiki/papers/*.md`` and ``wiki/concepts/*.md``, counts occurrences
    of ``query`` in each page, and returns the top ``top_k`` pages sorted by
    score (match count) descending. Pages with zero matches are skipped.

    Each result is ``{"slug", "title", "page_type", "score", "snippet"}``.
    """
    needle = query.strip().lower()
    if not needle:
        return []

    results: list[dict[str, Any]] = []
    for directory, page_type in (
        (workspace.papers_dir, "paper"),
        (workspace.concepts_dir, "concept"),
    ):
        if not directory.exists():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix != ".md":
                continue
            try:
                content = read_page_content(path)
            except (OSError, UnicodeDecodeError):
                continue
            score = content.lower().count(needle)
            if score == 0:
                continue
            try:
                fm = read_page_frontmatter(path)
            except (OSError, UnicodeDecodeError):
                fm = {}
            title = str(fm.get("title", path.stem)) if isinstance(fm, dict) else path.stem
            results.append(
                {
                    "slug": path.stem,
                    "title": title,
                    "page_type": page_type,
                    "score": float(score),
                    "snippet": content[:200],
                }
            )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


__all__ = ["grep_wiki_lines", "search_wiki_pages"]
