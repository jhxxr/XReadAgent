# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared frontmatter + content extraction utilities for wiki pages.

Extracts the repeated pattern of scanning ``wiki/papers/*.md``,
``wiki/concepts/*.md``, and ``wiki/queries/**/*.md`` from the agent
modules into a single framework-agnostic utility. The API router and
the ingest/query agents both call into this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from xreadagent.wiki.pages import read_page_frontmatter as read_page_frontmatter
from xreadagent.wiki.workspace import Workspace

__all__ = [
    "list_concepts",
    "list_papers",
    "list_queries",
    "read_page_content",
    "read_page_frontmatter",
]


def read_page_content(path: Path) -> str:
    """Return the markdown body *after* the YAML frontmatter block.

    Returns the full file text when there is no frontmatter.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return text
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            # Everything after the closing ``---`` (skip blank line).
            rest = lines[idx + 1 :]
            return "\n".join(rest)
    # No closing ``---`` — treat the whole thing as content.
    return text


def list_papers(workspace: Workspace) -> list[dict[str, Any]]:
    """Return a summary dict for every paper page in the workspace.

    Keys match the frontend ``PaperSummary`` type: slug, title, authors,
    year, ingestedAt. The ``ingestedAt`` falls back to the file mtime when
    no source manifest entry exists.
    """
    from xreadagent.wiki.sources import SourcesIndex

    papers_dir = workspace.papers_dir
    if not papers_dir.exists():
        return []

    sources_index = SourcesIndex.load(workspace)
    slug_to_source = {s.slug: s for s in sources_index.all()}

    results: list[dict[str, Any]] = []
    for path in sorted(papers_dir.iterdir()):
        if not path.is_file() or path.suffix != ".md":
            continue
        slug = path.stem
        try:
            fm = read_page_frontmatter(path)
        except (OSError, UnicodeDecodeError):
            fm = {}
        source = slug_to_source.get(slug)
        ingested_at = ""
        if source and source.ingestedAt:
            ingested_at = source.ingestedAt
        else:
            try:
                mtime = path.stat().st_mtime
                from datetime import datetime, timezone

                ingested_at = (
                    datetime.fromtimestamp(mtime, tz=timezone.utc)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z")
                )
            except OSError:
                ingested_at = ""
        results.append(
            {
                "slug": slug,
                "title": str(fm.get("title", "")),
                "authors": fm.get("authors", []) or [],
                "year": fm.get("year") or None,
                "ingestedAt": ingested_at,
                "sourcePath": source.sourcePath if source and source.sourcePath else None,
                "sourceKind": source.kind if source else "",
            }
        )
    return results


def list_concepts(workspace: Workspace) -> list[dict[str, Any]]:
    """Return a summary dict for every concept page in the workspace.

    Keys match the frontend ``ConceptSummary`` type: slug, title, aliases,
    paperCount (estimated from ``## Related Papers`` bullet count).
    """
    concepts_dir = workspace.concepts_dir
    if not concepts_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for path in sorted(concepts_dir.iterdir()):
        if not path.is_file() or path.suffix != ".md":
            continue
        slug = path.stem
        try:
            fm = read_page_frontmatter(path)
        except (OSError, UnicodeDecodeError):
            fm = {}
        paper_count = _count_related_papers(path)
        aliases = fm.get("aliases", []) or []
        if not isinstance(aliases, list):
            aliases = []
        results.append(
            {
                "slug": slug,
                "title": str(fm.get("title", slug)),
                "aliases": [str(a) for a in aliases],
                "paperCount": paper_count,
            }
        )
    return results


def list_queries(workspace: Workspace) -> list[dict[str, Any]]:
    """Return a summary dict for every archived query page.

    Keys match the frontend ``QuerySummary`` type: id, question, topic,
    archivedAt. The ``id`` is ``{topic}/{filename_stem}``.
    """
    queries_dir = workspace.queries_dir
    if not queries_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for topic_dir in sorted(queries_dir.iterdir()):
        if not topic_dir.is_dir():
            continue
        topic = topic_dir.name
        for path in sorted(topic_dir.iterdir()):
            if not path.is_file() or path.suffix != ".md":
                continue
            filename_stem = path.stem
            try:
                fm = read_page_frontmatter(path)
            except (OSError, UnicodeDecodeError):
                fm = {}
            raw_date = str(fm.get("date", ""))
            archived_at = f"{raw_date}T00:00:00Z" if raw_date else ""
            results.append(
                {
                    "id": f"{topic}/{filename_stem}",
                    "question": str(fm.get("question", "")),
                    "topic": topic,
                    "archivedAt": archived_at,
                }
            )
    return results


def _count_related_papers(path: Path) -> int:
    """Count bullet items under the ``## Related Papers`` section."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    in_section = False
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped.lower() == "## related papers"
            continue
        if in_section:
            if stripped.startswith("## "):
                break
            if stripped.startswith("- ") or stripped.startswith("* "):
                count += 1
    return count
