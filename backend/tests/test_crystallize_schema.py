# SPDX-License-Identifier: AGPL-3.0-or-later
"""Strict-mode validation for ``CrystallizePlan`` and its sub-models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from xreadagent.agents.crystallize_schema import (
    CrystallizeConceptPatch,
    CrystallizePaperPatch,
    CrystallizePlan,
)


def test_paper_patch_rejects_unknown_section() -> None:
    with pytest.raises(ValidationError):
        CrystallizePaperPatch(
            paper_slug="x",
            section="conclusion",  # type: ignore[arg-type]
            op="append",
            new_content="foo",
        )


def test_paper_patch_rejects_unknown_op() -> None:
    with pytest.raises(ValidationError):
        CrystallizePaperPatch(
            paper_slug="x",
            section="background",
            op="overwrite",  # type: ignore[arg-type]
            new_content="foo",
        )


def test_paper_patch_accepts_all_valid_sections() -> None:
    for section in (
        "background",
        "challenges",
        "solution",
        "positioning",
        "key_concepts",
        "experiments",
        "open_questions",
    ):
        patch = CrystallizePaperPatch(
            paper_slug="x",
            section=section,
            op="append",
            new_content="content",
        )
        assert patch.section == section


def test_concept_patch_rejects_unknown_op() -> None:
    with pytest.raises(ValidationError):
        CrystallizeConceptPatch(
            concept_slug="x",
            op="replace",  # type: ignore[arg-type]
        )


def test_concept_patch_defaults_are_safe() -> None:
    patch = CrystallizeConceptPatch(concept_slug="x", op="create")
    assert patch.canonical_name is None
    assert patch.aliases_to_add == []
    assert patch.summary_addition == ""
    assert patch.related_papers_to_add == []
    assert patch.related_claims_to_add == []


def test_plan_strict_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CrystallizePlan.model_validate(
            {
                "query_archive_path": "wiki/queries/general/2026-05-22-q.md",
                "paper_patches": [],
                "concept_patches": [],
                "log_subject": "subject",
                "rationale": "why",
                "extra_field": "not allowed",
            }
        )


def test_plan_round_trip_json() -> None:
    original = CrystallizePlan(
        query_archive_path="wiki/queries/general/2026-05-22-q.md",
        paper_patches=[
            CrystallizePaperPatch(
                paper_slug="alpha-aaa",
                section="open_questions",
                op="append",
                new_content="Does X imply Y?",
            )
        ],
        concept_patches=[
            CrystallizeConceptPatch(
                concept_slug="transformer",
                op="merge",
                aliases_to_add=["xformer"],
                summary_addition="New insight.",
                related_papers_to_add=["alpha-aaa"],
            )
        ],
        log_subject="Crystallize: transformer insight",
        rationale="Promoted from query 2026-05-22-q.md",
    )
    raw = original.model_dump_json()
    restored = CrystallizePlan.model_validate_json(raw)
    assert restored == original


def test_plan_accepts_empty_patches() -> None:
    """All-empty plan is a valid signal that no promotion is warranted."""
    plan = CrystallizePlan(
        query_archive_path="wiki/queries/g/2026-05-22-q.md",
        paper_patches=[],
        concept_patches=[],
        log_subject="empty",
        rationale="confidence was low",
    )
    assert plan.paper_patches == []
    assert plan.concept_patches == []
