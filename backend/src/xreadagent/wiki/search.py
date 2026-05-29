# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hybrid semantic search over wiki pages -- FTS5 + vec0 + RRF.

The top-level :func:`semantic_search` function is the primary entry point.
It combines vector similarity (via ``vec0``) and lexical relevance (via ``FTS5``)
using Reciprocal Rank Fusion.

When the embedding engine is unavailable but sqlite-vec is installed, the
search degrades to FTS5-only (still useful). When sqlite-vec itself is not
installed, ``semantic_search`` returns an empty list -- callers like the
``semantic_search`` LangChain tool should catch this and fall back to keyword
search (``search_wiki`` / grep).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final

from xreadagent.wiki.workspace import Workspace

_logger = logging.getLogger(__name__)

_RRF_K: Final[int] = 60


@dataclass(frozen=True)
class SearchResult:
    """A single search hit from the wiki."""

    slug: str
    title: str
    page_type: str
    score: float
    source: str  # "vec", "fts", or "vec+fts"
    snippet: str = ""
    vec_rank: int | None = None
    fts_rank: int | None = None


def semantic_search(
    query: str,
    workspace: Workspace,
    *,
    top_k: int = 10,
    page_type: str | None = None,
) -> list[SearchResult]:
    """Search wiki pages using hybrid FTS5 + vector similarity + RRF.

    Parameters
    ----------
    query
        The search query string.
    workspace
        The workspace to search.
    top_k
        Maximum number of results to return.
    page_type
        Filter to ``"paper"`` or ``"concept"``; ``None`` for both.

    Returns
    -------
    List of :class:`SearchResult` sorted by descending RRF score.
    """
    if not query.strip():
        return []

    vec_store = _open_vector_store(workspace)
    if vec_store is None:
        return []

    query_embedding = _embed_query(query)

    if query_embedding is not None:
        raw = vec_store.search_hybrid(
            query_embedding, query, k=top_k, rrf_k=_RRF_K
        )
    else:
        # Fallback to FTS5-only when embedding is unavailable.
        raw = vec_store.search_fts(query, k=top_k)
        raw = [
            {
                "slug": r["slug"],
                "title": r.get("title", r["slug"]),
                "page_type": "unknown",
                "score": 1.0 / (_RRF_K + rank),
                "source": "fts",
                "vec_rank": None,
                "fts_rank": rank,
            }
            for rank, r in enumerate(raw, start=1)
        ]

    vec_store.close()

    results: list[SearchResult] = []
    for item in raw:
        if page_type is not None and item.get("page_type") != page_type:
            continue
        results.append(
            SearchResult(
                slug=item["slug"],
                title=item.get("title", item["slug"]),
                page_type=item.get("page_type", "unknown"),
                score=item["score"],
                source=item.get("source", "unknown"),
                snippet=_build_snippet(item["slug"], workspace),
                vec_rank=item.get("vec_rank"),
                fts_rank=item.get("fts_rank"),
            )
        )
    return results[:top_k]


def _open_vector_store(workspace: Workspace) -> Any | None:
    """Try to open the VectorStore; return None on failure."""
    try:
        from xreadagent.wiki.vector import VectorStore

        return VectorStore.open(workspace)
    except ImportError:
        _logger.debug("sqlite-vec not available, search limited to FTS5")
        return None
    except Exception as exc:
        _logger.warning("failed to open vec.sqlite: %s", exc)
        return None


def _embed_query(query: str) -> list[float] | None:
    """Try to embed the query; return None on failure."""
    try:
        from xreadagent.wiki.embedder import Embedder

        embedder = Embedder()
        return embedder.embed(query)
    except ImportError:
        _logger.debug("embedding deps not available, falling back to FTS5-only")
        return None
    except Exception as exc:
        _logger.warning("embedding failed, falling back to FTS5-only: %s", exc)
        return None


def _build_snippet(slug: str, workspace: Workspace) -> str:
    """Extract a short text snippet from the wiki page."""
    from xreadagent.wiki.frontmatter_utils import read_page_content

    # Try paper pages then concept pages.
    for directory in (workspace.papers_dir, workspace.concepts_dir):
        path = directory / f"{slug}.md"
        if path.exists():
            try:
                content = read_page_content(path)
                # First 200 chars, stripped.
                snippet = content.strip()[:200]
                if len(snippet) == 200:
                    snippet = snippet.rstrip() + "..."
                return snippet
            except (OSError, UnicodeDecodeError):
                return ""
    return ""


__all__ = ["SearchResult", "semantic_search"]
