# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for wiki path / slug helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from xreadagent.wiki.paths import (
    WORKSPACE_LAYOUT,
    concept_slug,
    kebab_slug,
    stable_source_slug,
    validate_wiki_path,
)


def test_workspace_layout_has_expected_keys() -> None:
    expected = {
        "raw",
        "raw_processed",
        "extracts",
        "state",
        "state_by_source",
        "wiki",
        "wiki_papers",
        "wiki_concepts",
        "wiki_queries",
    }
    assert expected.issubset(WORKSPACE_LAYOUT.keys())


def test_kebab_slug_basic() -> None:
    assert kebab_slug("Attention Is All You Need") == "attention-is-all-you-need"
    assert kebab_slug("  GPT-4  ") == "gpt-4"
    assert kebab_slug("café au lait") == "cafe-au-lait"
    assert kebab_slug("") == "item"
    assert kebab_slug("!!!") == "item"


def test_stable_source_slug_is_deterministic() -> None:
    title = "Attention Is All You Need"
    key = "document:abc-123"
    slug = stable_source_slug(title, key)
    assert slug == stable_source_slug(title, key), "must be deterministic"
    assert slug.startswith("attention-is-all-you-need-")
    suffix = slug.rsplit("-", 1)[-1]
    assert len(suffix) == 12
    assert all(c in "0123456789abcdef" for c in suffix)


def test_stable_source_slug_differs_for_distinct_keys() -> None:
    a = stable_source_slug("Same Title", "key:a")
    b = stable_source_slug("Same Title", "key:b")
    assert a != b


def test_stable_source_slug_handles_empty_source_key() -> None:
    assert stable_source_slug("hello world", "") == "hello-world"


def test_concept_slug_collision_appends_counter() -> None:
    existing: set[str] = set()
    first = concept_slug("GPT", existing)
    existing.add(first)
    second = concept_slug("GPT", existing)
    existing.add(second)
    third = concept_slug("GPT", existing)
    assert first == "gpt"
    assert second == "gpt-2"
    assert third == "gpt-3"


def test_concept_slug_empty_falls_back_to_concept() -> None:
    assert concept_slug("", set()) == "concept"


def test_validate_wiki_path_accepts_simple_relative(tmp_path: Path) -> None:
    resolved = validate_wiki_path(tmp_path, "wiki/papers/hello.md")
    assert resolved.is_absolute()
    assert resolved.relative_to(tmp_path.resolve()).as_posix() == "wiki/papers/hello.md"


def test_validate_wiki_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_wiki_path(tmp_path, "../etc/passwd")
    with pytest.raises(ValueError):
        validate_wiki_path(tmp_path, "wiki/../../etc/passwd")


def test_validate_wiki_path_rejects_absolute(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_wiki_path(tmp_path, "/etc/passwd")
    with pytest.raises(ValueError):
        validate_wiki_path(tmp_path, "C:\\Windows\\System32")


def test_validate_wiki_path_rejects_forbidden_chars(tmp_path: Path) -> None:
    for bad in ['wiki/<bad>.md', 'wiki/bad"name.md', "wiki/bad|name.md", "wiki/bad?.md"]:
        with pytest.raises(ValueError):
            validate_wiki_path(tmp_path, bad)


def test_validate_wiki_path_rejects_empty(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_wiki_path(tmp_path, "")
    with pytest.raises(ValueError):
        validate_wiki_path(tmp_path, "   ")
