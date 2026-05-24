# SPDX-License-Identifier: AGPL-3.0-or-later
"""``CrystallizeAgent.propose`` is read-only — it never writes."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from xreadagent.agents.crystallize import CrystallizeAgent
from xreadagent.agents.crystallize_schema import (
    CrystallizeConceptPatch,
    CrystallizePaperPatch,
    CrystallizePlan,
)
from xreadagent.schemas.wiki_pages import ConceptFrontmatter, PaperFrontmatter, QueryFrontmatter
from xreadagent.wiki.pages import write_concept_page, write_paper_page, write_query_page
from xreadagent.wiki.workspace import Workspace


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _full_snapshot(workspace: Workspace) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in workspace.root.rglob("*"):
        if path.is_file():
            snapshot[path.relative_to(workspace.root).as_posix()] = _digest(path)
    return snapshot


def _seed(tmp_path: Path) -> tuple[Workspace, Path]:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    write_paper_page(
        workspace,
        "alpha-aaa",
        PaperFrontmatter(title="Alpha", source="raw/a.pdf", source_hash="aaa"),
        {"Background": "bg"},
    )
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer"),
        {"Summary": "summary"},
    )
    archive = write_query_page(
        workspace,
        "general",
        "2026-05-22",
        "what-is-transformer",
        QueryFrontmatter(
            question="What is a transformer?",
            date="2026-05-22",
            layers_used=["index", "papers"],
            sources_cited=["papers/alpha-aaa.md"],
        ),
        {
            "Question": "What is a transformer?",
            "Answer": "A self-attention model — see [[papers/alpha-aaa]].",
            "Sources": "- [[papers/alpha-aaa.md]] — _high_: self-attention",
        },
    )
    return workspace, archive


async def test_propose_does_not_write_anything(tmp_path: Path) -> None:
    workspace, archive = _seed(tmp_path)
    before = _full_snapshot(workspace)

    def planner(prompt: str, *, schema: type[CrystallizePlan]) -> CrystallizePlan:
        return CrystallizePlan(
            query_archive_path=archive.relative_to(workspace.root).as_posix(),
            paper_patches=[
                CrystallizePaperPatch(
                    paper_slug="alpha-aaa",
                    section="key_concepts",
                    op="append",
                    new_content="- [[concepts/transformer|Transformer]]",
                )
            ],
            concept_patches=[
                CrystallizeConceptPatch(
                    concept_slug="transformer",
                    op="merge",
                    summary_addition="Promoted insight.",
                )
            ],
            log_subject="promote transformer insight",
            rationale="from 2026-05-22 query",
        )

    agent = CrystallizeAgent(workspace, planner=planner)
    proposal = await agent.propose(archive)

    assert isinstance(proposal.plan, CrystallizePlan)
    assert proposal.plan.paper_patches[0].paper_slug == "alpha-aaa"
    # No files have changed.
    after = _full_snapshot(workspace)
    assert before == after, (
        f"propose() wrote to disk! diff="
        f"{ {k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k)} }"  # noqa: E501
    )


async def test_propose_requires_planner_or_model(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    with pytest.raises(ValueError):
        CrystallizeAgent(workspace)


async def test_propose_raises_on_missing_archive(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")

    def planner(prompt: str, *, schema: type[CrystallizePlan]) -> CrystallizePlan:
        raise AssertionError("planner should not be called for missing archive")

    agent = CrystallizeAgent(workspace, planner=planner)
    with pytest.raises(FileNotFoundError):
        await agent.propose(workspace.queries_dir / "missing.md")


async def test_propose_includes_archive_body_in_prompt(tmp_path: Path) -> None:
    workspace, archive = _seed(tmp_path)
    captured: list[str] = []

    def planner(prompt: str, *, schema: type[CrystallizePlan]) -> CrystallizePlan:
        captured.append(prompt)
        return CrystallizePlan(
            query_archive_path=archive.relative_to(workspace.root).as_posix(),
            log_subject="noop",
            rationale="noop",
        )

    agent = CrystallizeAgent(workspace, planner=planner)
    await agent.propose(archive)

    assert captured
    prompt = captured[0]
    assert "Query archive" in prompt
    assert "What is a transformer?" in prompt
    assert "alpha-aaa" in prompt
