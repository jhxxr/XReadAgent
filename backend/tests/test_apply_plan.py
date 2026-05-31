# SPDX-License-Identifier: AGPL-3.0-or-later
"""``apply_plan`` writes the wiki state described by an ``IngestPlan``."""

from __future__ import annotations

import json
from pathlib import Path

from xreadagent.agents.ingest import apply_plan
from xreadagent.agents.ingest_schema import (
    IngestConceptTouch,
    IngestPaperPage,
    IngestPlan,
)
from xreadagent.schemas.entities import Claim, Entity, Relation, SourceRef, Task
from xreadagent.schemas.sources import Source
from xreadagent.schemas.wiki_pages import ConceptFrontmatter, PaperFrontmatter
from xreadagent.wiki.distillation import DistillationPayload, load_distillation
from xreadagent.wiki.pages import (
    CONCEPT_SECTIONS,
    PAPER_SECTIONS,
    read_page_frontmatter,
    write_concept_page,
)
from xreadagent.wiki.workspace import Workspace


def _source(slug: str = "attention-deadbeef") -> Source:
    return Source(
        id=slug,
        title="Attention Is All You Need",
        slug=slug,
        kind="pdf",
        contentHash="deadbeef",
    )


def _paper_page(slug: str) -> IngestPaperPage:
    return IngestPaperPage(
        slug=slug,
        frontmatter=PaperFrontmatter(
            title="Attention Is All You Need",
            source="raw/attention.pdf",
            source_hash="deadbeef",
            year=2017,
            authors=["Vaswani"],
            topics=["transformers"],
        ),
        background="RNNs / CNNs dominated.",
        challenges="Long-range dependencies cost O(N).",
        solution="Self-attention with multi-head.",
        positioning="Replaces recurrence.",
        key_concepts="- [[concepts/transformer|Transformer]]",
        experiments="WMT-14, BLEU 28.4.",
        open_questions="Positional encoding sensitivity.",
    )


def _distillation(slug: str) -> DistillationPayload:
    return DistillationPayload(
        source=_source(slug),
        entities=[
            Entity(id="ent-transformer", title="Transformer", summary="self-attention model"),
        ],
        claims=[
            Claim(
                id="claim-1",
                title="Transformer beats LSTM on WMT-14",
                entityIds=["ent-transformer"],
                sourceRefs=[SourceRef(sourceId=slug, pageStart=8, pageEnd=8)],
            )
        ],
        relations=[
            Relation(
                id="r-1",
                type="introduces",
                fromId="ent-transformer",
                toId="ent-transformer",
            )
        ],
        tasks=[Task(id="t-1", title="Why does positional encoding need sinusoids?")],
    )


def test_apply_plan_writes_all_seven_paper_sections(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")

    slug = "attention-deadbeef"
    plan = IngestPlan(
        paper=_paper_page(slug),
        concepts=[
            IngestConceptTouch(
                slug="transformer",
                canonical_name="Transformer",
                aliases=["xformer"],
                op="create",
                summary_section="Self-attention based architecture.",
                related_papers_addition=[slug],
                related_claims_addition=["claim-1"],
            )
        ],
        distillation=_distillation(slug),
        log_subject="Attention Is All You Need",
        notes=[],
    )

    touched = apply_plan(workspace, plan, _source(slug))

    paper_path = workspace.papers_dir / f"{slug}.md"
    assert paper_path.exists()
    body = paper_path.read_text(encoding="utf-8")
    for section in PAPER_SECTIONS:
        assert f"## {section}" in body
    assert "Self-attention with multi-head." in body
    assert "[[concepts/transformer|Transformer]]" in body

    # Concept page was created with the new content.
    concept_path = workspace.concepts_dir / "transformer.md"
    assert concept_path.exists()
    concept_body = concept_path.read_text(encoding="utf-8")
    for section in CONCEPT_SECTIONS:
        assert f"## {section}" in concept_body
    assert "Self-attention based architecture." in concept_body
    assert f"[[papers/{slug}|{slug}]]" in concept_body
    assert "- claim-1" in concept_body
    fm = read_page_frontmatter(concept_path)
    assert fm["aliases"] == ["xformer"]

    # Distillation JSON sidecar persisted.
    by_source = workspace.state_by_source_dir / f"{slug}.json"
    assert by_source.exists()
    loaded = load_distillation(workspace, slug)
    assert loaded is not None
    assert loaded.source.id == slug
    assert {e.id for e in loaded.entities} == {"ent-transformer"}

    # Index regenerated with new paper + concept.
    index_body = workspace.index_md_path.read_text(encoding="utf-8")
    assert f"[[papers/{slug}|" in index_body
    assert "[[concepts/transformer|" in index_body

    # Log appended with an ``ingest`` entry mentioning the subject.
    log_body = workspace.log_md_path.read_text(encoding="utf-8")
    assert "] ingest |" in log_body
    assert "Attention Is All You Need" in log_body

    # Conversation log appended one JSONL row.
    conv = workspace.conversation_log_path.read_text(encoding="utf-8").splitlines()
    assert len(conv) == 1
    row = json.loads(conv[0])
    assert row["event"] == "ingest"
    assert row["slug"] == slug

    # All paths returned by apply_plan are workspace-relative.
    for rel in touched:
        assert not rel.startswith("/"), rel


def test_apply_plan_merges_existing_concept_without_dupe_aliases(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")

    # Seed an existing concept page with one alias + a summary.
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer", aliases=["xformer"]),
        {"Summary": "Original summary."},
    )

    slug = "follow-up-paper-cafebabe"
    plan = IngestPlan(
        paper=_paper_page(slug).model_copy(update={"slug": slug}),
        concepts=[
            IngestConceptTouch(
                slug="transformer",
                canonical_name="Transformer",
                aliases=["xformer", "self-attention-model"],
                op="merge",
                summary_section="New angle: transformers compress relational graphs.",
                related_papers_addition=[slug],
                related_claims_addition=["claim-2"],
            )
        ],
        distillation=_distillation(slug),
        log_subject="Follow-up paper",
        notes=[],
    )

    apply_plan(workspace, plan, _source(slug))

    concept_path = workspace.concepts_dir / "transformer.md"
    body = concept_path.read_text(encoding="utf-8")
    assert "Original summary." in body  # prior content preserved
    assert "### From follow-up-paper-cafebabe" in body
    assert "compress relational graphs" in body
    fm = read_page_frontmatter(concept_path)
    # aliases merged, deduped
    assert fm["aliases"] == ["xformer", "self-attention-model"]


def test_apply_plan_is_idempotent_for_index_regen(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    slug = "p1-aaaaaaaa"
    plan = IngestPlan(
        paper=_paper_page(slug),
        concepts=[],
        distillation=_distillation(slug),
        log_subject="P1",
    )
    apply_plan(workspace, plan, _source(slug))
    first_index = workspace.index_md_path.read_text(encoding="utf-8")
    apply_plan(workspace, plan, _source(slug))
    second_index = workspace.index_md_path.read_text(encoding="utf-8")
    assert first_index == second_index


def test_apply_plan_fills_missing_source_refs(tmp_path: Path) -> None:
    """If the LLM omits ``sourceRefs`` we back-fill the source id."""
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    slug = "p2-bbbbbbbb"
    plan = IngestPlan(
        paper=_paper_page(slug),
        concepts=[],
        distillation=DistillationPayload(
            source=_source(slug),
            entities=[Entity(id="e", title="X")],  # missing sourceRefs
        ),
        log_subject="P2",
    )
    apply_plan(workspace, plan, _source(slug))

    loaded = load_distillation(workspace, slug)
    assert loaded is not None
    assert len(loaded.entities[0].sourceRefs) == 1
    assert loaded.entities[0].sourceRefs[0].sourceId == slug


def test_apply_plan_reverse_projects_claims_into_concept_pages(tmp_path: Path) -> None:
    """A claim whose ``entityIds`` reference a concept lands in that concept's Related Claims."""
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    slug = "rev-cccccccc"
    plan = IngestPlan(
        paper=_paper_page(slug).model_copy(update={"slug": slug}),
        concepts=[
            IngestConceptTouch(
                slug="self-attention",
                canonical_name="Self-Attention",
                op="create",
                summary_section="Sub-quadratic alternative to recurrence.",
                related_papers_addition=[slug],
                related_claims_addition=[],
            )
        ],
        distillation=DistillationPayload(
            source=_source(slug),
            entities=[
                Entity(
                    id="entity-self-attention",
                    title="Self-Attention",
                    aliases=["self-attention"],
                )
            ],
            claims=[
                Claim(
                    id="c-attn-1",
                    title="Multi-head attention generalizes single-head attention",
                    entityIds=["entity-self-attention"],
                )
            ],
        ),
        log_subject="Reverse-projection test",
    )
    apply_plan(workspace, plan, _source(slug))

    concept_body = (workspace.concepts_dir / "self-attention.md").read_text(encoding="utf-8")
    assert "## Related Claims" in concept_body
    assert "- [c-attn-1] Multi-head attention generalizes single-head attention" in concept_body
    # Source slug is included so a reader knows which paper introduced the claim.
    assert f"({slug})" in concept_body


def test_apply_plan_defaults_concept_type_to_concept(tmp_path: Path) -> None:
    """An ``IngestConceptTouch`` with no explicit type still produces ``type: concept``."""
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    slug = "type-dddddddd"
    plan = IngestPlan(
        paper=_paper_page(slug).model_copy(update={"slug": slug}),
        concepts=[
            IngestConceptTouch(
                slug="layer-norm",
                canonical_name="Layer Normalization",
                op="create",
                summary_section="Per-sample feature normalization.",
            )
        ],
        distillation=_distillation(slug),
        log_subject="Type default test",
    )
    apply_plan(workspace, plan, _source(slug))
    fm = read_page_frontmatter(workspace.concepts_dir / "layer-norm.md")
    assert fm["type"] == "concept"


def test_apply_plan_auto_injects_infrastructure_metadata(tmp_path: Path) -> None:
    """Workspaces, timestamps, origin, status get populated even when the LLM omits them."""
    workspace = Workspace.at(tmp_path / "wkspace")
    workspace.init_empty("Test")
    slug = "meta-eeeeeeee"
    plan = IngestPlan(
        paper=_paper_page(slug).model_copy(update={"slug": slug}),
        concepts=[],
        distillation=DistillationPayload(
            source=_source(slug),
            entities=[Entity(id="ent", title="Bare Entity")],
            claims=[
                Claim(id="cl", title="Bare Claim", entityIds=["ent"]),
            ],
            relations=[
                Relation(id="r", type="introduces", fromId="ent", toId="ent"),
            ],
            tasks=[Task(id="t", title="Open question?")],
        ),
        log_subject="Metadata injection test",
    )
    apply_plan(workspace, plan, _source(slug))

    loaded = load_distillation(workspace, slug)
    assert loaded is not None
    for collection in (loaded.entities, loaded.claims, loaded.relations, loaded.tasks):
        for item in collection:
            assert item.workspaceId == "wkspace", item
            assert item.createdAt.endswith("Z"), item.createdAt
            assert item.updatedAt.endswith("Z"), item.updatedAt
            assert item.origin == f"ingest:{slug}", item.origin
            assert item.status == "active", item.status


def test_apply_plan_does_not_write_vector_index(tmp_path: Path) -> None:
    """``apply_plan`` is a pure filesystem writer over the markdown LLM-Wiki.

    Memory is a pure LLM-Wiki (markdown pages + index.md); there is no
    embedding / vector index, so ``apply_plan`` must never report a
    ``state/vec.sqlite`` write.
    """
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    slug = "pure-ffffffff"
    plan = IngestPlan(
        paper=_paper_page(slug).model_copy(update={"slug": slug}),
        concepts=[],
        distillation=_distillation(slug),
        log_subject="Purity test",
    )
    touched = apply_plan(workspace, plan, _source(slug))
    assert "state/vec.sqlite" not in touched
