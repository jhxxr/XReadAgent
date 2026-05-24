# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ``xreadagent.agents.json_planner``.

The planner has three documented repair passes:

1. Strip ```json / ``` markdown code fences from the response.
2. Extract a balanced ``{...}`` block when the model prefixes JSON with prose.
3. ``json.loads`` strings that landed where a ``list[BaseModel]`` was expected
   (the GLM-5.1-via-Anthropic-proxy bug we built this for).

Each test pins one of those passes by passing the right payload to a fake
chat client.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from xreadagent.agents.json_planner import (
    is_nested_list_string_error,
    is_truncated_output_error,
    make_json_planner,
    parse_and_repair,
    should_retry_with_json_planner,
)


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class _Inner(_Strict):
    slug: str
    name: str


class _Outer(_Strict):
    title: str
    items: list[_Inner] = Field(default_factory=list)


class _FakeAIMessage:
    """Mimics a LangChain AIMessage just enough for ``_extract_text``."""

    def __init__(self, content: Any) -> None:
        self.content = content


class _FakeChat:
    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.invocations: list[str] = []

    def invoke(self, prompt: str) -> Any:
        self.invocations.append(prompt)
        return self._payload


def test_parse_and_repair_accepts_clean_json() -> None:
    text = json.dumps({"title": "T", "items": [{"slug": "s", "name": "N"}]})
    parsed = parse_and_repair(text, _Outer)
    assert parsed.title == "T"
    assert parsed.items == [_Inner(slug="s", name="N")]


def test_parse_and_repair_strips_markdown_fences() -> None:
    payload = {"title": "T", "items": [{"slug": "s", "name": "N"}]}
    fenced = f"```json\n{json.dumps(payload)}\n```"
    parsed = parse_and_repair(fenced, _Outer)
    assert parsed.title == "T"

    # ``` (no json language tag) must also work.
    fenced_bare = f"```\n{json.dumps(payload)}\n```"
    parsed_bare = parse_and_repair(fenced_bare, _Outer)
    assert parsed_bare.title == "T"


def test_parse_and_repair_extracts_balanced_object_after_prose() -> None:
    payload = {"title": "T", "items": []}
    chatty = (
        "Sure! Here is the JSON you asked for:\n\n"
        + json.dumps(payload)
        + "\n\nLet me know if you need anything else."
    )
    parsed = parse_and_repair(chatty, _Outer)
    assert parsed.title == "T"


def test_parse_and_repair_unwraps_nested_list_as_string() -> None:
    """The GLM-via-proxy bug: ``items`` arrives as a JSON-encoded string."""
    payload = {
        "title": "T",
        "items": json.dumps([{"slug": "s1", "name": "N1"}, {"slug": "s2", "name": "N2"}]),
    }
    parsed = parse_and_repair(json.dumps(payload), _Outer)
    assert [i.slug for i in parsed.items] == ["s1", "s2"]


def test_parse_and_repair_rejects_non_object_root() -> None:
    with pytest.raises(ValueError, match="expected object"):
        parse_and_repair("[1, 2, 3]", _Outer)


def test_parse_and_repair_rejects_unparseable_text() -> None:
    with pytest.raises(ValueError, match="could not parse"):
        parse_and_repair("definitely not json at all", _Outer)


def test_make_json_planner_round_trips_via_fake_chat() -> None:
    payload = {"title": "T", "items": [{"slug": "s", "name": "N"}]}
    chat = _FakeChat(_FakeAIMessage(json.dumps(payload)))
    planner = make_json_planner(chat)

    parsed = planner("user prompt body", schema=_Outer)

    assert parsed.title == "T"
    assert chat.invocations, "fake chat should have been invoked"
    sent = chat.invocations[0]
    assert "user prompt body" in sent
    assert "Return ONLY a JSON object" in sent
    # The schema must be injected so the model knows the shape.
    assert "$defs" in sent or "items" in sent


def test_make_json_planner_handles_content_blocks() -> None:
    payload = {"title": "T2", "items": []}
    blocks = [{"type": "text", "text": json.dumps(payload)}]
    chat = _FakeChat(_FakeAIMessage(blocks))
    planner = make_json_planner(chat)
    parsed = planner("p", schema=_Outer)
    assert parsed.title == "T2"


def test_is_nested_list_string_error_detects_list_type_failure() -> None:
    from pydantic import ValidationError

    bad = {"title": "T", "items": json.dumps([{"slug": "s", "name": "N"}])}
    try:
        _Outer.model_validate(bad)
    except ValidationError as exc:
        assert is_nested_list_string_error(exc) is True
    else:
        pytest.fail("expected ValidationError")


def test_is_nested_list_string_error_false_for_unrelated_error() -> None:
    from pydantic import ValidationError

    # Missing required ``title`` is a different failure mode.
    try:
        _Outer.model_validate({"items": []})
    except ValidationError as exc:
        assert is_nested_list_string_error(exc) is False
    else:
        pytest.fail("expected ValidationError")


# ---------------------------------------------------------------------------
# New auto-fallback predicates: truncated output + combined gate
# ---------------------------------------------------------------------------


def test_should_retry_with_json_planner_on_list_type_error() -> None:
    """The original nested-list-as-string trigger still routes through retry."""
    from pydantic import ValidationError

    bad = {"title": "T", "items": json.dumps([{"slug": "s", "name": "N"}])}
    try:
        _Outer.model_validate(bad)
    except ValidationError as exc:
        assert should_retry_with_json_planner(exc) is True
    else:
        pytest.fail("expected ValidationError")


def test_should_retry_with_json_planner_on_none_model_type_error() -> None:
    """A truncated tool path lands as ``model_type`` with ``input=None``."""
    from pydantic import ValidationError

    # The tool path's failure shape: ``with_structured_output`` hands None
    # to the schema's outer validator when the chat model emitted no parseable
    # tool_use block.
    try:
        _Outer.model_validate(None)  # type: ignore[arg-type]
    except ValidationError as exc:
        assert is_truncated_output_error(exc) is True
        assert should_retry_with_json_planner(exc) is True
    else:
        pytest.fail("expected ValidationError")


def test_should_retry_with_json_planner_returns_false_on_unrelated_error() -> None:
    """Missing required field is a real model bug — bubble it up, don't retry."""
    from pydantic import ValidationError

    try:
        _Outer.model_validate({"items": []})
    except ValidationError as exc:
        assert should_retry_with_json_planner(exc) is False
    else:
        pytest.fail("expected ValidationError on missing required ``title``")


def test_should_retry_with_json_planner_returns_false_on_literal_mismatch() -> None:
    """A Literal mismatch (e.g. enum field) is a real bug — bubble up."""
    from typing import Literal

    from pydantic import ConfigDict, ValidationError

    class _Enum(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        kind: Literal["a", "b"]

    try:
        _Enum.model_validate({"kind": "c"})
    except ValidationError as exc:
        # Sanity check that this is NOT mis-classified as a retry-able failure.
        assert should_retry_with_json_planner(exc) is False
    else:
        pytest.fail("expected ValidationError on Literal mismatch")


def test_is_truncated_output_error_false_on_present_but_wrong_input() -> None:
    """A ``model_type`` whose input is a non-None value is NOT truncation."""
    from pydantic import ValidationError

    try:
        # Passing a list where a BaseModel is expected — that's a shape bug,
        # not a "tool returned nothing" failure.
        _Outer.model_validate(["not", "a", "dict"])  # type: ignore[arg-type]
    except ValidationError as exc:
        assert is_truncated_output_error(exc) is False
    else:
        pytest.fail("expected ValidationError")
