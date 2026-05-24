# SPDX-License-Identifier: AGPL-3.0-or-later
"""``DistillationPayload`` save / load round-trip."""

from __future__ import annotations

from pathlib import Path

from xreadagent.schemas.entities import Claim, Entity, Relation, SourceRef, Task
from xreadagent.schemas.sources import Source
from xreadagent.wiki.distillation import (
    DistillationPayload,
    load_distillation,
    save_distillation,
)
from xreadagent.wiki.workspace import Workspace


def test_load_distillation_returns_none_when_missing(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    assert load_distillation(workspace, "missing-slug") is None


def test_distillation_round_trip(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")

    payload = DistillationPayload(
        source=Source(
            id="src-1",
            title="A Paper",
            slug="a-paper-deadbeef0000",
            contentHash="deadbeef",
        ),
        entities=[Entity(id="ent-1", title="Transformer")],
        claims=[
            Claim(
                id="c-1",
                title="Self-attention scales linearly",
                entityIds=["ent-1"],
                sourceRefs=[SourceRef(sourceId="src-1", pageStart=2, pageEnd=2)],
            )
        ],
        relations=[Relation(id="r-1", type="uses", fromId="ent-1", toId="ent-1")],
        tasks=[Task(id="t-1", title="Why does attention need positional encoding?")],
    )

    save_distillation(workspace, "a-paper-deadbeef0000", payload)
    loaded = load_distillation(workspace, "a-paper-deadbeef0000")

    assert loaded == payload
