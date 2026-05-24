# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured-output contract for one query pass.

The query agent navigates the wiki (read-only) and emits a ``QueryAnswer``
describing the answer plus the evidence trail. The agent code is what writes
that answer to ``wiki/queries/{topic}/{date}-{slug}.md`` — the LLM output
itself stays pure data so the apply step is unit-testable without an LLM.

D4 (``plan.md`` §11): query results are isolated. ``QueryAnswer`` carries no
diffs to ``papers/`` / ``concepts/`` / ``index.md`` / ``log.md``. Promotion
into the main wiki happens only through ``/crystallize``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Literal["high", "medium", "low"]
RetrievalLayer = Literal["index", "papers", "concepts", "extracts", "search"]


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class CitedEvidence(_Strict):
    """A single piece of evidence backing the answer.

    ``source_wiki_path`` points at a wiki page (``papers/{slug}.md`` or
    ``concepts/{slug}.md``); the agent may quote verbatim or paraphrase.
    """

    source_wiki_path: str
    quote: str
    confidence: Confidence


class QueryAnswer(_Strict):
    """Complete structured-output contract for one query."""

    question: str
    answer_markdown: str
    evidence: list[CitedEvidence] = Field(default_factory=list)
    sources_cited: list[str] = Field(default_factory=list)
    layers_used: list[RetrievalLayer] = Field(default_factory=list)
    confidence: Confidence = "medium"
    open_questions_raised: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


__all__ = [
    "CitedEvidence",
    "Confidence",
    "QueryAnswer",
    "RetrievalLayer",
]
