# SPDX-License-Identifier: AGPL-3.0-or-later
"""``orchestrator.ingest_source`` end-to-end with cache-hit short-circuit."""

from __future__ import annotations

from pathlib import Path

from xreadagent.agents.ingest import IngestAgent
from xreadagent.agents.ingest_schema import (
    IngestConceptTouch,
    IngestPaperPage,
    IngestPlan,
)
from xreadagent.agents.orchestrator import ingest_source
from xreadagent.schemas.entities import Entity, SourceRef
from xreadagent.schemas.sources import Source
from xreadagent.schemas.wiki_pages import PaperFrontmatter
from xreadagent.wiki.distillation import DistillationPayload
from xreadagent.wiki.workspace import Workspace


def _drop_raw(workspace: Workspace, name: str, content: str) -> Path:
    path = workspace.raw_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _build_planner(call_log: list[str]) -> object:
    def planner(prompt: str, *, schema: type[IngestPlan]) -> IngestPlan:
        call_log.append(prompt)
        # Read the source slug out of the prompt so the plan slug matches.
        slug = ""
        for line in prompt.splitlines():
            line = line.strip()
            if line.startswith("- slug:"):
                slug = line.split(":", 1)[1].strip()
                break
        assert slug, "could not recover slug from prompt"
        return IngestPlan(
            paper=IngestPaperPage(
                slug=slug,
                frontmatter=PaperFrontmatter(
                    title="Mock", source=f"raw/{slug}.html", source_hash="x"
                ),
                background="b",
                challenges="c",
                solution="s",
                positioning="p",
                key_concepts="",
                experiments="e",
                open_questions="oq",
            ),
            concepts=[
                IngestConceptTouch(
                    slug="alpha",
                    canonical_name="Alpha",
                    op="create",
                    summary_section="alpha entry",
                )
            ],
            distillation=DistillationPayload(
                source=Source(id=slug, title="Mock", slug=slug, contentHash="x"),
                entities=[
                    Entity(
                        id="ent-1",
                        title="Alpha",
                        sourceRefs=[SourceRef(sourceId=slug)],
                    )
                ],
            ),
            log_subject="Mock",
        )

    return planner


async def test_ingest_source_runs_pipeline_then_agent(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    raw = _drop_raw(workspace, "page.html", "<html><body>hi</body></html>")
    calls: list[str] = []
    agent = IngestAgent(workspace, planner=_build_planner(calls))  # type: ignore[arg-type]

    result = await ingest_source(workspace, raw, agent=agent)
    assert result.cache_hit is False
    assert len(calls) == 1
    paper_path = workspace.papers_dir / f"{result.source.slug}.md"
    assert paper_path.exists()


async def test_ingest_source_short_circuits_on_cache_hit(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    raw = _drop_raw(workspace, "page.html", "<html><body>hi</body></html>")
    calls: list[str] = []
    agent = IngestAgent(workspace, planner=_build_planner(calls))  # type: ignore[arg-type]

    first = await ingest_source(workspace, raw, agent=agent)
    assert first.cache_hit is False
    assert len(calls) == 1

    # Same file, same content — second call must be a cache hit and NOT touch the LLM.
    second = await ingest_source(workspace, raw, agent=agent)
    assert second.cache_hit is True
    assert second.source.id == first.source.id
    assert len(calls) == 1  # planner was not invoked again
