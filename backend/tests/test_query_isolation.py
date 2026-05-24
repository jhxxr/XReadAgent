# SPDX-License-Identifier: AGPL-3.0-or-later
"""Strict isolation: query never writes to the synthesis zone.

This is the locked contract from D4 in ``plan.md`` §11. The test takes a
byte-level digest of every file in the synthesis zone (papers/, concepts/,
index.md, log.md, overview.md, open-questions.md) BEFORE the query and again
AFTER, and asserts every digest is unchanged. The query archive is the only
new file allowed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from xreadagent.agents.query import QueryAgent
from xreadagent.agents.query_orchestrator import answer_query
from xreadagent.agents.query_schema import CitedEvidence, QueryAnswer
from xreadagent.schemas.wiki_pages import ConceptFrontmatter, PaperFrontmatter
from xreadagent.wiki.pages import write_concept_page, write_paper_page
from xreadagent.wiki.workspace import Workspace


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_synthesis_zone(workspace: Workspace) -> dict[str, str]:
    """Take a content digest of every file the query agent must NOT modify."""
    snapshot: dict[str, str] = {}
    # Top-level synthesis files.
    for path in (
        workspace.index_md_path,
        workspace.log_md_path,
        workspace.overview_md_path,
        workspace.open_questions_md_path,
    ):
        if path.exists():
            snapshot[path.relative_to(workspace.root).as_posix()] = _digest(path)
    # Papers and concepts dirs (recursive).
    for directory in (workspace.papers_dir, workspace.concepts_dir):
        if not directory.exists():
            continue
        for entry in directory.rglob("*"):
            if entry.is_file():
                snapshot[entry.relative_to(workspace.root).as_posix()] = _digest(entry)
    return snapshot


def _seed_workspace(tmp_path: Path) -> Workspace:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Isolation Test")
    write_paper_page(
        workspace,
        "alpha-aaa",
        PaperFrontmatter(title="Alpha Paper", source="raw/alpha.pdf", source_hash="aaa"),
        {
            "Background": "alpha background",
            "Challenges": "alpha challenges",
            "Solution": "alpha solution",
            "Positioning": "alpha positioning",
            "Key Concepts": "- [[concepts/transformer|Transformer]]",
            "Experiments": "alpha experiments",
            "Open Questions": "alpha open",
        },
    )
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer", aliases=["xformer"]),
        {"Summary": "Original summary."},
    )
    return workspace


async def test_query_does_not_modify_synthesis_zone(tmp_path: Path) -> None:
    """Run a query and verify every synthesis-zone file is byte-identical."""
    workspace = _seed_workspace(tmp_path)
    before = _snapshot_synthesis_zone(workspace)

    def planner(prompt: str, *, schema: type[QueryAnswer]) -> QueryAnswer:
        # Return a "rich" answer with all the optional sections populated, so we
        # exercise every code path the orchestrator can take.
        return QueryAnswer(
            question="What does Alpha Paper claim?",
            answer_markdown="Alpha solution. See [[papers/alpha-aaa]].",
            evidence=[
                CitedEvidence(
                    source_wiki_path="papers/alpha-aaa.md",
                    quote="alpha solution",
                    confidence="high",
                )
            ],
            sources_cited=["papers/alpha-aaa.md"],
            layers_used=["index", "papers"],
            confidence="high",
            open_questions_raised=["raised q"],
            notes=["a note"],
        )

    agent = QueryAgent(workspace, planner=planner)
    result = await answer_query(workspace, "What does Alpha Paper claim?", agent=agent)

    # The single allowed write: the query archive.
    assert result.query_page_path.exists()
    rel = result.query_page_path.relative_to(workspace.root).as_posix()
    assert rel.startswith("wiki/queries/")

    after = _snapshot_synthesis_zone(workspace)
    assert before == after, (
        "Query agent modified synthesis-zone files! diff="
        f"{ {k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k)} }"  # noqa: E501
    )

    # And no new files appeared anywhere except under wiki/queries and state/.
    forbidden_new = []
    for path in workspace.wiki_dir.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(workspace.root).as_posix()
        if rel_path.startswith("wiki/queries/"):
            continue
        # Pre-existing synthesis-zone files are in `before`; any not-in-before
        # entry would mean a new file was created outside queries/.
        if rel_path not in before:
            forbidden_new.append(rel_path)
    assert forbidden_new == [], (
        f"Query created new files in the synthesis zone: {forbidden_new}"
    )


async def test_repeated_queries_keep_synthesis_zone_stable(tmp_path: Path) -> None:
    """Two back-to-back queries — synthesis zone digest stays constant."""
    workspace = _seed_workspace(tmp_path)
    before = _snapshot_synthesis_zone(workspace)

    def planner(prompt: str, *, schema: type[QueryAnswer]) -> QueryAnswer:
        return QueryAnswer(
            question="Q",
            answer_markdown="A",
            evidence=[],
            sources_cited=[],
            layers_used=["index"],
            confidence="low",
        )

    agent = QueryAgent(workspace, planner=planner)
    await answer_query(workspace, "first question that goes on and on", agent=agent)
    after_first = _snapshot_synthesis_zone(workspace)
    await answer_query(workspace, "second question", agent=agent)
    after_second = _snapshot_synthesis_zone(workspace)

    assert before == after_first
    assert before == after_second
