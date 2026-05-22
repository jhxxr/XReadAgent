# SPDX-License-Identifier: AGPL-3.0-or-later
"""Frontmatter schemas for the three first-class wiki page types.

Borrowed from ``obsidian-paper-curator`` page templates (see
``research/llm-wiki-prior-art.md`` § "Page templates"):

- Paper page  — seven body sections; frontmatter records provenance + reliability.
- Concept page — aggregates aliases for entity disambiguation.
- Query page  — records which retrieval layers were consulted and which sources cited.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


Reliability = Literal["high", "medium", "low"]


class PaperFrontmatter(_Strict):
    page_type: Literal["paper"] = "paper"
    title: str
    source: str
    source_hash: str
    doi: str = ""
    year: int = 0
    authors: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    reliability: Reliability = "medium"


class ConceptFrontmatter(_Strict):
    page_type: Literal["concept"] = "concept"
    title: str
    aliases: list[str] = Field(default_factory=list)
    type: str = ""


class QueryFrontmatter(_Strict):
    page_type: Literal["query"] = "query"
    question: str
    date: str
    layers_used: list[str] = Field(default_factory=list)
    sources_cited: list[str] = Field(default_factory=list)
