# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared ``merge_concept_into_page`` helper exercised directly.

Both ``apply_plan`` (ingest) and ``apply_crystallize`` route through this
helper. Tests assert the helper handles the create-and-merge cases with
correct alias dedup, heading flexibility, and section preservation.
"""

from __future__ import annotations

from pathlib import Path

from xreadagent.agents._merge import merge_concept_into_page
from xreadagent.schemas.wiki_pages import ConceptFrontmatter
from xreadagent.wiki.pages import (
    CONCEPT_SECTIONS,
    read_page_frontmatter,
    write_concept_page,
)
from xreadagent.wiki.workspace import Workspace


def _workspace(tmp_path: Path) -> Workspace:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    return workspace


def test_merge_into_new_concept_creates_page(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    path = merge_concept_into_page(
        workspace,
        "transformer",
        canonical_name="Transformer",
        aliases_to_add=["xformer"],
        summary_addition="Self-attention model.",
        summary_section_heading="From paper-foo",
        related_papers_to_add=["paper-foo"],
        related_claims_to_add=["claim-1"],
    )
    assert path.exists()
    body = path.read_text(encoding="utf-8")
    for section in CONCEPT_SECTIONS:
        assert f"## {section}" in body
    assert "### From paper-foo" in body
    assert "Self-attention model." in body
    assert "[[papers/paper-foo|paper-foo]]" in body
    assert "- claim-1" in body
    fm = read_page_frontmatter(path)
    assert fm["title"] == "Transformer"
    assert fm["aliases"] == ["xformer"]


def test_merge_preserves_existing_content_and_dedupes_aliases(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer", aliases=["xformer"]),
        {"Summary": "Original summary."},
    )

    merge_concept_into_page(
        workspace,
        "transformer",
        canonical_name="Transformer",
        aliases_to_add=["xformer", "self-attention-model"],
        summary_addition="Additional context.",
        summary_section_heading="From paper-bar",
        related_papers_to_add=["paper-bar"],
        related_claims_to_add=["claim-99"],
    )

    body = (workspace.concepts_dir / "transformer.md").read_text(encoding="utf-8")
    assert "Original summary." in body
    assert "Additional context." in body
    assert "### From paper-bar" in body
    fm = read_page_frontmatter(workspace.concepts_dir / "transformer.md")
    assert fm["aliases"] == ["xformer", "self-attention-model"]


def test_merge_dedupes_bullets(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer"),
        {
            "Summary": "Summary.",
            "Related Papers": "- [[papers/p1|p1]]",
            "Related Claims": "- claim-existing",
        },
    )

    merge_concept_into_page(
        workspace,
        "transformer",
        canonical_name="Transformer",
        aliases_to_add=[],
        summary_addition="x",
        summary_section_heading="From paper-bar",
        related_papers_to_add=["p1", "p2"],
        related_claims_to_add=["claim-existing", "claim-new"],
    )

    body = (workspace.concepts_dir / "transformer.md").read_text(encoding="utf-8")
    # Existing entries kept exactly once.
    assert body.count("[[papers/p1|p1]]") == 1
    assert body.count("- claim-existing") == 1
    # New entries appended.
    assert "[[papers/p2|p2]]" in body
    assert "- claim-new" in body


def test_merge_with_empty_summary_does_not_add_heading(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer"),
        {"Summary": "Existing summary."},
    )

    merge_concept_into_page(
        workspace,
        "transformer",
        canonical_name="Transformer",
        aliases_to_add=[],
        summary_addition="   ",  # whitespace only
        summary_section_heading="From whatever",
        related_papers_to_add=[],
        related_claims_to_add=[],
    )

    body = (workspace.concepts_dir / "transformer.md").read_text(encoding="utf-8")
    assert "### From whatever" not in body
    assert "Existing summary." in body


def test_merge_preserves_existing_title_when_canonical_name_omitted(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer (the original)"),
        {"Summary": "s"},
    )

    merge_concept_into_page(
        workspace,
        "transformer",
        canonical_name=None,
        aliases_to_add=["new-alias"],
        summary_addition="more context",
        summary_section_heading="From X",
        related_papers_to_add=[],
        related_claims_to_add=[],
    )

    fm = read_page_frontmatter(workspace.concepts_dir / "transformer.md")
    assert fm["title"] == "Transformer (the original)"
    assert "new-alias" in fm["aliases"]  # type: ignore[operator]


def test_merge_falls_back_to_slug_when_no_title_anywhere(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    path = merge_concept_into_page(
        workspace,
        "new-concept",
        canonical_name=None,
        aliases_to_add=[],
        summary_addition="x",
        summary_section_heading="From Y",
        related_papers_to_add=[],
        related_claims_to_add=[],
    )
    fm = read_page_frontmatter(path)
    assert fm["title"] == "new-concept"


def test_merge_handles_blank_heading(tmp_path: Path) -> None:
    """A blank summary heading falls back to ``Update`` so we don't render ``### ``."""
    workspace = _workspace(tmp_path)
    path = merge_concept_into_page(
        workspace,
        "x",
        canonical_name="X",
        aliases_to_add=[],
        summary_addition="some content",
        summary_section_heading="   ",
        related_papers_to_add=[],
        related_claims_to_add=[],
    )
    body = path.read_text(encoding="utf-8")
    assert "### Update" in body
