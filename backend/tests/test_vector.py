# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for xreadagent.wiki.vector — VectorStore with sqlite-vec + FTS5."""

from __future__ import annotations

import pytest

from xreadagent.wiki.workspace import Workspace

# Skip the entire module when sqlite-vec is not installed.
sqlite_vec = pytest.importorskip("sqlite_vec")

from xreadagent.wiki.vector import VectorStore  # noqa: E402


@pytest.fixture()
def workspace(tmp_path: object) -> Workspace:
    """Create a minimal initialized workspace in a temp directory."""
    ws = Workspace.at(tmp_path)  # type: ignore[arg-type]
    ws.init_empty("Test Workspace", workspace_id="test")
    return ws


@pytest.fixture()
def store(workspace: Workspace) -> VectorStore:
    """Open a VectorStore for the test workspace."""
    s = VectorStore.open(workspace)
    yield s
    s.close()


class TestVectorStoreOpen:
    def test_creates_vec_sqlite_on_open(self, workspace: Workspace) -> None:
        store = VectorStore.open(workspace)
        assert workspace.vec_sqlite_path.exists()
        store.close()

    def test_creates_required_tables(self, workspace: Workspace) -> None:
        store = VectorStore.open(workspace)
        conn = store.conn
        # Check that the expected tables exist in sqlite_master.
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "wiki_pages" in tables
        assert "fts_pages" in tables
        store.close()


class TestVectorStoreUpsert:
    def test_upsert_with_embedding(self, store: VectorStore) -> None:
        embedding = [0.1] * 384
        store.upsert(
            "test-paper", "paper", "Background content here",
            embedding=embedding, title="Test Paper",
        )
        assert store.count() == 1

    def test_upsert_without_embedding(self, store: VectorStore) -> None:
        store.upsert(
            "test-concept", "concept", "Summary of the concept",
            title="Test Concept",
        )
        assert store.count() == 1

    def test_upsert_idempotent_same_content(self, store: VectorStore) -> None:
        """Same content hash → no extra row."""
        embedding = [0.2] * 384
        store.upsert("paper-1", "paper", "Same content", embedding=embedding, title="P1")
        store.upsert("paper-1", "paper", "Same content", embedding=embedding, title="P1")
        assert store.count() == 1

    def test_upsert_updates_on_content_change(self, store: VectorStore) -> None:
        """Different content → update existing row."""
        embedding = [0.3] * 384
        store.upsert("paper-1", "paper", "Version 1", embedding=embedding, title="P1")
        store.upsert("paper-1", "paper", "Version 2", embedding=embedding, title="P1 Updated")
        assert store.count() == 1
        # Verify title was updated.
        row = store.conn.execute(
            "SELECT title FROM wiki_pages WHERE slug = 'paper-1'"
        ).fetchone()
        assert row[0] == "P1 Updated"


class TestVectorStoreDelete:
    def test_delete_removes_all_entries(self, store: VectorStore) -> None:
        embedding = [0.1] * 384
        store.upsert("to-delete", "paper", "Content", embedding=embedding, title="Delete Me")
        assert store.count() == 1
        store.delete("to-delete")
        assert store.count() == 0

    def test_delete_nonexistent_is_noop(self, store: VectorStore) -> None:
        store.delete("never-existed")
        assert store.count() == 0


class TestVectorStoreSearchVector:
    def test_knn_search(self, store: VectorStore) -> None:
        # Insert two pages with different embeddings.
        embedding_a = [0.0] * 384
        embedding_a[0] = 1.0  # Pointing along axis 0.
        embedding_b = [0.0] * 384
        embedding_b[1] = 1.0  # Pointing along axis 1.
        store.upsert("paper-a", "paper", "Content A", embedding=embedding_a, title="Paper A")
        store.upsert("paper-b", "paper", "Content B", embedding=embedding_b, title="Paper B")

        # Query close to A should rank A first.
        query = [0.0] * 384
        query[0] = 0.9
        results = store.search_vector(query, k=2)
        assert len(results) >= 1
        assert results[0]["slug"] == "paper-a"

    def test_knn_wrong_dimension_returns_empty(self, store: VectorStore) -> None:
        results = store.search_vector([0.1] * 128, k=5)  # Wrong dimension.
        assert results == []


class TestVectorStoreSearchFts:
    def test_fts_search(self, store: VectorStore) -> None:
        store.upsert(
            "paper-x", "paper",
            "The transformer architecture uses self-attention",
            title="Transformer",
        )
        results = store.search_fts("transformer", k=5)
        assert len(results) >= 1
        assert results[0]["slug"] == "paper-x"

    def test_fts_empty_query_returns_empty(self, store: VectorStore) -> None:
        results = store.search_fts("", k=5)
        assert results == []


class TestVectorStoreSearchHybrid:
    def test_hybrid_rrf(self, store: VectorStore) -> None:
        # Insert a page whose title matches the FTS query and whose embedding
        # is close to the query vector.
        embedding = [0.0] * 384
        embedding[0] = 1.0
        store.upsert(
            "attention-paper",
            "paper",
            "The attention mechanism is central to transformer models.",
            embedding=embedding,
            title="Attention Is All You Need",
        )

        query_emb = [0.0] * 384
        query_emb[0] = 0.95
        results = store.search_hybrid(query_emb, "attention transformer", k=5)
        assert len(results) >= 1
        assert results[0]["slug"] == "attention-paper"
        assert results[0]["source"] == "vec+fts"
        assert results[0]["score"] > 0


class TestVectorStoreCount:
    def test_count_empty(self, store: VectorStore) -> None:
        assert store.count() == 0

    def test_count_after_inserts(self, store: VectorStore) -> None:
        store.upsert("a", "paper", "Content A", title="A")
        store.upsert("b", "concept", "Content B", title="B")
        assert store.count() == 2


class TestVectorStoreIsStale:
    def test_stale_when_missing(self, store: VectorStore) -> None:
        assert store.is_stale("nonexistent", "anyhash") is True

    def test_stale_when_hash_differs(self, store: VectorStore) -> None:
        store.upsert("paper-1", "paper", "Original content", title="P1")
        assert store.is_stale("paper-1", "different_hash") is True

    def test_not_stale_when_hash_matches(self, store: VectorStore) -> None:
        content = "Original content"
        import hashlib

        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        store.upsert("paper-1", "paper", content, title="P1")
        assert store.is_stale("paper-1", expected_hash) is False


class TestVectorStoreRebuild:
    def test_rebuild_fts_only(self, workspace: Workspace) -> None:
        """Rebuild without embedding function creates FTS entries only."""
        from xreadagent.schemas.wiki_pages import ConceptFrontmatter, PaperFrontmatter
        from xreadagent.wiki.pages import write_concept_page, write_paper_page

        empty_sections = {
            "Background": "Test background", "Challenges": "",
            "Solution": "", "Positioning": "", "Key Concepts": "",
            "Experiments": "", "Open Questions": "",
        }
        write_paper_page(
            workspace, "test-paper",
            PaperFrontmatter(title="Test", source="x", source_hash="h"),
            empty_sections,
        )
        concept_sections = {
            "Summary": "A concept about testing",
            "Related Papers": "", "Related Claims": "",
            "Open Questions": "",
        }
        write_concept_page(
            workspace, "test-concept",
            ConceptFrontmatter(title="Concept X"),
            concept_sections,
        )

        store = VectorStore.open(workspace)
        stats = store.rebuild(embed_fn=None)
        assert stats["papers"] == 1
        assert stats["concepts"] == 1
        assert stats["errors"] == 0
        assert store.count() == 2

        # FTS should find the paper.
        results = store.search_fts("testing", k=5)
        assert len(results) >= 1

        store.close()
