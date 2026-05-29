# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vector store for wiki pages -- sqlite-vec + FTS5.

Manages ``{workspace}/state/vec.sqlite`` which holds:

- ``vec_pages`` -- vec0 virtual table for 384-d float embeddings keyed by page slug.
- ``wiki_pages`` -- metadata table mapping rowid -> slug + page_type + content_hash.
- ``fts_pages`` -- FTS5 full-text index over page titles + content.

The vec.sqlite file is a **regenerable cache** -- ``state/sources.json`` remains
the canonical source of truth. If vec.sqlite is deleted or corrupted it can be
rebuilt from the wiki pages on disk via :meth:`VectorStore.rebuild`.

Single-writer: only one process should write to vec.sqlite at a time
(Phase 4 single-sidecar assumption).
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from xreadagent.wiki.workspace import Workspace

_logger = logging.getLogger(__name__)

_EMBEDDING_DIM: Final[int] = 384


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _load_vec_extension(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec extension into ``conn``."""
    import sqlite_vec  # lazy -- not installed in all environments

    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def _open_vec_sqlite(path: Path) -> sqlite3.Connection:
    """Open (or create) a vec.sqlite database with the required tables."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        _load_vec_extension(conn)
    except ImportError:
        conn.close()
        raise

    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS vec_pages USING vec0("
        "  page_slug TEXT PRIMARY KEY,"
        "  embedding float[384]"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS wiki_pages ("
        "  slug TEXT PRIMARY KEY,"
        "  page_type TEXT NOT NULL,"
        "  title TEXT NOT NULL DEFAULT '',"
        "  content_hash TEXT NOT NULL,"
        "  created_at TEXT NOT NULL,"
        "  updated_at TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS fts_pages USING fts5("
        "  page_slug,"
        "  title,"
        "  content"
        ")"
    )
    conn.commit()
    return conn


class VectorStore:
    """Manages ``{workspace}/state/vec.sqlite``: embeddings + FTS5 for wiki pages.

    Parameters
    ----------
    workspace
        The workspace whose ``state/vec.sqlite`` to manage.
    embedding_dim
        Vector dimension. Must match the embedder model output.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        embedding_dim: int = _EMBEDDING_DIM,
    ) -> None:
        self._workspace = workspace
        self._embedding_dim = embedding_dim
        self._conn: sqlite3.Connection | None = None

    @classmethod
    def open(cls, workspace: Workspace, *, embedding_dim: int = _EMBEDDING_DIM) -> VectorStore:
        """Open an existing vec.sqlite or create a new one.

        Raises :class:`ImportError` if sqlite-vec is not installed.
        """
        store = cls(workspace, embedding_dim=embedding_dim)
        store._connect()
        return store

    def _connect(self) -> sqlite3.Connection:
        """Open the database connection, creating the file if needed."""
        if self._conn is not None:
            return self._conn
        self._conn = _open_vec_sqlite(self._workspace.vec_sqlite_path)
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._connect()
        assert self._conn is not None
        return self._conn

    def upsert(
        self,
        slug: str,
        page_type: str,
        text: str,
        embedding: list[float] | None = None,
        title: str = "",
    ) -> None:
        """Insert or update a page's vector + FTS entry.

        Parameters
        ----------
        slug
            Wiki page slug (e.g. ``"attention-is-all-you-need-a1b2c3d4e5f6"``).
        page_type
            One of ``"paper"``, ``"concept"``.
        text
            Full page body (markdown after frontmatter).
        embedding
            Pre-computed embedding vector. When ``None``, the FTS and metadata
            are upserted but no vector entry is created.
        title
            Page title for the FTS index and metadata.
        """
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        now = _utc_now_iso()

        # Check if the page already exists with the same content hash.
        existing = self.conn.execute(
            "SELECT content_hash FROM wiki_pages WHERE slug = ?", (slug,)
        ).fetchone()
        if existing and existing[0] == content_hash and embedding is not None:
            # Content unchanged and we have an embedding -- nothing to do.
            return

        # Delete stale entries first (upsert = delete + insert for vec0).
        self._delete_internal(slug)

        # Insert metadata.
        self.conn.execute(
            "INSERT INTO wiki_pages (slug, page_type, title, content_hash, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (slug, page_type, title, content_hash, now, now),
        )

        # Insert vector if available.
        if embedding is not None and len(embedding) == self._embedding_dim:
            blob = struct.pack(f"{len(embedding)}f", *embedding)
            self.conn.execute(
                "INSERT INTO vec_pages (page_slug, embedding) VALUES (?, ?)",
                (slug, blob),
            )

        # Insert FTS entry.
        self.conn.execute(
            "INSERT INTO fts_pages (page_slug, title, content) VALUES (?, ?, ?)",
            (slug, title, text),
        )

        self.conn.commit()

    def delete(self, slug: str) -> None:
        """Remove a page's vector + FTS + metadata entries."""
        self._delete_internal(slug)
        self.conn.commit()

    def _delete_internal(self, slug: str) -> None:
        """Delete all entries for ``slug`` without committing."""
        self.conn.execute("DELETE FROM vec_pages WHERE page_slug = ?", (slug,))
        self.conn.execute("DELETE FROM wiki_pages WHERE slug = ?", (slug,))
        self.conn.execute("DELETE FROM fts_pages WHERE page_slug = ?", (slug,))

    def search_vector(self, query_embedding: list[float], *, k: int = 10) -> list[dict[str, Any]]:
        """KNN search against vec0. Returns ``[{slug, distance}, ...]``.

        Note: sqlite-vec KNN requires ``k = ?`` parameter, not bare ``LIMIT``.
        """
        if len(query_embedding) != self._embedding_dim:
            _logger.warning(
                "query embedding dimension %d != expected %d, skipping vector search",
                len(query_embedding),
                self._embedding_dim,
            )
            return []

        blob = struct.pack(f"{len(query_embedding)}f", *query_embedding)
        cursor = self.conn.execute(
            "SELECT page_slug, distance FROM vec_pages WHERE embedding MATCH ? AND k = ?",
            (blob, k),
        )
        results: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            results.append({"slug": row[0], "distance": row[1]})
        return results

    def search_fts(self, query: str, *, k: int = 10) -> list[dict[str, Any]]:
        """FTS5 full-text search. Returns ``[{slug, title, rank}, ...]``."""
        if not query.strip():
            return []
        cursor = self.conn.execute(
            "SELECT page_slug, title, rank FROM fts_pages WHERE fts_pages MATCH ? "
            "ORDER BY rank LIMIT ?",
            (query, k),
        )
        results: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            results.append({"slug": row[0], "title": row[1], "rank": row[2]})
        return results

    def search_hybrid(
        self,
        query_embedding: list[float],
        query_text: str,
        *,
        k: int = 10,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """Hybrid search: vec0 KNN + FTS5 with Reciprocal Rank Fusion.

        Parameters
        ----------
        query_embedding
            Pre-computed embedding for the query text.
        query_text
            The raw query string for FTS5.
        k
            Number of results to return.
        rrf_k
            RRF smoothing constant (60 is standard).
        """
        vec_results = self.search_vector(query_embedding, k=k)
        fts_results = self.search_fts(query_text, k=k)

        # Build rank maps (1-indexed).
        vec_ranks: dict[str, int] = {}
        for rank, item in enumerate(vec_results, start=1):
            vec_ranks[item["slug"]] = rank

        fts_ranks: dict[str, int] = {}
        for rank, item in enumerate(fts_results, start=1):
            fts_ranks[item["slug"]] = rank

        # RRF merge.
        all_slugs = set(vec_ranks) | set(fts_ranks)
        rrf_scores: dict[str, float] = {}
        for slug in all_slugs:
            score = 0.0
            if slug in vec_ranks:
                score += 1.0 / (rrf_k + vec_ranks[slug])
            if slug in fts_ranks:
                score += 1.0 / (rrf_k + fts_ranks[slug])
            rrf_scores[slug] = score

        # Enrich with metadata.
        sorted_slugs = sorted(rrf_scores, key=lambda s: -rrf_scores[s])
        results: list[dict[str, Any]] = []
        for slug in sorted_slugs[:k]:
            meta = self.conn.execute(
                "SELECT page_type, title FROM wiki_pages WHERE slug = ?", (slug,)
            ).fetchone()
            page_type = meta[0] if meta else "unknown"
            title = meta[1] if meta else slug
            source_parts: list[str] = []
            if slug in vec_ranks:
                source_parts.append("vec")
            if slug in fts_ranks:
                source_parts.append("fts")
            results.append({
                "slug": slug,
                "title": title,
                "page_type": page_type,
                "score": rrf_scores[slug],
                "source": "+".join(source_parts),
                "vec_rank": vec_ranks.get(slug),
                "fts_rank": fts_ranks.get(slug),
            })
        return results

    def count(self) -> int:
        """Return the number of indexed pages."""
        row = self.conn.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()
        return row[0] if row else 0

    def is_stale(self, slug: str, content_hash: str) -> bool:
        """Return ``True`` if the stored content hash differs from ``content_hash``."""
        row = self.conn.execute(
            "SELECT content_hash FROM wiki_pages WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            return True
        return bool(row[0] != content_hash)

    def rebuild(self, embed_fn: Any = None) -> dict[str, int]:
        """Rebuild the entire index from wiki pages on disk.

        Deletes all existing entries and re-indexes every paper + concept page.
        Query archive pages are NOT indexed per the isolation rule.

        Parameters
        ----------
        embed_fn
            Optional callable ``embed_fn(text: str) -> list[float]``. When
            ``None``, only FTS entries are created (no vectors).

        Returns
        -------
        dict with keys ``"papers"``, ``"concepts"``, ``"errors"``.
        """
        from xreadagent.wiki.frontmatter_utils import read_page_content
        from xreadagent.wiki.pages import read_page_frontmatter

        # Clear all existing data.
        self.conn.execute("DELETE FROM vec_pages")
        self.conn.execute("DELETE FROM wiki_pages")
        self.conn.execute("INSERT INTO fts_pages (fts_pages) VALUES ('rebuild')")
        self.conn.commit()

        stats = {"papers": 0, "concepts": 0, "errors": 0}

        # Index paper pages.
        papers_dir = self._workspace.papers_dir
        if papers_dir.exists():
            for path in sorted(papers_dir.iterdir()):
                if not path.is_file() or path.suffix != ".md":
                    continue
                slug = path.stem
                try:
                    fm = read_page_frontmatter(path)
                    title = str(fm.get("title", slug)) if isinstance(fm, dict) else slug
                    content = read_page_content(path)
                    embedding = embed_fn(content) if embed_fn else None
                    self.upsert(slug, "paper", content, embedding=embedding, title=title)
                    stats["papers"] += 1
                except Exception as exc:
                    _logger.warning("failed to index paper %s: %s", slug, exc)
                    stats["errors"] += 1

        # Index concept pages.
        concepts_dir = self._workspace.concepts_dir
        if concepts_dir.exists():
            for path in sorted(concepts_dir.iterdir()):
                if not path.is_file() or path.suffix != ".md":
                    continue
                slug = path.stem
                try:
                    fm = read_page_frontmatter(path)
                    title = str(fm.get("title", slug)) if isinstance(fm, dict) else slug
                    content = read_page_content(path)
                    embedding = embed_fn(content) if embed_fn else None
                    self.upsert(slug, "concept", content, embedding=embedding, title=title)
                    stats["concepts"] += 1
                except Exception as exc:
                    _logger.warning("failed to index concept %s: %s", slug, exc)
                    stats["errors"] += 1

        return stats


__all__ = ["VectorStore"]
