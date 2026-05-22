# SPDX-License-Identifier: AGPL-3.0-or-later
"""Core knowledge types ported from OpenSciReader ``workspace_knowledge_types.go``.

Four categories — Entity, Claim, Relation, Task — each with a uniform
``sourceRefs`` provenance contract. Fields match the Go JSON tags so
``state/by-source/{slug}.json`` artifacts are wire-compatible if we ever
migrate workspaces between the two implementations.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class SourceRef(_Strict):
    """A single citation pointer: source id, page range, short excerpt."""

    sourceId: str
    pageStart: int = 0
    pageEnd: int = 0
    excerpt: str = ""


class Entity(_Strict):
    """A canonical concept page — one per ``concepts/{slug}.md``."""

    id: str
    workspaceId: str = ""
    title: str
    type: str = ""
    summary: str = ""
    aliases: list[str] = Field(default_factory=list)
    sourceRefs: list[SourceRef] = Field(default_factory=list)
    origin: str = ""
    status: str = ""
    confidence: float = 0.0
    createdAt: str = ""
    updatedAt: str = ""


class Claim(_Strict):
    """A factual assertion bound to one or more entities."""

    id: str
    workspaceId: str = ""
    title: str
    type: str = ""
    summary: str = ""
    entityIds: list[str] = Field(default_factory=list)
    sourceRefs: list[SourceRef] = Field(default_factory=list)
    origin: str = ""
    status: str = ""
    confidence: float = 0.0
    createdAt: str = ""
    updatedAt: str = ""


class Relation(_Strict):
    """A typed edge between two entities."""

    id: str
    workspaceId: str = ""
    type: str
    fromId: str
    toId: str
    summary: str = ""
    sourceRefs: list[SourceRef] = Field(default_factory=list)
    origin: str = ""
    status: str = ""
    confidence: float = 0.0
    createdAt: str = ""
    updatedAt: str = ""


class Task(_Strict):
    """An open question / follow-up surfaced by ingest, aggregated in open-questions.md."""

    id: str
    workspaceId: str = ""
    title: str
    type: str = ""
    summary: str = ""
    priority: str = ""
    sourceRefs: list[SourceRef] = Field(default_factory=list)
    origin: str = ""
    status: str = ""
    confidence: float = 0.0
    createdAt: str = ""
    updatedAt: str = ""
