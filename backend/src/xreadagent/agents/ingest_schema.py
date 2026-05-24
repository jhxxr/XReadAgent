# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured-output contract for one ingest pass.

The LLM emits exactly one ``IngestPlan`` per paper. The agent code (see
``ingest.apply_plan``) is what actually writes to disk — keeping the LLM's
output pure data makes the apply step replayable and unit-testable without an
LLM in the loop.

Per ``plan.md`` §2.3, an ingest touches 10–15 wiki pages: one paper page, a
few concept pages, the index, and the log. ``IngestPlan`` is shaped to cover
each of those edits in a single structured response.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from xreadagent.schemas.wiki_pages import PaperFrontmatter
from xreadagent.wiki.distillation import DistillationPayload


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class IngestPaperPage(_Strict):
    """The single ``wiki/papers/{slug}.md`` write for this ingest.

    Section bodies are markdown — wikilinks like ``[[concepts/transformer]]``
    are expected where the LLM cross-references concept pages.
    """

    slug: str
    frontmatter: PaperFrontmatter
    background: str
    challenges: str
    solution: str
    positioning: str
    key_concepts: str
    experiments: str
    open_questions: str


class IngestConceptTouch(_Strict):
    """One update to a concept page — create-new or merge-into-existing.

    ``op = "merge"`` is the disambiguation discipline from
    ``research/llm-wiki-prior-art.md`` § "Entity disambiguation": when the LLM
    sees that ``concepts/{slug}.md`` already exists, it appends a contribution
    section under the existing page rather than replacing it.
    """

    slug: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    op: Literal["create", "merge"]
    summary_section: str
    related_papers_addition: list[str] = Field(default_factory=list)
    related_claims_addition: list[str] = Field(default_factory=list)


class IngestPlan(_Strict):
    """Complete structured-output contract for one ingest."""

    paper: IngestPaperPage
    concepts: list[IngestConceptTouch] = Field(default_factory=list)
    distillation: DistillationPayload
    log_subject: str
    notes: list[str] = Field(default_factory=list)
