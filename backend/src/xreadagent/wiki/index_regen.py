# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic ``wiki/index.md`` regenerator.

Reads frontmatter from every ``wiki/papers/*.md`` and ``wiki/concepts/*.md``,
sorts alphabetically by slug, and emits the index body. Same input → identical
output, so re-running on an unchanged workspace produces a byte-identical
file (and ``write_index`` short-circuits the write).

Inspired by OpenSciReader's ``buildIndexWikiPage`` at
``workspace_knowledge_compile.go:340-378``, but simplified — Karpathy's contract
says ``index.md`` is auto-regenerated, never hand-edited.
"""

from __future__ import annotations

import json
from pathlib import Path

from xreadagent.wiki.atomic import atomic_write_text
from xreadagent.wiki.pages import read_page_frontmatter
from xreadagent.wiki.workspace import Workspace


def _list_page_entries(directory: Path) -> list[tuple[str, str]]:
    """Return ``(slug, title)`` pairs sorted by slug."""
    if not directory.exists():
        return []
    entries: list[tuple[str, str]] = []
    for path in directory.iterdir():
        if not path.is_file() or path.suffix != ".md":
            continue
        slug = path.stem
        try:
            fm = read_page_frontmatter(path)
        except (OSError, UnicodeDecodeError):
            fm = {}
        title_raw = fm.get("title")
        title = str(title_raw).strip() if isinstance(title_raw, str) else ""
        entries.append((slug, title or slug))
    entries.sort(key=lambda row: row[0])
    return entries


def _stats(workspace: Workspace, paper_count: int, concept_count: int) -> dict[str, object]:
    last_ingest = "never"
    sources_path = workspace.sources_json_path
    if sources_path.exists():
        try:
            payload = json.loads(sources_path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        candidates: list[str] = []
        for row in payload.get("sources", []) or []:
            ts = row.get("ingestedAt", "") if isinstance(row, dict) else ""
            if isinstance(ts, str) and ts:
                candidates.append(ts)
        if candidates:
            # ISO 8601 sorts lexicographically — max == latest.
            last_ingest = max(candidates)
    return {
        "documents": paper_count,
        "concepts": concept_count,
        "last_ingest_at": last_ingest,
    }


def regenerate_index(workspace: Workspace) -> str:
    """Return the markdown body for ``wiki/index.md`` without writing it."""
    workspace_title = _read_index_title(workspace) or "Workspace"

    papers = _list_page_entries(workspace.papers_dir)
    concepts = _list_page_entries(workspace.concepts_dir)
    stats = _stats(workspace, len(papers), len(concepts))

    lines: list[str] = []
    lines.append(f"# {workspace_title}\n")
    lines.append("")
    lines.append(
        "<!-- Managed by XReadAgent. Sections delimited by `<!-- xread:managed -->` "
        "are regenerated automatically; hand-edits inside those blocks may be overwritten. -->"
    )
    lines.append("")
    lines.append("## Documents")
    lines.append("")
    if papers:
        for slug, title in papers:
            lines.append(f"- [[papers/{slug}|{title}]]")
    else:
        lines.append("_(no documents yet — run an ingest to populate)_")
    lines.append("")
    lines.append("## Concepts")
    lines.append("")
    if concepts:
        for slug, title in concepts:
            lines.append(f"- [[concepts/{slug}|{title}]]")
    else:
        lines.append("_(no concepts yet)_")
    lines.append("")
    lines.append("## Stats")
    lines.append("")
    lines.append(f"- documents: {stats['documents']}")
    lines.append(f"- concepts: {stats['concepts']}")
    lines.append(f"- last_ingest_at: {stats['last_ingest_at']}")
    lines.append("")
    return "\n".join(lines)


def write_index(workspace: Workspace) -> bool:
    """Regenerate the index and write it iff it differs from the on-disk file.

    Returns ``True`` if a write occurred.
    """
    new_body = regenerate_index(workspace)
    path = workspace.index_md_path
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == new_body:
            return False
    atomic_write_text(path, new_body)
    return True


def _read_index_title(workspace: Workspace) -> str:
    """Recover the H1 title from an existing index, falling back to "Workspace"."""
    path = workspace.index_md_path
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""
