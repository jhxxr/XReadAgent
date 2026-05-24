# SPDX-License-Identifier: AGPL-3.0-or-later
"""``apply_crystallize`` writes the patches described by a ``CrystallizePlan``."""

from __future__ import annotations

import json
from pathlib import Path

from xreadagent.agents.crystallize import apply_crystallize
from xreadagent.agents.crystallize_schema import (
    CrystallizeConceptPatch,
    CrystallizePaperPatch,
    CrystallizePlan,
)
from xreadagent.schemas.wiki_pages import ConceptFrontmatter, PaperFrontmatter, QueryFrontmatter
from xreadagent.wiki.pages import (
    read_page_frontmatter,
    write_concept_page,
    write_paper_page,
    write_query_page,
)
from xreadagent.wiki.workspace import Workspace


def _seed(tmp_path: Path) -> tuple[Workspace, str]:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    write_paper_page(
        workspace,
        "alpha-aaa",
        PaperFrontmatter(title="Alpha", source="raw/a.pdf", source_hash="aaa"),
        {
            "Background": "alpha bg",
            "Challenges": "alpha c",
            "Solution": "alpha s",
            "Positioning": "alpha p",
            "Key Concepts": "- existing",
            "Experiments": "alpha exp",
            "Open Questions": "alpha oq",
        },
    )
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer", aliases=["xformer"]),
        {"Summary": "Original summary."},
    )
    archive_path = write_query_page(
        workspace,
        "rl",
        "2026-05-22",
        "ppo-vs-grpo",
        QueryFrontmatter(
            question="PPO vs GRPO?",
            date="2026-05-22",
            sources_cited=["papers/alpha-aaa.md"],
        ),
        {
            "Question": "PPO vs GRPO?",
            "Answer": "GRPO drops the value head.",
            "Sources": "- [[papers/alpha-aaa.md]] — _high_: drops the value head",
        },
    )
    rel = archive_path.relative_to(workspace.root).as_posix()
    return workspace, rel


def test_apply_crystallize_appends_to_paper_section(tmp_path: Path) -> None:
    workspace, archive = _seed(tmp_path)
    plan = CrystallizePlan(
        query_archive_path=archive,
        paper_patches=[
            CrystallizePaperPatch(
                paper_slug="alpha-aaa",
                section="open_questions",
                op="append",
                new_content="What about GRPO vs PPO?",
            )
        ],
        concept_patches=[],
        log_subject="GRPO vs PPO",
        rationale="from 2026-05-22 query",
    )
    result = apply_crystallize(workspace, plan)
    paper_body = (workspace.papers_dir / "alpha-aaa.md").read_text(encoding="utf-8")
    assert "alpha oq" in paper_body  # original preserved
    assert "What about GRPO vs PPO?" in paper_body
    assert "wiki/papers/alpha-aaa.md" in result.files_touched


def test_apply_crystallize_replaces_subsection(tmp_path: Path) -> None:
    workspace, archive = _seed(tmp_path)
    # Seed the target subsection so replace has something to target.
    paper_path = workspace.papers_dir / "alpha-aaa.md"
    current = paper_path.read_text(encoding="utf-8")
    seeded = current.replace(
        "alpha s",
        "alpha s\n\n### Notes\n\nOriginal notes — to replace.",
    )
    paper_path.write_text(seeded, encoding="utf-8")

    plan = CrystallizePlan(
        query_archive_path=archive,
        paper_patches=[
            CrystallizePaperPatch(
                paper_slug="alpha-aaa",
                section="solution",
                op="replace_subsection",
                subsection_heading="Notes",
                new_content="Replaced notes.",
            )
        ],
        concept_patches=[],
        log_subject="replace notes",
        rationale="r",
    )
    apply_crystallize(workspace, plan)
    body = paper_path.read_text(encoding="utf-8")
    assert "Original notes" not in body
    assert "Replaced notes." in body
    # Other sections untouched.
    assert "alpha bg" in body
    assert "alpha oq" in body


def test_apply_crystallize_merges_existing_concept(tmp_path: Path) -> None:
    workspace, archive = _seed(tmp_path)
    plan = CrystallizePlan(
        query_archive_path=archive,
        paper_patches=[],
        concept_patches=[
            CrystallizeConceptPatch(
                concept_slug="transformer",
                op="merge",
                aliases_to_add=["xformer", "self-attention-model"],
                summary_addition="Promoted insight from query.",
                related_papers_to_add=["alpha-aaa"],
                related_claims_to_add=["claim-99"],
            )
        ],
        log_subject="merge transformer insight",
        rationale="r",
    )
    apply_crystallize(workspace, plan)
    body = (workspace.concepts_dir / "transformer.md").read_text(encoding="utf-8")
    assert "Original summary." in body
    assert "Promoted insight from query." in body
    assert "### From query: rl" in body
    fm = read_page_frontmatter(workspace.concepts_dir / "transformer.md")
    # Aliases deduped against the existing "xformer".
    assert fm["aliases"] == ["xformer", "self-attention-model"]
    assert "[[papers/alpha-aaa|alpha-aaa]]" in body
    assert "- claim-99" in body


def test_apply_crystallize_creates_new_concept(tmp_path: Path) -> None:
    workspace, archive = _seed(tmp_path)
    plan = CrystallizePlan(
        query_archive_path=archive,
        paper_patches=[],
        concept_patches=[
            CrystallizeConceptPatch(
                concept_slug="grpo",
                op="create",
                canonical_name="Group Relative Policy Optimization",
                aliases_to_add=["GRPO"],
                summary_addition="GRPO drops the value head.",
                related_papers_to_add=["alpha-aaa"],
            )
        ],
        log_subject="create grpo",
        rationale="r",
    )
    apply_crystallize(workspace, plan)
    path = workspace.concepts_dir / "grpo.md"
    assert path.exists()
    body = path.read_text(encoding="utf-8")
    assert "GRPO drops the value head." in body
    fm = read_page_frontmatter(path)
    assert fm["title"] == "Group Relative Policy Optimization"
    assert fm["aliases"] == ["GRPO"]


def test_apply_crystallize_regenerates_index(tmp_path: Path) -> None:
    workspace, archive = _seed(tmp_path)
    plan = CrystallizePlan(
        query_archive_path=archive,
        paper_patches=[],
        concept_patches=[
            CrystallizeConceptPatch(
                concept_slug="grpo",
                op="create",
                canonical_name="GRPO",
                summary_addition="x",
            )
        ],
        log_subject="grpo",
        rationale="r",
    )
    apply_crystallize(workspace, plan)
    index = workspace.index_md_path.read_text(encoding="utf-8")
    assert "[[concepts/grpo|" in index


def test_apply_crystallize_appends_log_and_conversation(tmp_path: Path) -> None:
    workspace, archive = _seed(tmp_path)
    plan = CrystallizePlan(
        query_archive_path=archive,
        paper_patches=[
            CrystallizePaperPatch(
                paper_slug="alpha-aaa",
                section="open_questions",
                op="append",
                new_content="another oq",
            )
        ],
        concept_patches=[],
        log_subject="alpha-oq-update",
        rationale="r",
    )
    apply_crystallize(workspace, plan)

    log_body = workspace.log_md_path.read_text(encoding="utf-8")
    assert "] crystallize | alpha-oq-update" in log_body

    conv_lines = workspace.conversation_log_path.read_text(encoding="utf-8").splitlines()
    assert conv_lines
    row = json.loads(conv_lines[-1])
    assert row["event"] == "crystallize"
    assert row["query_archive_path"] == archive
    assert row["log_subject"] == "alpha-oq-update"
    assert row["paper_patches"][0]["paper_slug"] == "alpha-aaa"


def test_apply_crystallize_missing_paper_reports_skip(tmp_path: Path) -> None:
    workspace, archive = _seed(tmp_path)
    plan = CrystallizePlan(
        query_archive_path=archive,
        paper_patches=[
            CrystallizePaperPatch(
                paper_slug="does-not-exist",
                section="background",
                op="append",
                new_content="x",
            )
        ],
        concept_patches=[],
        log_subject="missing-paper",
        rationale="r",
    )
    result = apply_crystallize(workspace, plan)
    # Touched list flags the missing target so callers can surface the failure.
    assert any("[missing]" in entry for entry in result.files_touched)


def test_apply_crystallize_query_archive_unchanged(tmp_path: Path) -> None:
    """The source query archive is NEVER modified by crystallize."""
    workspace, archive = _seed(tmp_path)
    archive_path = workspace.root / archive
    before = archive_path.read_bytes()

    plan = CrystallizePlan(
        query_archive_path=archive,
        paper_patches=[
            CrystallizePaperPatch(
                paper_slug="alpha-aaa",
                section="background",
                op="append",
                new_content="extra bg",
            )
        ],
        concept_patches=[],
        log_subject="r",
        rationale="r",
    )
    apply_crystallize(workspace, plan)
    after = archive_path.read_bytes()
    assert before == after


def test_apply_crystallize_empty_plan_skips_index_regen(tmp_path: Path) -> None:
    """All-empty plan still logs but does not regenerate index."""
    workspace, archive = _seed(tmp_path)
    index_before = workspace.index_md_path.read_text(encoding="utf-8")
    plan = CrystallizePlan(
        query_archive_path=archive,
        paper_patches=[],
        concept_patches=[],
        log_subject="no-op",
        rationale="confidence was low; skipping promotion",
    )
    apply_crystallize(workspace, plan)
    # Index unchanged.
    assert workspace.index_md_path.read_text(encoding="utf-8") == index_before
    # Log appended.
    log_body = workspace.log_md_path.read_text(encoding="utf-8")
    assert "no-op" in log_body
