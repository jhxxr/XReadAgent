# SPDX-License-Identifier: AGPL-3.0-or-later
"""Source manifest schemas (``state/sources.json``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Source(_Strict):
    """One row in the workspace's source manifest."""

    id: str
    title: str
    slug: str
    kind: str = ""
    sourcePath: str = ""
    contentHash: str
    ingestedAt: str = ""
    pageCount: int = 0
    extractPath: str = ""
    lastError: str = ""


class SourcesManifest(_Strict):
    """Top-level container persisted to ``state/sources.json``."""

    workspaceId: str = ""
    sources: list[Source] = Field(default_factory=list)
