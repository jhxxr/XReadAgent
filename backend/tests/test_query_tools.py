# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only tool wrappers used by the query agent."""

from __future__ import annotations

import json
from pathlib import Path

from xreadagent.agents.query_tools import build_query_tools
from xreadagent.schemas.entities import Entity, SourceRef
from xreadagent.schemas.sources import Source
from xreadagent.schemas.wiki_pages import ConceptFrontmatter, PaperFrontmatter
from xreadagent.wiki.distillation import DistillationPayload, save_distillation
from xreadagent.wiki.log import WikiLog
from xreadagent.wiki.pages import write_concept_page, write_paper_page
from xreadagent.wiki.workspace import Workspace


def _seed(tmp_path: Path) -> Workspace:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    workspace.extracts_dir.mkdir(parents=True, exist_ok=True)
    (workspace.extracts_dir / "alpha-aaa.md").write_text(
        "# Alpha extract\n\nLorem ipsum.", encoding="utf-8"
    )
    write_paper_page(
        workspace,
        "alpha-aaa",
        PaperFrontmatter(title="Alpha Paper", source="raw/alpha.pdf", source_hash="aaa"),
        {"Background": "alpha background"},
    )
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer", aliases=["xformer"]),
        {"Summary": "self-attention model"},
    )
    save_distillation(
        workspace,
        "alpha-aaa",
        DistillationPayload(
            source=Source(
                id="alpha-aaa",
                title="Alpha Paper",
                slug="alpha-aaa",
                contentHash="aaa",
            ),
            entities=[
                Entity(
                    id="ent-transformer",
                    title="Transformer",
                    summary="self-attention model",
                    sourceRefs=[SourceRef(sourceId="alpha-aaa")],
                )
            ],
        ),
    )
    return workspace


def test_query_tools_include_all_nine_tools(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    names = {tool.name for tool in build_query_tools(workspace)}
    assert {
        "read_extract",
        "list_papers",
        "list_concepts",
        "read_paper",
        "read_concept",
        "search_wiki",
        "read_index",
        "read_distillation",
        "list_recent_logs",
    } <= names


def test_read_distillation_returns_payload(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_query_tools(workspace)}
    payload = tools["read_distillation"].invoke({"slug": "alpha-aaa"})
    assert isinstance(payload, dict)
    assert payload["source"]["id"] == "alpha-aaa"
    assert payload["entities"][0]["id"] == "ent-transformer"


def test_read_distillation_returns_empty_for_unknown(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_query_tools(workspace)}
    assert tools["read_distillation"].invoke({"slug": "nope"}) == {}


def test_read_distillation_returns_empty_for_blank_slug(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_query_tools(workspace)}
    assert tools["read_distillation"].invoke({"slug": "   "}) == {}


def test_read_distillation_handles_corrupt_json(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    # Corrupt the json sidecar — the tool should swallow and return {}.
    path = workspace.state_by_source_dir / "alpha-aaa.json"
    path.write_text("not json", encoding="utf-8")
    tools = {t.name: t for t in build_query_tools(workspace)}
    assert tools["read_distillation"].invoke({"slug": "alpha-aaa"}) == {}


def test_list_recent_logs_returns_last_n_entries(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    log = WikiLog(workspace)
    for i in range(5):
        log.append("ingest", f"Paper {i}", files_touched=[f"wiki/papers/p-{i}.md"])

    tools = {t.name: t for t in build_query_tools(workspace)}
    entries = tools["list_recent_logs"].invoke({"n": 3})
    assert isinstance(entries, list)
    assert len(entries) == 3
    # list_recent_logs returns the newest entries at the end (chronological order).
    assert "Paper 2" in entries[0]
    assert "Paper 4" in entries[-1]


def test_list_recent_logs_zero_returns_empty(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    WikiLog(workspace).append("ingest", "Paper", files_touched=[])
    tools = {t.name: t for t in build_query_tools(workspace)}
    assert tools["list_recent_logs"].invoke({"n": 0}) == []


def test_list_recent_logs_missing_log_returns_empty(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.ensure_layout()
    # No init_empty — wiki/log.md does not exist.
    tools = {t.name: t for t in build_query_tools(workspace)}
    assert tools["list_recent_logs"].invoke({"n": 5}) == []


def test_list_recent_logs_caps_oversized_request(tmp_path: Path) -> None:
    workspace = _seed(tmp_path)
    log = WikiLog(workspace)
    for i in range(70):
        log.append("ingest", f"Paper {i}", files_touched=[])
    tools = {t.name: t for t in build_query_tools(workspace)}
    entries = tools["list_recent_logs"].invoke({"n": 10_000})
    # Cap is 50 per the module constant.
    assert len(entries) <= 50


def test_read_distillation_json_serializable(tmp_path: Path) -> None:
    """The returned dict round-trips through ``json.dumps`` (LangChain serializes)."""
    workspace = _seed(tmp_path)
    tools = {t.name: t for t in build_query_tools(workspace)}
    payload = tools["read_distillation"].invoke({"slug": "alpha-aaa"})
    json.dumps(payload)  # raises if non-serializable
