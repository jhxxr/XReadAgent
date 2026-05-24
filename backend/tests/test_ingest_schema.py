# SPDX-License-Identifier: AGPL-3.0-or-later
"""``IngestPlan`` schema validation."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from xreadagent.agents.ingest_schema import (
    IngestConceptTouch,
    IngestPaperPage,
    IngestPlan,
)
from xreadagent.schemas.entities import Claim, Entity, Relation, SourceRef, Task
from xreadagent.schemas.sources import Source
from xreadagent.schemas.wiki_pages import PaperFrontmatter
from xreadagent.wiki.distillation import DistillationPayload


def _minimal_source() -> Source:
    return Source(
        id="paper-x",
        title="Paper X",
        slug="paper-x-abc123",
        contentHash="abc123",
    )


def _minimal_paper_page() -> IngestPaperPage:
    return IngestPaperPage(
        slug="paper-x-abc123",
        frontmatter=PaperFrontmatter(
            title="Paper X",
            source="raw/x.pdf",
            source_hash="abc123",
        ),
        background="b",
        challenges="c",
        solution="s",
        positioning="p",
        key_concepts="- [[concepts/transformer]]",
        experiments="e",
        open_questions="oq",
    )


def test_ingest_plan_round_trips_through_json() -> None:
    plan = IngestPlan(
        paper=_minimal_paper_page(),
        concepts=[
            IngestConceptTouch(
                slug="transformer",
                canonical_name="Transformer",
                aliases=["xformer"],
                op="create",
                summary_section="Self-attention based architecture.",
                related_papers_addition=["paper-x-abc123"],
                related_claims_addition=["claim-1"],
            )
        ],
        distillation=DistillationPayload(
            source=_minimal_source(),
            entities=[Entity(id="ent-1", title="Transformer")],
            claims=[
                Claim(
                    id="claim-1",
                    title="Self-attention scales",
                    entityIds=["ent-1"],
                    sourceRefs=[SourceRef(sourceId="paper-x", pageStart=3)],
                )
            ],
            relations=[
                Relation(id="r-1", type="uses", fromId="ent-1", toId="ent-1")
            ],
            tasks=[Task(id="t-1", title="Find a faster attention variant")],
        ),
        log_subject="Paper X",
        notes=["model uncertain about table 3"],
    )

    raw = plan.model_dump_json()
    reloaded = IngestPlan.model_validate(json.loads(raw))
    assert reloaded == plan


def test_ingest_plan_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        IngestPlan.model_validate(
            {
                "paper": _minimal_paper_page().model_dump(mode="json"),
                "distillation": DistillationPayload(
                    source=_minimal_source()
                ).model_dump(mode="json"),
                "log_subject": "x",
                "extraneous": "nope",
            }
        )


def test_ingest_plan_rejects_invalid_op() -> None:
    with pytest.raises(ValidationError):
        IngestConceptTouch(
            slug="transformer",
            canonical_name="Transformer",
            op="upsert",  # type: ignore[arg-type]
            summary_section="x",
        )


def test_ingest_plan_requires_paper() -> None:
    with pytest.raises(ValidationError):
        IngestPlan.model_validate(
            {
                "distillation": DistillationPayload(
                    source=_minimal_source()
                ).model_dump(mode="json"),
                "log_subject": "x",
            }
        )
