# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the wiki read API endpoints.

These endpoints parse frontmatter + content from wiki markdown pages on
disk.  The tests build a real :class:`Workspace` with seed files and
exercise the FastAPI app directly — no LLM or agent stubs needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xreadagent.api.main import create_app
from xreadagent.schemas.sources import Source
from xreadagent.wiki.sources import SourcesIndex
from xreadagent.wiki.workspace import Workspace


def _seeded_workspace(tmp_path: Path) -> Workspace:
    """Create a workspace with sample papers, concepts, and queries."""
    workspace = Workspace.at(tmp_path / "ws")
    workspace.init_empty("Wiki API Test")
    workspace.ensure_layout()

    # Write a sample paper page.
    (workspace.papers_dir / "attention-aaa.md").write_text(
        "---\ntitle: Attention Is All You Need\nauthors:\n- Vaswani\n- Shazeer\nyear: 2017\n"
        "source: raw/attention.pdf\nsource_hash: abc123\n---\n"
        "# Attention Is All You Need\n\n## Background\n\nDeep learning for NLP.\n\n"
        "## Challenges\n\nRNNs are slow.\n\n## Solution\n\nTransformer architecture.\n\n"
        "## Positioning\n\nFoundational.\n\n## Key Concepts\n\nSelf-attention.\n\n"
        "## Experiments\n\nWMT translation.\n\n## Open Questions\n\nScaling laws.\n",
        encoding="utf-8",
    )
    sources = SourcesIndex.load(workspace)
    sources.add_or_update(
        Source(
            id="attention-aaa",
            title="Attention Is All You Need",
            slug="attention-aaa",
            kind="pdf",
            sourcePath="raw/_processed/attention-aaa.pdf",
            contentHash="abc123",
            ingestedAt="2026-05-27T00:00:00Z",
            extractPath="extracts/attention-aaa.md",
        )
    )
    sources.save()

    # Write a sample concept page.
    (workspace.concepts_dir / "self-attention.md").write_text(
        "---\ntitle: Self-Attention\naliases:\n- scaled dot-product attention\ntype: concept\n---\n"
        "# Self-Attention\n\n## Summary\n\nA mechanism that relates different positions.\n\n"
        "## Related Papers\n\n- [[papers/attention-aaa|Attention]]\n\n"
        "## Related Claims\n\n_(not yet filled)_\n\n## Open Questions\n\n_(not yet filled)_\n",
        encoding="utf-8",
    )

    # Write a sample query page.
    topic_dir = workspace.queries_dir / "transformers"
    topic_dir.mkdir(parents=True, exist_ok=True)
    (topic_dir / "2026-05-27-what-is-attention.md").write_text(
        "---\nquestion: What is attention?\ndate: '2026-05-27'\nlayers_used:\n- paper\n"
        "sources_cited:\n- papers/attention-aaa\n---\n"
        "# What is attention?\n\n## Question\n\nWhat is attention?\n\n"
        "## Answer\n\nAttention is a mechanism.\n\n## Sources\n\n"
        "- [[papers/attention-aaa]]\n",
        encoding="utf-8",
    )

    return workspace


# ---------------------------------------------------------------------------
# GET /api/wiki/papers
# ---------------------------------------------------------------------------


def test_papers_list_returns_all_papers(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/papers", params={"workspacePath": str(workspace.root)}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["slug"] == "attention-aaa"
    assert body[0]["title"] == "Attention Is All You Need"
    assert body[0]["authors"] == ["Vaswani", "Shazeer"]
    assert body[0]["year"] == 2017
    assert body[0]["sourcePath"] == "raw/_processed/attention-aaa.pdf"
    assert body[0]["sourceKind"] == "pdf"


def test_papers_list_returns_empty_for_no_papers(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path / "empty")
    workspace.init_empty("Empty")
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/papers", params={"workspacePath": str(workspace.root)}
    )
    assert response.status_code == 200
    assert response.json() == []


def test_papers_list_rejects_missing_workspace(tmp_path: Path) -> None:
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/papers",
        params={"workspacePath": str(tmp_path / "nonexistent")},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/wiki/papers/{slug}
# ---------------------------------------------------------------------------


def test_paper_detail_returns_content_and_frontmatter(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/papers/attention-aaa",
        params={"workspacePath": str(workspace.root)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["slug"] == "attention-aaa"
    assert "Transformer architecture" in body["content"]
    assert body["frontmatter"]["title"] == "Attention Is All You Need"
    assert body["frontmatter"]["year"] == 2017
    assert body["sourcePath"] == "raw/_processed/attention-aaa.pdf"
    assert body["sourceKind"] == "pdf"


def test_paper_detail_returns_404_for_missing_slug(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/papers/nonexistent",
        params={"workspacePath": str(workspace.root)},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/wiki/concepts
# ---------------------------------------------------------------------------


def test_concepts_list_returns_all_concepts(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/concepts", params={"workspacePath": str(workspace.root)}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["slug"] == "self-attention"
    assert body[0]["title"] == "Self-Attention"
    assert body[0]["aliases"] == ["scaled dot-product attention"]
    assert body[0]["paperCount"] == 1


# ---------------------------------------------------------------------------
# GET /api/wiki/concepts/{slug}
# ---------------------------------------------------------------------------


def test_concept_detail_returns_content_and_frontmatter(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/concepts/self-attention",
        params={"workspacePath": str(workspace.root)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["slug"] == "self-attention"
    assert "relates different positions" in body["content"]
    assert body["frontmatter"]["title"] == "Self-Attention"


def test_concept_detail_returns_404_for_missing_slug(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/concepts/nonexistent",
        params={"workspacePath": str(workspace.root)},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/wiki/queries
# ---------------------------------------------------------------------------


def test_queries_list_returns_all_queries(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/queries", params={"workspacePath": str(workspace.root)}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "transformers/2026-05-27-what-is-attention"
    assert body[0]["question"] == "What is attention?"
    assert body[0]["topic"] == "transformers"


# ---------------------------------------------------------------------------
# GET /api/wiki/queries/{topic}/{slug}
# ---------------------------------------------------------------------------


def test_query_detail_returns_content_and_frontmatter(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/queries/transformers/2026-05-27-what-is-attention",
        params={"workspacePath": str(workspace.root)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["slug"] == "transformers/2026-05-27-what-is-attention"
    assert "Attention is a mechanism" in body["content"]
    assert body["frontmatter"]["question"] == "What is attention?"


def test_query_detail_returns_404_for_missing_query(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/queries/transformers/nonexistent",
        params={"workspacePath": str(workspace.root)},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/wiki/index
# ---------------------------------------------------------------------------


def test_index_returns_content(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/index", params={"workspacePath": str(workspace.root)}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "content" in body
    assert isinstance(body["content"], str)


# ---------------------------------------------------------------------------
# GET /api/wiki/overview
# ---------------------------------------------------------------------------


def test_overview_returns_content(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/wiki/overview", params={"workspacePath": str(workspace.root)}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "content" in body


# Suppress accidental unused-import flake.
_ = pytest
