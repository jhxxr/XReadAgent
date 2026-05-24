# SPDX-License-Identifier: AGPL-3.0-or-later
"""``QueryAgent`` + ``answer_query`` with a stub planner — end-to-end loop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xreadagent.agents.query import QueryAgent, QueryPlanner
from xreadagent.agents.query_orchestrator import answer_query
from xreadagent.agents.query_schema import CitedEvidence, QueryAnswer
from xreadagent.schemas.wiki_pages import PaperFrontmatter
from xreadagent.wiki.pages import write_paper_page
from xreadagent.wiki.workspace import Workspace


def _make_answer(question: str) -> QueryAnswer:
    return QueryAnswer(
        question=question,
        answer_markdown=(
            "Transformers introduced self-attention. "
            "See [[papers/attention-deadbeef]]."
        ),
        evidence=[
            CitedEvidence(
                source_wiki_path="papers/attention-deadbeef.md",
                quote="self-attention with multi-head",
                confidence="high",
            )
        ],
        sources_cited=["papers/attention-deadbeef.md"],
        layers_used=["index", "papers"],
        confidence="high",
        open_questions_raised=["What about cross-attention?"],
        notes=["Verified against extract."],
    )


def _seed_with_paper(tmp_path: Path) -> Workspace:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    write_paper_page(
        workspace,
        "attention-deadbeef",
        PaperFrontmatter(
            title="Attention Is All You Need",
            source="raw/attention.pdf",
            source_hash="deadbeef",
        ),
        {"Background": "RNNs dominated."},
    )
    return workspace


async def test_answer_query_writes_archive_and_nothing_else(tmp_path: Path) -> None:
    workspace = _seed_with_paper(tmp_path)
    question = "What does the transformer paper claim?"

    captured: list[str] = []

    def planner(prompt: str, *, schema: type[QueryAnswer]) -> QueryAnswer:
        captured.append(prompt)
        return _make_answer(question)

    agent = QueryAgent(workspace, planner=planner)
    result = await answer_query(workspace, question, agent=agent)

    # Archive was written.
    assert result.query_page_path.exists()
    assert result.query_page_path.is_relative_to(workspace.queries_dir)

    rel = result.query_page_path.relative_to(workspace.root).as_posix()
    assert rel.startswith("wiki/queries/")
    assert rel.endswith(".md")
    assert result.files_touched == [rel]

    body = result.query_page_path.read_text(encoding="utf-8")
    assert "## Question" in body
    assert "## Answer" in body
    assert "## Sources" in body
    assert "Transformers introduced self-attention." in body
    assert "[[papers/attention-deadbeef.md]]" in body
    # Open questions and notes are rendered in the Answer section.
    assert "Open questions raised" in body
    assert "What about cross-attention?" in body
    assert "Notes" in body

    # Conversation log got a query event with the right shape.
    conv_lines = workspace.conversation_log_path.read_text(encoding="utf-8").splitlines()
    assert conv_lines
    row = json.loads(conv_lines[-1])
    assert row["event"] == "query"
    assert row["question"] == question
    assert row["archive_path"] == rel
    assert "sources_cited" in row


async def test_answer_query_requires_planner_or_model(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    with pytest.raises(ValueError):
        QueryAgent(workspace)


async def test_answer_query_rejects_blank_question(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")

    def planner(prompt: str, *, schema: type[QueryAnswer]) -> QueryAnswer:
        raise AssertionError("planner should not be called for blank question")

    agent = QueryAgent(workspace, planner=planner)
    with pytest.raises(ValueError):
        await answer_query(workspace, "   ", agent=agent)


async def test_answer_query_respects_explicit_topic(tmp_path: Path) -> None:
    workspace = _seed_with_paper(tmp_path)

    def planner(prompt: str, *, schema: type[QueryAnswer]) -> QueryAnswer:
        return _make_answer("Q")

    agent = QueryAgent(workspace, planner=planner)
    result = await answer_query(
        workspace,
        "anything",
        agent=agent,
        topic="reinforcement learning",
    )
    rel = result.query_page_path.relative_to(workspace.root).as_posix()
    assert "/queries/reinforcement-learning/" in rel


async def test_answer_query_derives_topic_when_omitted(tmp_path: Path) -> None:
    workspace = _seed_with_paper(tmp_path)

    def planner(prompt: str, *, schema: type[QueryAnswer]) -> QueryAnswer:
        return _make_answer("Q")

    agent = QueryAgent(workspace, planner=planner)
    result = await answer_query(
        workspace,
        "How does PPO compare to GRPO?",
        agent=agent,
    )
    rel = result.query_page_path.relative_to(workspace.root).as_posix()
    # Derived topic uses the first 3 tokens — exact form may evolve, but
    # the segment should not be empty and should not equal the default.
    parts = rel.split("/")
    queries_idx = parts.index("queries")
    topic_dir = parts[queries_idx + 1]
    assert topic_dir
    assert topic_dir != ""


async def test_query_agent_includes_workspace_summary_in_prompt(tmp_path: Path) -> None:
    workspace = _seed_with_paper(tmp_path)
    captured: list[str] = []

    def planner(prompt: str, *, schema: type[QueryAnswer]) -> QueryAnswer:
        captured.append(prompt)
        return _make_answer("Q")

    agent = QueryAgent(workspace, planner=planner)
    await answer_query(workspace, "What is attention?", agent=agent)

    assert captured
    prompt = captured[0]
    assert "Existing papers (1)" in prompt
    assert "attention-deadbeef" in prompt
    # Protocol typecheck — the test stub satisfies QueryPlanner.
    _: QueryPlanner = planner


async def test_answer_query_tokens_used_propagates(tmp_path: Path) -> None:
    workspace = _seed_with_paper(tmp_path)

    def planner(prompt: str, *, schema: type[QueryAnswer]) -> QueryAnswer:
        return _make_answer("Q")

    agent = QueryAgent(workspace, planner=planner)
    result = await answer_query(workspace, "What is attention?", agent=agent)
    # Default planner contributes an empty dict; the contract is that the
    # field exists and is a dict.
    assert isinstance(result.tokens_used, dict)
