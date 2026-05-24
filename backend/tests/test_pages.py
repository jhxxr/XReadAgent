# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wiki page writer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from xreadagent.schemas.wiki_pages import (
    ConceptFrontmatter,
    PaperFrontmatter,
    QueryFrontmatter,
)
from xreadagent.wiki.pages import (
    CONCEPT_SECTIONS,
    PAPER_SECTIONS,
    QUERY_SECTIONS,
    read_page_frontmatter,
    write_concept_page,
    write_paper_page,
    write_query_page,
)
from xreadagent.wiki.workspace import Workspace


def _new_workspace(tmp_path: Path) -> Workspace:
    ws = Workspace.at(tmp_path)
    ws.init_empty("Test")
    return ws


def test_write_paper_page_emits_all_sections(tmp_path: Path) -> None:
    workspace = _new_workspace(tmp_path)
    fm = PaperFrontmatter(
        title="Attention Is All You Need",
        source="raw/attention.pdf",
        source_hash="abc12345",
        year=2017,
        authors=["Vaswani"],
        topics=["transformers"],
    )
    path = write_paper_page(
        workspace,
        "attention-is-all-you-need-abc",
        fm,
        {"Background": "Encoder-decoder eras predated Transformer."},
    )

    body = path.read_text(encoding="utf-8")
    for section in PAPER_SECTIONS:
        assert f"## {section}" in body
    assert "_(not yet filled)_" in body  # at least one section is empty
    assert "Encoder-decoder eras predated Transformer." in body
    # Frontmatter round-trips.
    fm_dict = read_page_frontmatter(path)
    assert fm_dict["title"] == "Attention Is All You Need"
    assert fm_dict["page_type"] == "paper"
    assert fm_dict["year"] == 2017


def test_write_concept_page_emits_all_sections(tmp_path: Path) -> None:
    workspace = _new_workspace(tmp_path)
    fm = ConceptFrontmatter(title="Transformer", aliases=["xformer"], type="architecture")
    path = write_concept_page(workspace, "transformer", fm, {"Summary": "Self-attention."})

    body = path.read_text(encoding="utf-8")
    for section in CONCEPT_SECTIONS:
        assert f"## {section}" in body
    fm_dict = read_page_frontmatter(path)
    assert fm_dict["aliases"] == ["xformer"]


def test_write_query_page_writes_under_topic_dir(tmp_path: Path) -> None:
    workspace = _new_workspace(tmp_path)
    fm = QueryFrontmatter(
        question="what is RLHF?",
        date="2026-05-22",
        layers_used=["L1"],
        sources_cited=["wiki/papers/instructgpt.md"],
    )
    path = write_query_page(
        workspace,
        "reinforcement-learning",
        "2026-05-22",
        "what-is-rlhf",
        fm,
        {"Answer": "Training language models with human preference signals."},
    )

    relative = path.relative_to(workspace.queries_dir).as_posix()
    assert relative == "reinforcement-learning/2026-05-22-what-is-rlhf.md"
    body = path.read_text(encoding="utf-8")
    for section in QUERY_SECTIONS:
        assert f"## {section}" in body


def test_query_page_requires_date(tmp_path: Path) -> None:
    workspace = _new_workspace(tmp_path)
    fm = QueryFrontmatter(question="?", date="ignored", layers_used=[], sources_cited=[])
    with pytest.raises(ValueError):
        write_query_page(workspace, "topic", "   ", "slug", fm, {})


def test_paper_page_overwrite_is_atomic(tmp_path: Path) -> None:
    workspace = _new_workspace(tmp_path)
    fm = PaperFrontmatter(title="t", source="s", source_hash="h")
    path = write_paper_page(workspace, "test-slug", fm, {"Background": "v1"})
    assert "v1" in path.read_text(encoding="utf-8")

    write_paper_page(workspace, "test-slug", fm, {"Background": "v2"})
    text = path.read_text(encoding="utf-8")
    assert "v2" in text
    assert "v1" not in text
    # No stale .tmp file left behind.
    sibling_tmp = path.with_name(f".{path.name}.tmp")
    assert not sibling_tmp.exists()


def test_read_page_frontmatter_returns_empty_for_no_frontmatter(tmp_path: Path) -> None:
    file_path = tmp_path / "plain.md"
    file_path.write_text("# Heading\n\nNo frontmatter.\n", encoding="utf-8")
    assert read_page_frontmatter(file_path) == {}
