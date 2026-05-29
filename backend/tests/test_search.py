# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for xreadagent.wiki.search — hybrid semantic search."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from xreadagent.wiki.search import SearchResult, semantic_search
from xreadagent.wiki.workspace import Workspace


@pytest.fixture()
def workspace(tmp_path: object) -> Workspace:
    ws = Workspace.at(tmp_path)  # type: ignore[arg-type]
    ws.init_empty("Test Workspace", workspace_id="test")
    return ws


class TestSearchResult:
    def test_search_result_is_frozen(self) -> None:
        r = SearchResult(slug="a", title="A", page_type="paper", score=0.5, source="fts")
        with pytest.raises(AttributeError):
            r.slug = "b"  # type: ignore[misc]

    def test_search_result_fields(self) -> None:
        r = SearchResult(
            slug="test",
            title="Test Paper",
            page_type="paper",
            score=0.032,
            source="vec+fts",
            snippet="Some text...",
            vec_rank=1,
            fts_rank=2,
        )
        assert r.slug == "test"
        assert r.source == "vec+fts"
        assert r.vec_rank == 1
        assert r.fts_rank == 2


class TestSemanticSearch:
    def test_empty_query_returns_empty(self, workspace: Workspace) -> None:
        result = semantic_search("", workspace)
        assert result == []

    def test_whitespace_query_returns_empty(self, workspace: Workspace) -> None:
        result = semantic_search("   ", workspace)
        assert result == []

    def test_search_when_vector_store_unavailable(self, workspace: Workspace) -> None:
        """When sqlite-vec is not installed, search returns empty (graceful degradation)."""
        with patch("xreadagent.wiki.search._open_vector_store", return_value=None):
            result = semantic_search("test query", workspace)
            assert result == []

    def test_search_with_mock_vector_store(self, workspace: Workspace) -> None:
        """Test search path with a mocked VectorStore."""
        mock_store = MagicMock()
        mock_store.search_hybrid.return_value = [
            {
                "slug": "attention-paper",
                "title": "Attention Is All You Need",
                "page_type": "paper",
                "score": 0.032,
                "source": "vec+fts",
                "vec_rank": 1,
                "fts_rank": 2,
            }
        ]
        mock_store.close = MagicMock()

        with (
            patch("xreadagent.wiki.search._open_vector_store", return_value=mock_store),
            patch("xreadagent.wiki.search._embed_query", return_value=[0.1] * 384),
        ):
            results = semantic_search("attention mechanism", workspace)
            assert len(results) == 1
            assert results[0].slug == "attention-paper"
            assert results[0].source == "vec+fts"

    def test_search_fts_only_fallback(self, workspace: Workspace) -> None:
        """When embedding fails, search falls back to FTS5-only."""
        mock_store = MagicMock()
        mock_store.search_fts.return_value = [
            {"slug": "paper-1", "title": "Paper One", "rank": -1.5},
        ]
        mock_store.close = MagicMock()

        with (
            patch("xreadagent.wiki.search._open_vector_store", return_value=mock_store),
            patch("xreadagent.wiki.search._embed_query", return_value=None),
        ):
            results = semantic_search("test", workspace)
            assert len(results) == 1
            assert results[0].source == "fts"

    def test_search_page_type_filter(self, workspace: Workspace) -> None:
        """page_type filter excludes non-matching results."""
        mock_store = MagicMock()
        mock_store.search_hybrid.return_value = [
            {
                "slug": "paper-1", "title": "P1", "page_type": "paper",
                "score": 0.03, "source": "fts",
                "vec_rank": None, "fts_rank": 1,
            },
            {
                "slug": "concept-1", "title": "C1", "page_type": "concept",
                "score": 0.02, "source": "fts",
                "vec_rank": None, "fts_rank": 2,
            },
        ]
        mock_store.close = MagicMock()

        with (
            patch("xreadagent.wiki.search._open_vector_store", return_value=mock_store),
            patch("xreadagent.wiki.search._embed_query", return_value=[0.1] * 384),
        ):
            results = semantic_search("test", workspace, page_type="paper")
            assert len(results) == 1
            assert results[0].page_type == "paper"

    def test_top_k_limits_results(self, workspace: Workspace) -> None:
        """top_k parameter limits the number of results."""
        mock_store = MagicMock()
        mock_store.search_hybrid.return_value = [
            {
                "slug": f"p-{i}", "title": f"P{i}", "page_type": "paper",
                "score": 0.03 - i * 0.001, "source": "fts",
                "vec_rank": None, "fts_rank": i + 1,
            }
            for i in range(10)
        ]
        mock_store.close = MagicMock()

        with (
            patch("xreadagent.wiki.search._open_vector_store", return_value=mock_store),
            patch("xreadagent.wiki.search._embed_query", return_value=[0.1] * 384),
        ):
            results = semantic_search("test", workspace, top_k=3)
            assert len(results) == 3
