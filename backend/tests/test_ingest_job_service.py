# SPDX-License-Identifier: AGPL-3.0-or-later
"""Service-level tests for :class:`xreadagent.api.ingest_jobs.IngestJobService`.

The runner is injected (no agent / LLM / converter), mirroring how
``test_translation_service.py`` stubs the worker. Covers:

- Phase callbacks become ordered ``stage_start`` / ``stage_end`` events with
  a terminal ``finish`` carrying the ingest result.
- Unknown phase tokens are ignored (forward compatibility).
- Runner exceptions surface as a terminal ``error`` event AND an
  ``ingest_error`` record in ``state/conversation-log.jsonl``.
- Input validation in ``start_ingest`` (missing file / not a file).
- Late subscribers replay the buffered event history.
- Unknown job ids raise ``KeyError`` from ``event_stream``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from xreadagent.api.ingest_jobs import (
    IngestEvent,
    IngestJobRequest,
    IngestJobService,
)
from xreadagent.wiki.workspace import Workspace


def _fake_result(
    *, slug: str = "alpha-aaaaaaaaaaaa", title: str = "Alpha", cache_hit: bool = False
) -> Any:
    return SimpleNamespace(
        source=SimpleNamespace(slug=slug, title=title),
        cache_hit=cache_hit,
        files_touched=["wiki/papers/alpha-aaaaaaaaaaaa.md"],
        duration_s=3.25,
    )


def _make_runner(
    phases: list[str], outcome: Any
) -> Callable[..., Any]:
    async def _runner(
        workspace: Workspace,
        request: IngestJobRequest,
        *,
        on_phase: Callable[[str], None],
    ) -> Any:
        for phase in phases:
            on_phase(phase)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return _runner


def _request(tmp_path: Path) -> IngestJobRequest:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.4\nfake")
    return IngestJobRequest(
        workspace_path=tmp_path,
        file_path=source,
        model="anthropic:claude-fake",
    )


async def _collect(service: IngestJobService, job_id: str) -> list[IngestEvent]:
    return [event async for event in service.event_stream(job_id)]


def test_success_emits_stage_events_then_finish(tmp_path: Path) -> None:
    runner = _make_runner(["converting", "analyzing", "writing"], _fake_result())
    service = IngestJobService(runner=runner, poll_interval=0.01)
    job_id = service.start_ingest(_request(tmp_path))

    events = asyncio.run(_collect(service, job_id))

    kinds = [(e.type, getattr(e, "stage", None)) for e in events]
    assert kinds == [
        ("stage_start", "converting"),
        ("stage_end", "converting"),
        ("stage_start", "analyzing"),
        ("stage_end", "analyzing"),
        ("stage_start", "writing"),
        ("stage_end", "writing"),
        ("finish", None),
    ]
    finish = events[-1]
    assert finish.type == "finish"
    assert finish.slug == "alpha-aaaaaaaaaaaa"
    assert finish.title == "Alpha"
    assert finish.cache_hit is False
    assert finish.files_touched == ["wiki/papers/alpha-aaaaaaaaaaaa.md"]
    assert finish.duration_s == pytest.approx(3.25)


def test_cache_hit_finish_skips_llm_stages(tmp_path: Path) -> None:
    """A cache hit only reports the converting phase before finishing."""
    runner = _make_runner(["converting"], _fake_result(cache_hit=True))
    service = IngestJobService(runner=runner, poll_interval=0.01)
    job_id = service.start_ingest(_request(tmp_path))

    events = asyncio.run(_collect(service, job_id))

    assert [e.type for e in events] == ["stage_start", "stage_end", "finish"]
    finish = events[-1]
    assert finish.type == "finish"
    assert finish.cache_hit is True


def test_unknown_phase_tokens_are_ignored(tmp_path: Path) -> None:
    runner = _make_runner(["converting", "mystery-phase"], _fake_result())
    service = IngestJobService(runner=runner, poll_interval=0.01)
    job_id = service.start_ingest(_request(tmp_path))

    events = asyncio.run(_collect(service, job_id))

    stages = [getattr(e, "stage", None) for e in events if e.type == "stage_start"]
    assert stages == ["converting"]


def test_runner_failure_emits_error_event_and_logs(tmp_path: Path) -> None:
    runner = _make_runner(["converting"], RuntimeError("planner exploded"))
    service = IngestJobService(runner=runner, poll_interval=0.01)
    job_id = service.start_ingest(_request(tmp_path))

    events = asyncio.run(_collect(service, job_id))

    terminal = events[-1]
    assert terminal.type == "error"
    assert "RuntimeError: planner exploded" in terminal.message
    assert terminal.stage == "converting"

    log_path = Workspace.at(tmp_path).conversation_log_path
    assert log_path.exists()
    records = [json.loads(line) for line in log_path.read_text("utf-8").splitlines()]
    error_records = [r for r in records if r["event"] == "ingest_error"]
    assert len(error_records) == 1
    assert error_records[0]["job_id"] == job_id
    assert "planner exploded" in error_records[0]["message"]


def test_start_ingest_rejects_missing_file(tmp_path: Path) -> None:
    service = IngestJobService(runner=_make_runner([], _fake_result()))
    request = IngestJobRequest(
        workspace_path=tmp_path,
        file_path=tmp_path / "missing.pdf",
        model="m",
    )
    with pytest.raises(FileNotFoundError):
        service.start_ingest(request)


def test_start_ingest_rejects_directory(tmp_path: Path) -> None:
    service = IngestJobService(runner=_make_runner([], _fake_result()))
    directory = tmp_path / "a-directory"
    directory.mkdir()
    request = IngestJobRequest(
        workspace_path=tmp_path, file_path=directory, model="m"
    )
    with pytest.raises(ValueError, match="not a regular file"):
        service.start_ingest(request)


def test_late_subscriber_replays_buffered_events(tmp_path: Path) -> None:
    runner = _make_runner(["converting", "analyzing", "writing"], _fake_result())
    service = IngestJobService(runner=runner, poll_interval=0.01)
    job_id = service.start_ingest(_request(tmp_path))

    first_pass = asyncio.run(_collect(service, job_id))
    second_pass = asyncio.run(_collect(service, job_id))

    assert [e.type for e in second_pass] == [e.type for e in first_pass]
    assert second_pass[-1].type == "finish"


def test_unknown_job_id_raises_key_error(tmp_path: Path) -> None:
    service = IngestJobService(runner=_make_runner([], _fake_result()))
    with pytest.raises(KeyError):
        asyncio.run(_collect(service, "no-such-job"))
