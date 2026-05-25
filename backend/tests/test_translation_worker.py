# SPDX-License-Identifier: AGPL-3.0-or-later
"""``AsyncTranslationWorker`` tests using the in-thread runner.

The real worker spawns a subprocess via ``multiprocessing.get_context("spawn")``;
tests inject ``thread_runner`` which executes the worker entry-point in a
background thread of the test process. Same queue contract, but cheap.

We do NOT exercise the BabelDOC import / engine; instead, we monkey-patch
``_worker_entry``'s helpers so the worker pushes pre-built event dicts.
"""

from __future__ import annotations

import asyncio
import queue
from pathlib import Path
from typing import Any

import pytest

from xreadagent.translation.babeldoc_adapter import AdapterConfig
from xreadagent.translation.events import (
    ErrorEvent,
    FinishEvent,
    ModelDownloadEvent,
    StageEvent,
    utc_now_iso,
)
from xreadagent.translation.worker import (
    _DONE,
    AsyncTranslationWorker,
    ChatConfig,
    WorkerJobConfig,
    thread_runner,
)


def _adapter(tmp_path: Path) -> AdapterConfig:
    src = tmp_path / "x.pdf"
    src.write_bytes(b"%PDF-1.4 ...")
    return AdapterConfig(input_path=src, output_dir=tmp_path / "out")


def _chat() -> ChatConfig:
    return ChatConfig(model="anthropic:claude-fake")


async def _drain(worker: AsyncTranslationWorker, job_id: str) -> list[Any]:
    items: list[Any] = []
    async for event in worker.events(job_id):
        items.append(event)
    return items


def _make_worker_with_canned_events(
    monkeypatch: pytest.MonkeyPatch, events: list[dict[str, Any]]
) -> AsyncTranslationWorker:
    """Patch the worker entry to push ``events`` onto the queue then signal done."""

    def fake_entry(
        config: WorkerJobConfig, event_queue: "queue.Queue[Any]"
    ) -> None:
        for evt in events:
            event_queue.put(evt)
        event_queue.put(_DONE)

    monkeypatch.setattr(
        "xreadagent.translation.worker._worker_entry", fake_entry
    )
    return AsyncTranslationWorker(
        runner=thread_runner, queue_factory=lambda: queue.Queue()
    )


async def test_worker_yields_events_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ts = utc_now_iso()
    canned = [
        StageEvent(type="stage_start", stage="parsing", ts=ts).model_dump(mode="json"),
        StageEvent(
            type="stage_progress", stage="parsing", percent=50.0, ts=ts
        ).model_dump(mode="json"),
        StageEvent(type="stage_end", stage="parsing", ts=ts).model_dump(mode="json"),
        FinishEvent(
            mono_path="translations/x.mono.pdf",
            dual_path="translations/x.dual.pdf",
            duration_s=1.0,
            ts=ts,
        ).model_dump(mode="json"),
    ]
    worker = _make_worker_with_canned_events(monkeypatch, canned)
    job_id = worker.start(
        WorkerJobConfig(adapter=_adapter(tmp_path), chat=_chat(), job_id="job-1")
    )

    events = await _drain(worker, job_id)
    assert [e.type for e in events] == [
        "stage_start",
        "stage_progress",
        "stage_end",
        "finish",
    ]
    assert isinstance(events[-1], FinishEvent)
    assert events[-1].mono_path == "translations/x.mono.pdf"


async def test_worker_surfaces_model_download_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ts = utc_now_iso()
    canned = [
        ModelDownloadEvent(
            type="model_download_start", asset="layout-yolo", ts=ts
        ).model_dump(mode="json"),
        ModelDownloadEvent(
            type="model_download_progress",
            asset="layout-yolo",
            bytes_downloaded=1024,
            bytes_total=4096,
            ts=ts,
        ).model_dump(mode="json"),
        ModelDownloadEvent(
            type="model_download_done", asset="layout-yolo", ts=ts
        ).model_dump(mode="json"),
        FinishEvent(duration_s=0.1, ts=ts).model_dump(mode="json"),
    ]
    worker = _make_worker_with_canned_events(monkeypatch, canned)
    job_id = worker.start(
        WorkerJobConfig(adapter=_adapter(tmp_path), chat=_chat(), job_id="dl")
    )
    events = await _drain(worker, job_id)
    download_types = [e.type for e in events if isinstance(e, ModelDownloadEvent)]
    assert download_types == [
        "model_download_start",
        "model_download_progress",
        "model_download_done",
    ]


async def test_worker_terminates_on_error_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ts = utc_now_iso()
    canned = [
        StageEvent(type="stage_start", stage="parsing", ts=ts).model_dump(mode="json"),
        ErrorEvent(stage="parsing", message="boom", ts=ts).model_dump(mode="json"),
    ]
    worker = _make_worker_with_canned_events(monkeypatch, canned)
    job_id = worker.start(
        WorkerJobConfig(adapter=_adapter(tmp_path), chat=_chat(), job_id="err")
    )
    events = await _drain(worker, job_id)
    assert [e.type for e in events] == ["stage_start", "error"]


async def test_worker_concurrent_jobs_are_demuxed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two simultaneous jobs each see only their own events.

    The thread runner's per-job queue gives natural isolation — this test
    asserts the API exposes that isolation correctly.
    """
    ts = utc_now_iso()

    call_count = {"n": 0}

    def fake_entry(
        config: WorkerJobConfig, event_queue: "queue.Queue[Any]"
    ) -> None:
        idx = call_count["n"]
        call_count["n"] += 1
        event_queue.put(
            StageEvent(
                type="stage_start",
                stage="parsing",
                payload={"job_idx": idx, "job_id": config.job_id},
                ts=ts,
            ).model_dump(mode="json")
        )
        event_queue.put(FinishEvent(duration_s=0.1, ts=ts).model_dump(mode="json"))
        event_queue.put(_DONE)

    monkeypatch.setattr(
        "xreadagent.translation.worker._worker_entry", fake_entry
    )
    worker = AsyncTranslationWorker(
        runner=thread_runner, queue_factory=lambda: queue.Queue()
    )

    job_a = worker.start(
        WorkerJobConfig(adapter=_adapter(tmp_path), chat=_chat(), job_id="A")
    )
    job_b = worker.start(
        WorkerJobConfig(adapter=_adapter(tmp_path), chat=_chat(), job_id="B")
    )

    a_events, b_events = await asyncio.gather(_drain(worker, job_a), _drain(worker, job_b))
    a_payloads = [e.payload for e in a_events if isinstance(e, StageEvent)]
    b_payloads = [e.payload for e in b_events if isinstance(e, StageEvent)]
    a_ids = {p["job_id"] for p in a_payloads}
    b_ids = {p["job_id"] for p in b_payloads}
    assert a_ids == {"A"}
    assert b_ids == {"B"}


async def test_worker_buffer_replays_for_late_subscriber(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once a job finishes, a late ``events`` call still yields the buffer.

    This is the contract the FastAPI WS handler relies on when the client
    reconnects after a brief dropout.
    """
    ts = utc_now_iso()
    canned = [
        StageEvent(type="stage_start", stage="parsing", ts=ts).model_dump(mode="json"),
        FinishEvent(duration_s=0.1, ts=ts).model_dump(mode="json"),
    ]
    worker = _make_worker_with_canned_events(monkeypatch, canned)
    job_id = worker.start(
        WorkerJobConfig(adapter=_adapter(tmp_path), chat=_chat(), job_id="late")
    )

    # First subscriber drains everything.
    first = await _drain(worker, job_id)
    assert len(first) == 2

    # Second subscriber gets a replay of the buffer.
    second = await _drain(worker, job_id)
    assert [e.type for e in second] == ["stage_start", "finish"]


async def test_worker_handles_unknown_job_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = _make_worker_with_canned_events(monkeypatch, [])
    with pytest.raises(KeyError):
        async for _ in worker.events("nonexistent"):
            pass


async def test_worker_drop_removes_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ts = utc_now_iso()
    canned = [FinishEvent(duration_s=0.0, ts=ts).model_dump(mode="json")]
    worker = _make_worker_with_canned_events(monkeypatch, canned)
    job_id = worker.start(
        WorkerJobConfig(adapter=_adapter(tmp_path), chat=_chat(), job_id="d")
    )
    await _drain(worker, job_id)
    worker.drop(job_id)
    assert worker.get_record(job_id) is None
