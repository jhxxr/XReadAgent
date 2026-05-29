# SPDX-License-Identifier: AGPL-3.0-or-later
"""LangChain tool wrappers around wiki primitives.

These tools are what a deepagents loop would call to inspect workspace state
before producing an ``IngestPlan``. They are intentionally thin — domain logic
stays in ``xreadagent.wiki.*`` — and their return values are JSON-friendly so
LangChain serialization is a no-op.

The factory ``build_ingest_tools`` closes each tool over a ``Workspace`` so the
agent never has to manage paths itself. Eight tools are provided: read_extract,
list_papers, list_concepts, read_paper, read_concept, search_wiki, read_index,
and semantic_search (hybrid vector + FTS5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, tool

from xreadagent.wiki.pages import read_page_frontmatter
from xreadagent.wiki.workspace import Workspace

_MAX_SEARCH_HITS = 50


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _list_page_meta(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix != ".md":
            continue
        slug = path.stem
        try:
            fm = read_page_frontmatter(path)
        except (OSError, UnicodeDecodeError):
            fm = {}
        rows.append({"slug": slug, "frontmatter": fm})
    return rows


def build_ingest_tools(workspace: Workspace) -> list[BaseTool]:
    """Build the eight tools the ingest agent uses to inspect workspace state."""

    @tool
    def read_extract(slug: str) -> str:
        """Return the markdown extract under ``extracts/{slug}.md`` (empty if absent)."""
        clean = slug.strip()
        if not clean:
            return ""
        return _read_text(workspace.extracts_dir / f"{clean}.md")

    @tool
    def list_papers() -> list[dict[str, Any]]:
        """List existing paper pages with slug + frontmatter (title, year, etc.)."""
        rows: list[dict[str, Any]] = []
        for entry in _list_page_meta(workspace.papers_dir):
            fm = entry["frontmatter"]
            rows.append(
                {
                    "slug": entry["slug"],
                    "title": str(fm.get("title", "")) if isinstance(fm, dict) else "",
                    "year": fm.get("year", 0) if isinstance(fm, dict) else 0,
                }
            )
        return rows

    @tool
    def list_concepts() -> list[dict[str, Any]]:
        """List existing concept pages with slug + canonical name + aliases."""
        rows: list[dict[str, Any]] = []
        for entry in _list_page_meta(workspace.concepts_dir):
            fm = entry["frontmatter"]
            title = str(fm.get("title", "")) if isinstance(fm, dict) else ""
            aliases_raw = fm.get("aliases", []) if isinstance(fm, dict) else []
            aliases = [str(a) for a in aliases_raw] if isinstance(aliases_raw, list) else []
            rows.append({"slug": entry["slug"], "canonical_name": title, "aliases": aliases})
        return rows

    @tool
    def read_paper(slug: str) -> str:
        """Return the full markdown body of ``wiki/papers/{slug}.md``."""
        clean = slug.strip()
        if not clean:
            return ""
        return _read_text(workspace.papers_dir / f"{clean}.md")

    @tool
    def read_concept(slug: str) -> str:
        """Return the full markdown body of ``wiki/concepts/{slug}.md``."""
        clean = slug.strip()
        if not clean:
            return ""
        return _read_text(workspace.concepts_dir / f"{clean}.md")

    def _grep_wiki(pattern: str) -> list[dict[str, Any]]:
        """Grep ``pattern`` across ``wiki/*.md``; returns up to 50 hits."""
        needle = pattern.strip()
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
                if needle in line:
                    hits.append({"path": rel, "line_no": line_no, "match": line.strip()})
                    if len(hits) >= _MAX_SEARCH_HITS:
                        return hits
        return hits

    @tool
    def search_wiki(pattern: str) -> list[dict[str, Any]]:
        """Grep ``pattern`` across ``wiki/*.md``; returns up to 50 hits."""
        return _grep_wiki(pattern)

    @tool
    def read_index() -> str:
        """Return the current ``wiki/index.md`` body."""
        return _read_text(workspace.index_md_path)

    @tool
    def semantic_search(query: str) -> list[dict[str, Any]]:
        """Search wiki pages by semantic similarity. Returns top-10 matches.

        Uses hybrid vector + full-text search with Reciprocal Rank Fusion.
        Falls back to keyword search when the vector index is unavailable.
        Each result contains: slug, title, page_type, score, source.
        """
        clean = query.strip()
        if not clean:
            return []
        try:
            from xreadagent.wiki.search import semantic_search as _semantic_search

            results = _semantic_search(clean, workspace, top_k=10)
            return [
                {
                    "slug": r.slug,
                    "title": r.title,
                    "page_type": r.page_type,
                    "score": r.score,
                    "source": r.source,
                    "snippet": r.snippet,
                }
                for r in results
            ]
        except Exception:  # noqa: BLE001
            # Degrade to keyword search when semantic search is unavailable.
            # Broad catch is intentional: any failure in the vector/FTS pipeline
            # (missing deps, corrupt vec.sqlite, embedding model error) should
            # fall back gracefully rather than crash the agent tool loop.
            return _grep_wiki(clean)

    tools: list[BaseTool] = [
        read_extract,
        list_papers,
        list_concepts,
        read_paper,
        read_concept,
        search_wiki,
        read_index,
        semantic_search,
    ]
    return tools


__all__ = ["build_ingest_tools"]
