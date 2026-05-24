# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured-output contract for one ``/crystallize`` proposal.

Crystallize is the user-invoked promotion of a query archive into the main
wiki (papers/, concepts/). The LLM proposes a ``CrystallizePlan`` of patches;
the user reviews; ``apply_crystallize`` applies the patches deterministically.

The agent NEVER writes the plan itself — the workflow is "propose, review,
apply" so the human stays in the loop (D4 in ``plan.md`` §11).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PaperSection = Literal[
    "background",
    "challenges",
    "solution",
    "positioning",
    "key_concepts",
    "experiments",
    "open_questions",
]

PaperPatchOp = Literal["append", "replace_subsection"]
ConceptPatchOp = Literal["create", "merge"]


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class CrystallizePaperPatch(_Strict):
    """One surgical edit to a ``wiki/papers/{slug}.md`` page.

    ``op = "append"`` is the conservative default — adds new content under the
    given section. ``op = "replace_subsection"`` targets a ``### {heading}``
    block inside the section and is only allowed when the new content is
    strictly better than what's there (anti-loss discipline).
    """

    paper_slug: str
    section: PaperSection
    op: PaperPatchOp
    subsection_heading: str | None = None
    new_content: str


class CrystallizeConceptPatch(_Strict):
    """One edit to a ``wiki/concepts/{slug}.md`` page — create-new or merge.

    Mirrors ``IngestConceptTouch`` (same merge discipline) so the shared
    ``merge_concept_into_page`` helper handles both call sites.
    """

    concept_slug: str
    op: ConceptPatchOp
    canonical_name: str | None = None
    aliases_to_add: list[str] = Field(default_factory=list)
    summary_addition: str = ""
    related_papers_to_add: list[str] = Field(default_factory=list)
    related_claims_to_add: list[str] = Field(default_factory=list)


class CrystallizePlan(_Strict):
    """Complete structured-output contract for one ``/crystallize``."""

    query_archive_path: str
    paper_patches: list[CrystallizePaperPatch] = Field(default_factory=list)
    concept_patches: list[CrystallizeConceptPatch] = Field(default_factory=list)
    log_subject: str
    rationale: str


__all__ = [
    "ConceptPatchOp",
    "CrystallizeConceptPatch",
    "CrystallizePaperPatch",
    "CrystallizePlan",
    "PaperPatchOp",
    "PaperSection",
]
