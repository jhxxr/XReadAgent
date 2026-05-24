# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-source distillation JSON — ``state/by-source/{slug}.json``.

This is the audit/recompile substrate (per ``plan.md`` §2.3): the wiki
``papers/{slug}.md`` is human-readable but the JSON sidecar is what lets us
re-render the wiki when templates change without re-LLM-ing every paper.

The shape mirrors OpenSciReader's ``WorkspaceKnowledgeBySourcePayload`` so
state is wire-compatible if a workspace is ever migrated.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from xreadagent.schemas.entities import Claim, Entity, Relation, Task
from xreadagent.schemas.sources import Source
from xreadagent.wiki.atomic import atomic_write_text
from xreadagent.wiki.workspace import Workspace


class DistillationPayload(BaseModel):
    """One paper's worth of LLM-distilled entities/claims/relations/tasks."""

    model_config = ConfigDict(strict=True, extra="forbid")

    source: Source
    entities: list[Entity] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)


def load_distillation(workspace: Workspace, slug: str) -> DistillationPayload | None:
    path = workspace.state_by_source_dir / f"{slug}.json"
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return None
    return DistillationPayload.model_validate_json(raw)


def save_distillation(workspace: Workspace, slug: str, payload: DistillationPayload) -> None:
    path = workspace.state_by_source_dir / f"{slug}.json"
    data = payload.model_dump(mode="json")
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    atomic_write_text(path, text)
