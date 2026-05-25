# SPDX-License-Identifier: AGPL-3.0-or-later
"""``TranslationsIndex`` / ``TranslationsManifest`` schema + persistence tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from xreadagent.translation.manifest import (
    TranslationEntry,
    TranslationsIndex,
    TranslationsManifest,
)
from xreadagent.wiki.workspace import Workspace


def _seed_workspace(tmp_path: Path) -> Workspace:
    workspace = Workspace.at(tmp_path / "ws")
    workspace.init_empty("Manifest Test")
    return workspace


def test_entry_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        TranslationEntry(  # type: ignore[call-arg]
            sourceSlug="x",
            sourceHash="h",
            targetLang="zh",
            model="m",
            translatedAt="t",
            durationS=0.1,
            mystery="forbidden",  # extra field — strict mode rejects.
        )


def test_entry_required_fields_enforced() -> None:
    with pytest.raises(ValidationError):
        TranslationEntry()  # type: ignore[call-arg]


def test_manifest_load_returns_empty_when_absent(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path)
    # Remove the seeded manifest to verify "no file" path.
    workspace.translations_manifest_path.unlink()
    index = TranslationsIndex.load(workspace)
    assert index.all() == []


def test_manifest_round_trip(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path)
    index = TranslationsIndex.load(workspace)

    entry = TranslationEntry(
        sourceSlug="attention-aaa",
        sourceHash="aaa",
        targetLang="zh",
        model="anthropic:claude-sonnet-4-6",
        monoPath="translations/attention-aaa.mono.pdf",
        dualPath="translations/attention-aaa.dual.pdf",
        translatedAt="2026-05-25T10:00:00Z",
        durationS=12.5,
        babeldocVersion="0.6.2",
    )
    index.add(entry)
    index.save()

    reloaded = TranslationsIndex.load(workspace)
    rows = reloaded.all()
    assert len(rows) == 1
    assert rows[0] == entry


def test_find_keys_on_triple(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path)
    index = TranslationsIndex.load(workspace)
    e1 = TranslationEntry(
        sourceSlug="s",
        sourceHash="h1",
        targetLang="zh",
        model="m1",
        translatedAt="t",
        durationS=1.0,
    )
    e2 = TranslationEntry(
        sourceSlug="s",
        sourceHash="h1",
        targetLang="zh",
        model="m2",  # different model
        translatedAt="t",
        durationS=1.0,
    )
    e3 = TranslationEntry(
        sourceSlug="s",
        sourceHash="h1",
        targetLang="ja",  # different lang
        model="m1",
        translatedAt="t",
        durationS=1.0,
    )
    index.add(e1)
    index.add(e2)
    index.add(e3)
    index.save()

    reloaded = TranslationsIndex.load(workspace)
    assert reloaded.find("h1", "zh", "m1") == e1
    assert reloaded.find("h1", "zh", "m2") == e2
    assert reloaded.find("h1", "ja", "m1") == e3
    assert reloaded.find("h1", "ja", "m2") is None
    assert reloaded.find("h2", "zh", "m1") is None


def test_add_replaces_matching_triple(tmp_path: Path) -> None:
    """Re-running a translation overwrites the matching manifest row, not duplicates."""
    workspace = _seed_workspace(tmp_path)
    index = TranslationsIndex.load(workspace)

    first = TranslationEntry(
        sourceSlug="s",
        sourceHash="h",
        targetLang="zh",
        model="m",
        translatedAt="2026-05-25T10:00:00Z",
        durationS=10.0,
    )
    index.add(first)

    second = TranslationEntry(
        sourceSlug="s",
        sourceHash="h",
        targetLang="zh",
        model="m",
        translatedAt="2026-05-25T11:00:00Z",  # newer
        durationS=20.0,
    )
    index.add(second)
    index.save()

    reloaded = TranslationsIndex.load(workspace)
    assert len(reloaded.all()) == 1
    assert reloaded.all()[0].translatedAt == "2026-05-25T11:00:00Z"


def test_manifest_file_is_valid_json(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path)
    index = TranslationsIndex.load(workspace)
    entry = TranslationEntry(
        sourceSlug="s",
        sourceHash="h",
        targetLang="zh",
        model="m",
        translatedAt="t",
        durationS=1.0,
    )
    index.add(entry)
    index.save()
    raw = workspace.translations_manifest_path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    # camelCase enforcement on the persisted shape.
    assert payload["entries"][0]["sourceSlug"] == "s"
    assert payload["version"] == 1


def test_manifest_atomic_write_does_not_leave_tmp_file(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path)
    index = TranslationsIndex.load(workspace)
    index.add(
        TranslationEntry(
            sourceSlug="s",
            sourceHash="h",
            targetLang="zh",
            model="m",
            translatedAt="t",
            durationS=1.0,
        )
    )
    index.save()
    # The atomic-write helper renames a sibling .tmp file; verify it does not
    # remain behind after a successful save.
    siblings = list(workspace.translations_manifest_path.parent.iterdir())
    tmp_files = [p for p in siblings if ".tmp" in p.name]
    assert tmp_files == []


def test_top_level_manifest_strict_extra_forbidden(tmp_path: Path) -> None:
    """The wire schema must reject unknown top-level keys (state JSON discipline)."""
    with pytest.raises(ValidationError):
        TranslationsManifest.model_validate({"version": 1, "entries": [], "mystery": True})
