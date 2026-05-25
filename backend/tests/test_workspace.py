# SPDX-License-Identifier: AGPL-3.0-or-later
"""Workspace bootstrap tests."""

from __future__ import annotations

import json
from pathlib import Path

from xreadagent.wiki.workspace import Workspace


def test_ensure_layout_creates_all_dirs(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.ensure_layout()

    expected = [
        tmp_path / "raw",
        tmp_path / "raw" / "_processed",
        tmp_path / "extracts",
        tmp_path / "state",
        tmp_path / "state" / "by-source",
        tmp_path / "wiki",
        tmp_path / "wiki" / "papers",
        tmp_path / "wiki" / "concepts",
        tmp_path / "wiki" / "queries",
        tmp_path / "translations",
    ]
    for directory in expected:
        assert directory.is_dir(), f"expected directory missing: {directory}"


def test_ensure_layout_is_idempotent(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.ensure_layout()
    # Write a stray file under wiki/ — re-ensure_layout must not nuke it.
    sentinel = tmp_path / "wiki" / "sentinel.md"
    sentinel.write_text("hello", encoding="utf-8")

    workspace.ensure_layout()
    assert sentinel.exists()
    assert sentinel.read_text(encoding="utf-8") == "hello"


def test_init_empty_creates_seed_files(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    assert not workspace.is_initialized()

    workspace.init_empty("My Vault", workspace_id="ws-1")
    assert workspace.is_initialized()

    assert workspace.index_md_path.read_text(encoding="utf-8").startswith("# My Vault")
    assert "log" in workspace.log_md_path.read_text(encoding="utf-8").lower()
    assert workspace.overview_md_path.exists()
    assert workspace.open_questions_md_path.exists()

    manifest = json.loads(workspace.sources_json_path.read_text(encoding="utf-8"))
    assert manifest == {"workspaceId": "ws-1", "sources": []}

    summary = json.loads(workspace.compile_summary_json_path.read_text(encoding="utf-8"))
    assert summary["sourceCount"] == 0
    assert summary["compileDirty"] is False


def test_init_empty_does_not_overwrite_existing_files(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("First Title")
    original_index = workspace.index_md_path.read_text(encoding="utf-8")

    workspace.init_empty("Second Title")
    assert workspace.index_md_path.read_text(encoding="utf-8") == original_index


def test_workspace_paths_match_layout(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    assert workspace.papers_dir == tmp_path / "wiki" / "papers"
    assert workspace.concepts_dir == tmp_path / "wiki" / "concepts"
    assert workspace.queries_dir == tmp_path / "wiki" / "queries"
    assert workspace.raw_processed_dir == tmp_path / "raw" / "_processed"
    assert workspace.state_by_source_dir == tmp_path / "state" / "by-source"
    assert workspace.translations_dir == tmp_path / "translations"
    assert workspace.translations_manifest_path == tmp_path / "translations" / "manifest.json"


def test_init_empty_seeds_translations_manifest(tmp_path: Path) -> None:
    """``init_empty`` writes an empty translations manifest at v1 shape."""
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Translation Test")

    assert workspace.translations_manifest_path.exists()
    payload = json.loads(workspace.translations_manifest_path.read_text(encoding="utf-8"))
    assert payload == {"version": 1, "entries": []}
