# SPDX-License-Identifier: AGPL-3.0-or-later
"""``SourcesIndex`` + ``compute_content_hash`` tests."""

from __future__ import annotations

import json
from pathlib import Path

from xreadagent.schemas.sources import Source
from xreadagent.wiki.sources import SourcesIndex, compute_content_hash
from xreadagent.wiki.workspace import Workspace


def _make_source(*, id_: str = "src-1", content_hash: str = "h1") -> Source:
    return Source(
        id=id_,
        title="A Paper",
        slug="a-paper-abcdef012345",
        contentHash=content_hash,
    )


def test_compute_content_hash_is_deterministic(tmp_path: Path) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_bytes(b"hello world")
    h1 = compute_content_hash(sample)
    h2 = compute_content_hash(sample)
    assert h1 == h2
    assert len(h1) == 64


def test_compute_content_hash_differs_for_different_content(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes(b"one")
    b.write_bytes(b"two")
    assert compute_content_hash(a) != compute_content_hash(b)


def test_sources_index_load_empty_workspace(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.ensure_layout()
    index = SourcesIndex.load(workspace)
    assert index.all() == []


def test_sources_index_save_then_load_round_trip(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")

    index = SourcesIndex.load(workspace)
    src = _make_source(id_="src-A", content_hash="hash-A")
    assert index.add_or_update(src) is True
    index.save()

    reloaded = SourcesIndex.load(workspace)
    assert len(reloaded.all()) == 1
    assert reloaded.find_by_id("src-A") == src
    assert reloaded.find_by_hash("hash-A") == src


def test_sources_index_add_or_update_idempotent_on_same_object(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    index = SourcesIndex.load(workspace)

    src = _make_source()
    assert index.add_or_update(src) is True
    # Re-adding the byte-identical row should report no change.
    assert index.add_or_update(src) is False


def test_sources_index_add_or_update_detects_changes(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    index = SourcesIndex.load(workspace)

    original = _make_source(id_="src-X", content_hash="h-old")
    index.add_or_update(original)

    updated = original.model_copy(update={"contentHash": "h-new"})
    assert index.add_or_update(updated) is True
    assert index.find_by_id("src-X") == updated
    assert index.find_by_hash("h-old") is None


def test_sources_index_save_writes_atomically(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    index = SourcesIndex.load(workspace)
    src = _make_source()
    index.add_or_update(src)
    index.save()

    # After save, no leftover .tmp file should remain in state/.
    state_files = list(workspace.state_dir.iterdir())
    tmp_files = [p for p in state_files if p.name.startswith(".") and p.name.endswith(".tmp")]
    assert tmp_files == []

    # On disk file should be valid JSON.
    payload = json.loads(workspace.sources_json_path.read_text(encoding="utf-8"))
    assert payload["sources"][0]["id"] == src.id
