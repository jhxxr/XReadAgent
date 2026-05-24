# SPDX-License-Identifier: AGPL-3.0-or-later
"""``regenerate_index`` / ``write_index`` determinism tests."""

from __future__ import annotations

from pathlib import Path

from xreadagent.schemas.wiki_pages import ConceptFrontmatter, PaperFrontmatter
from xreadagent.wiki.index_regen import regenerate_index, write_index
from xreadagent.wiki.pages import write_concept_page, write_paper_page
from xreadagent.wiki.workspace import Workspace


def _seed_workspace(tmp_path: Path) -> Workspace:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test Vault")

    write_paper_page(
        workspace,
        "alpha-paper-aaa",
        PaperFrontmatter(
            title="Alpha Paper",
            source="raw/alpha.pdf",
            source_hash="aaa",
        ),
        {"Background": "Alpha background"},
    )
    write_paper_page(
        workspace,
        "beta-paper-bbb",
        PaperFrontmatter(
            title="Beta Paper",
            source="raw/beta.pdf",
            source_hash="bbb",
        ),
        {},
    )
    write_paper_page(
        workspace,
        "gamma-paper-ccc",
        PaperFrontmatter(
            title="Gamma Paper",
            source="raw/gamma.pdf",
            source_hash="ccc",
        ),
        {},
    )

    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer"),
        {"Summary": "Self-attention based model"},
    )
    write_concept_page(
        workspace,
        "self-attention",
        ConceptFrontmatter(title="Self-Attention"),
        {},
    )
    return workspace


def test_regenerate_index_lists_papers_and_concepts(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path)
    body = regenerate_index(workspace)

    assert "# Test Vault" in body
    assert "## Documents" in body
    assert "## Concepts" in body
    assert "## Stats" in body

    # Documents appear alphabetically by slug.
    alpha_index = body.index("alpha-paper-aaa")
    beta_index = body.index("beta-paper-bbb")
    gamma_index = body.index("gamma-paper-ccc")
    assert alpha_index < beta_index < gamma_index

    # Stats reflect actual counts.
    assert "- documents: 3" in body
    assert "- concepts: 2" in body
    # No ingestedAt timestamp has been recorded yet by these unit tests.
    assert "- last_ingest_at: never" in body


def test_regenerate_index_is_deterministic(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path)
    first = regenerate_index(workspace)
    second = regenerate_index(workspace)
    assert first == second


def test_write_index_is_idempotent(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path)
    assert write_index(workspace) is True
    first_contents = workspace.index_md_path.read_text(encoding="utf-8")
    # Second call with unchanged inputs must not write again.
    assert write_index(workspace) is False
    assert workspace.index_md_path.read_text(encoding="utf-8") == first_contents


def test_regenerate_index_with_empty_workspace(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Empty")
    body = regenerate_index(workspace)
    assert "# Empty" in body
    assert "- documents: 0" in body
    assert "- concepts: 0" in body
