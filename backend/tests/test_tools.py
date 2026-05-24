# SPDX-License-Identifier: AGPL-3.0-or-later
"""Workspace-introspection tool wrappers used by the ingest agent."""

from __future__ import annotations

from pathlib import Path

from xreadagent.agents.tools import build_ingest_tools
from xreadagent.schemas.wiki_pages import ConceptFrontmatter, PaperFrontmatter
from xreadagent.wiki.pages import write_concept_page, write_paper_page
from xreadagent.wiki.workspace import Workspace


def _seed(tmp_path: Path) -> Workspace:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    workspace.extracts_dir.mkdir(parents=True, exist_ok=True)
    (workspace.extracts_dir / "alpha-aaa.md").write_text(
        "# Alpha extract\n\nLorem ipsum.", encoding="utf-8"
    )
    write_paper_page(
        workspace,
        "alpha-aaa",
        PaperFrontmatter(title="Alpha Paper", source="raw/alpha.pdf", source_hash="aaa", year=2024),
        {"Background": "alpha background"},
    )
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer", aliases=["xformer"]),
        {"Summary": "self-attention model"},
    )
    return workspace


def test_read_extract_returns_markdown(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_ingest_tools(workspace)}
    out = tools["read_extract"].invoke({"slug": "alpha-aaa"})
    assert "Alpha extract" in out


def test_read_extract_returns_empty_for_unknown(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_ingest_tools(workspace)}
    assert tools["read_extract"].invoke({"slug": "nope"}) == ""


def test_list_papers_returns_paper_metadata(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_ingest_tools(workspace)}
    rows = tools["list_papers"].invoke({})
    assert len(rows) == 1
    assert rows[0]["slug"] == "alpha-aaa"
    assert rows[0]["title"] == "Alpha Paper"
    assert rows[0]["year"] == 2024


def test_list_concepts_returns_canonical_names_and_aliases(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_ingest_tools(workspace)}
    rows = tools["list_concepts"].invoke({})
    assert rows == [
        {"slug": "transformer", "canonical_name": "Transformer", "aliases": ["xformer"]}
    ]


def test_read_paper_returns_full_body(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_ingest_tools(workspace)}
    body = tools["read_paper"].invoke({"slug": "alpha-aaa"})
    assert "## Background" in body
    assert "alpha background" in body


def test_read_concept_returns_full_body(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_ingest_tools(workspace)}
    body = tools["read_concept"].invoke({"slug": "transformer"})
    assert "## Summary" in body
    assert "self-attention model" in body


def test_search_wiki_returns_hits_with_line_numbers(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_ingest_tools(workspace)}
    hits = tools["search_wiki"].invoke({"pattern": "alpha background"})
    assert hits
    assert all("path" in h and "line_no" in h and "match" in h for h in hits)


def test_search_wiki_empty_pattern_returns_empty(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_ingest_tools(workspace)}
    assert tools["search_wiki"].invoke({"pattern": "   "}) == []


def test_read_index_returns_index_md(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_ingest_tools(workspace)}
    body = tools["read_index"].invoke({})
    assert "# Test" in body
