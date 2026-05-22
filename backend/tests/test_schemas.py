# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pydantic schema strictness tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from xreadagent.schemas import (
    Claim,
    ConceptFrontmatter,
    Entity,
    PaperFrontmatter,
    QueryFrontmatter,
    Relation,
    Source,
    SourceRef,
    SourcesManifest,
    Task,
)


def test_entity_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Entity(id="e1", title="Transformer", surprise="nope")  # type: ignore[call-arg]


def test_entity_requires_id_and_title() -> None:
    with pytest.raises(ValidationError):
        Entity()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Entity(id="e1")  # type: ignore[call-arg]


def test_claim_strict_type_coercion() -> None:
    # Strict mode forbids string->int silent coercion.
    with pytest.raises(ValidationError):
        Claim(id="c1", title="x", confidence="0.9")  # type: ignore[arg-type]


def test_relation_basic() -> None:
    rel = Relation(id="r1", type="uses", fromId="a", toId="b")
    assert rel.type == "uses"
    assert rel.fromId == "a"
    assert rel.toId == "b"


def test_task_basic() -> None:
    task = Task(id="t1", title="open question")
    assert task.title == "open question"
    assert task.sourceRefs == []


def test_source_ref_defaults() -> None:
    ref = SourceRef(sourceId="src-1")
    assert ref.pageStart == 0
    assert ref.pageEnd == 0
    assert ref.excerpt == ""


def test_source_manifest_round_trip() -> None:
    source = Source(
        id="src-1",
        title="A Paper",
        slug="a-paper-abc123def456",
        contentHash="deadbeef",
    )
    manifest = SourcesManifest(sources=[source])
    assert manifest.sources[0].slug == "a-paper-abc123def456"


def test_paper_frontmatter_defaults() -> None:
    page = PaperFrontmatter(
        title="A Paper",
        source="raw/a-paper.pdf",
        source_hash="abc",
    )
    assert page.page_type == "paper"
    assert page.reliability == "medium"
    assert page.authors == []


def test_paper_frontmatter_rejects_unknown_reliability() -> None:
    with pytest.raises(ValidationError):
        PaperFrontmatter(
            title="A Paper",
            source="raw/a.pdf",
            source_hash="abc",
            reliability="bogus",  # type: ignore[arg-type]
        )


def test_concept_frontmatter_aliases() -> None:
    page = ConceptFrontmatter(title="Transformer", aliases=["xformer"])
    assert page.aliases == ["xformer"]
    assert page.page_type == "concept"


def test_query_frontmatter_layers() -> None:
    page = QueryFrontmatter(
        question="what is RLHF?",
        date="2026-05-22",
        layers_used=["L1", "L2"],
        sources_cited=["wiki/papers/instructgpt-...md"],
    )
    assert page.layers_used == ["L1", "L2"]
    assert page.page_type == "query"


def test_query_frontmatter_rejects_extra() -> None:
    with pytest.raises(ValidationError):
        QueryFrontmatter(
            question="?",
            date="2026-05-22",
            extra="nope",  # type: ignore[call-arg]
        )
