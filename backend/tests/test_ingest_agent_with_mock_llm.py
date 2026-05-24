# SPDX-License-Identifier: AGPL-3.0-or-later
"""``IngestAgent`` with a stub planner — exercises the end-to-end loop.

We never hit a real LLM. The planner protocol is injected so the test can
hand back a hand-built ``IngestPlan`` and assert ``apply_plan`` runs through
correctly inside the agent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xreadagent.agents.ingest import IngestAgent, IngestPlanner
from xreadagent.agents.ingest_schema import (
    IngestConceptTouch,
    IngestPaperPage,
    IngestPlan,
)
from xreadagent.schemas.entities import Claim, Entity, SourceRef
from xreadagent.schemas.sources import Source
from xreadagent.schemas.wiki_pages import ConceptFrontmatter, PaperFrontmatter
from xreadagent.wiki.distillation import DistillationPayload
from xreadagent.wiki.pages import write_concept_page, write_paper_page
from xreadagent.wiki.workspace import Workspace


def _make_plan(slug: str) -> IngestPlan:
    return IngestPlan(
        paper=IngestPaperPage(
            slug=slug,
            frontmatter=PaperFrontmatter(
                title="Mock Paper",
                source="raw/mock.pdf",
                source_hash="mockhash",
            ),
            background="b",
            challenges="c",
            solution="s",
            positioning="p",
            key_concepts="- [[concepts/foo|Foo]]",
            experiments="e",
            open_questions="oq",
        ),
        concepts=[
            IngestConceptTouch(
                slug="foo",
                canonical_name="Foo",
                op="create",
                summary_section="Foo is the canonical example.",
            )
        ],
        distillation=DistillationPayload(
            source=Source(
                id=slug, title="Mock Paper", slug=slug, contentHash="mockhash"
            ),
            entities=[
                Entity(id="ent-foo", title="Foo", sourceRefs=[SourceRef(sourceId=slug)])
            ],
            claims=[
                Claim(
                    id="claim-1",
                    title="foo claim",
                    entityIds=["ent-foo"],
                    sourceRefs=[SourceRef(sourceId=slug)],
                )
            ],
        ),
        log_subject="Mock Paper",
    )


async def test_ingest_agent_runs_planner_then_applies_plan(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")

    slug = "mock-paper-mockhash01"
    extract_path = workspace.extracts_dir / f"{slug}.md"
    extract_path.parent.mkdir(parents=True, exist_ok=True)
    extract_path.write_text("# Mock extract\n\nA short body.", encoding="utf-8")

    called: dict[str, object] = {}

    def planner(prompt: str, *, schema: type[IngestPlan]) -> IngestPlan:
        called["prompt"] = prompt
        called["schema"] = schema
        return _make_plan(slug)

    agent = IngestAgent(workspace, planner=planner)
    source = Source(
        id=slug, title="Mock Paper", slug=slug, contentHash="mockhash"
    )

    result = await agent.ingest(source, extract_path)

    assert result.plan.paper.slug == slug
    assert result.cache_hit is False
    # The planner was called once with a prompt that included the extract body.
    assert isinstance(called["prompt"], str)
    assert "A short body." in called["prompt"]  # type: ignore[operator]
    assert called["schema"] is IngestPlan
    # Files were touched.
    assert (workspace.papers_dir / f"{slug}.md").exists()
    assert (workspace.concepts_dir / "foo.md").exists()


async def test_ingest_agent_requires_planner_or_model(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    with pytest.raises(ValueError):
        IngestAgent(workspace)


async def test_ingest_agent_exposes_tool_list(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")

    def planner(prompt: str, *, schema: type[IngestPlan]) -> IngestPlan:
        return _make_plan("ignored")

    agent = IngestAgent(workspace, planner=planner)
    names = {tool.name for tool in agent.tools}
    assert {
        "read_extract",
        "list_papers",
        "list_concepts",
        "read_paper",
        "read_concept",
        "search_wiki",
        "read_index",
    } <= names


async def test_ingest_agent_includes_workspace_summary_in_prompt(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    # Pre-populate one paper to exercise the workspace-summary section.
    write_paper_page(
        workspace,
        "prior-paper-0001",
        PaperFrontmatter(title="Prior Paper", source="raw/p.pdf", source_hash="p"),
        {},
    )
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer", aliases=["xformer"]),
        {},
    )

    slug = "new-paper-2222"
    extract_path = workspace.extracts_dir / f"{slug}.md"
    extract_path.parent.mkdir(parents=True, exist_ok=True)
    extract_path.write_text("extract body.", encoding="utf-8")

    captured: list[str] = []

    def planner(prompt: str, *, schema: type[IngestPlan]) -> IngestPlan:
        captured.append(prompt)
        return _make_plan(slug)

    agent = IngestAgent(workspace, planner=planner)
    source = Source(id=slug, title="New Paper", slug=slug, contentHash="n")
    await agent.ingest(source, extract_path)

    assert captured
    prompt = captured[0]
    assert "Existing papers (1)" in prompt
    assert "prior-paper-0001" in prompt
    assert "Existing concepts (1)" in prompt
    assert "transformer" in prompt
    assert "aliases: xformer" in prompt
    assert "extract body." in prompt
    # The planner protocol matches the static type.
    _: IngestPlanner = planner
