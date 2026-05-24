# SPDX-License-Identifier: AGPL-3.0-or-later
"""Strict-mode validation tests for ``QueryAnswer`` and ``CitedEvidence``."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from xreadagent.agents.query_schema import CitedEvidence, QueryAnswer


def test_cited_evidence_rejects_unknown_confidence() -> None:
    with pytest.raises(ValidationError):
        CitedEvidence(
            source_wiki_path="papers/foo.md",
            quote="quote",
            confidence="excellent",  # type: ignore[arg-type]
        )


def test_cited_evidence_accepts_all_three_levels() -> None:
    for level in ("high", "medium", "low"):
        evidence = CitedEvidence(
            source_wiki_path="papers/foo.md", quote="q", confidence=level
        )
        assert evidence.confidence == level


def test_query_answer_strict_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        QueryAnswer.model_validate(
            {
                "question": "q",
                "answer_markdown": "a",
                "evidence": [],
                "sources_cited": [],
                "layers_used": [],
                "extra_field": "not allowed",
            }
        )


def test_query_answer_defaults_are_safe() -> None:
    answer = QueryAnswer(question="q", answer_markdown="a")
    assert answer.evidence == []
    assert answer.sources_cited == []
    assert answer.layers_used == []
    assert answer.confidence == "medium"
    assert answer.open_questions_raised == []
    assert answer.notes == []


def test_query_answer_rejects_unknown_layer() -> None:
    with pytest.raises(ValidationError):
        QueryAnswer.model_validate(
            {
                "question": "q",
                "answer_markdown": "a",
                "evidence": [],
                "sources_cited": [],
                "layers_used": ["index", "vector-store"],
            }
        )


def test_query_answer_round_trip_json() -> None:
    original = QueryAnswer(
        question="What does the transformer paper claim about WMT-14?",
        answer_markdown="It reports BLEU 28.4 — see [[papers/attention-deadbeef]].",
        evidence=[
            CitedEvidence(
                source_wiki_path="papers/attention-deadbeef.md",
                quote="BLEU 28.4 on WMT-14",
                confidence="high",
            )
        ],
        sources_cited=["papers/attention-deadbeef.md"],
        layers_used=["index", "papers"],
        confidence="high",
        open_questions_raised=["What about WMT-15?"],
        notes=["Verified against extract."],
    )
    raw = original.model_dump_json()
    restored = QueryAnswer.model_validate_json(raw)
    assert restored == original
    # Also round-trip via dict.
    restored_dict = QueryAnswer.model_validate(json.loads(raw))
    assert restored_dict == original
