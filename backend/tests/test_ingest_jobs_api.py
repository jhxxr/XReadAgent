# SPDX-License-Identifier: AGPL-3.0-or-later
"""``POST /api/ingest`` job flow + ``/ws/jobs/{job_id}`` tests.

Mirrors ``test_translate_api.py``: the app is wired through a stub
:class:`IngestJobService` so no agent/LLM ever runs. Asserts:

- ``POST /api/ingest`` returns a ``jobId`` immediately and forwards the
  resolved model/workspace/file into the service request.
- ``/ws/jobs/{job_id}`` streams the ingest events in order.
- Service-level ``FileNotFoundError`` surfaces as 422.
- The shared WS channel still resolves translation jobs when both services
  are wired (ingest by-job map wins only for its own job ids).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient, WebSocketDisconnect

from xreadagent.api.ingest_jobs import (
    IngestEvent,
    IngestFinishEvent,
    IngestJobRequest,
    IngestStageEvent,
)
from xreadagent.api.main import create_app
from xreadagent.translation.events import utc_now_iso

_JOB_ID = "ingest-job-1"


class _StubIngestService:
    """Stand-in :class:`IngestJobService` for endpoint tests."""

    def __init__(self, events: list[IngestEvent]) -> None:
        self.events_seq = events
        self.requests: list[IngestJobRequest] = []

    def start_ingest(self, request: IngestJobRequest) -> str:
        self.requests.append(request)
        return _JOB_ID

    async def event_stream(self, job_id: str) -> AsyncIterator[IngestEvent]:
        if job_id != _JOB_ID:
            raise KeyError(f"unknown job_id: {job_id}")
        for event in self.events_seq:
            yield event
            await asyncio.sleep(0)


def _make_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "paper.pdf"
    p.write_bytes(b"%PDF-1.4\nfake")
    return p


def _canned() -> list[IngestEvent]:
    ts = utc_now_iso()
    return [
        IngestStageEvent(type="stage_start", stage="converting", ts=ts),
        IngestStageEvent(type="stage_end", stage="converting", ts=ts),
        IngestStageEvent(type="stage_start", stage="analyzing", ts=ts),
        IngestStageEvent(type="stage_end", stage="analyzing", ts=ts),
        IngestFinishEvent(
            slug="alpha-aaaaaaaaaaaa",
            title="Alpha Paper",
            cache_hit=False,
            files_touched=["wiki/papers/alpha-aaaaaaaaaaaa.md"],
            duration_s=12.5,
            ts=ts,
        ),
    ]


def test_post_register_starts_register_mode_job(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path)
    stub = _StubIngestService(_canned())
    client = TestClient(create_app(ingest_service=stub))  # type: ignore[arg-type]
    response = client.post(
        "/api/sources/register",
        json={
            "workspacePath": str(tmp_path),
            "filePath": str(pdf),
            "title": "Alpha Paper",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"jobId": _JOB_ID}
    assert len(stub.requests) == 1
    req = stub.requests[0]
    assert req.mode == "register"
    assert req.model == ""  # register needs no model
    assert req.file_path == pdf
    assert req.title == "Alpha Paper"


def test_post_register_missing_file_is_422(tmp_path: Path) -> None:
    stub = _StubIngestService(_canned())
    client = TestClient(create_app(ingest_service=stub))  # type: ignore[arg-type]
    response = client.post(
        "/api/sources/register",
        json={"workspacePath": str(tmp_path), "filePath": str(tmp_path / "nope.pdf")},
    )
    assert response.status_code == 422


def test_post_build_wiki_resolves_archived_source(tmp_path: Path) -> None:
    from xreadagent.schemas.sources import Source
    from xreadagent.wiki.sources import SourcesIndex
    from xreadagent.wiki.workspace import Workspace

    workspace = Workspace.at(tmp_path / "ws")
    workspace.init_empty("Build")
    workspace.ensure_layout()
    archived = workspace.raw_processed_dir / "alpha-aaa.pdf"
    archived.write_bytes(b"%PDF-1.4\nfake")
    sources = SourcesIndex.load(workspace)
    sources.add_or_update(
        Source(
            id="alpha-aaa",
            title="Alpha",
            slug="alpha-aaa",
            kind="pdf",
            sourcePath="raw/_processed/alpha-aaa.pdf",
            contentHash="h",
            ingestedAt="2026-06-14T00:00:00Z",
            extractPath="extracts/alpha-aaa.md",
        )
    )
    sources.save()

    stub = _StubIngestService(_canned())
    client = TestClient(create_app(ingest_service=stub))  # type: ignore[arg-type]
    response = client.post(
        "/api/sources/alpha-aaa/build",
        json={"workspacePath": str(workspace.root), "model": "anthropic:claude-fake"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"jobId": _JOB_ID}
    req = stub.requests[0]
    assert req.mode == "wiki"
    assert req.file_path == archived
    assert req.title == "Alpha"


def test_post_build_wiki_unknown_slug_is_404(tmp_path: Path) -> None:
    from xreadagent.wiki.workspace import Workspace

    workspace = Workspace.at(tmp_path / "ws")
    workspace.init_empty("Build")
    stub = _StubIngestService(_canned())
    client = TestClient(create_app(ingest_service=stub))  # type: ignore[arg-type]
    response = client.post(
        "/api/sources/ghost/build",
        json={"workspacePath": str(workspace.root), "model": "m"},
    )
    assert response.status_code == 404


def test_post_ingest_returns_job_id(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path)
    stub = _StubIngestService(_canned())
    client = TestClient(create_app(ingest_service=stub))  # type: ignore[arg-type]
    response = client.post(
        "/api/ingest",
        json={
            "workspacePath": str(tmp_path),
            "filePath": str(pdf),
            "model": "anthropic:claude-fake",
            "title": "Alpha Paper",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"jobId": _JOB_ID}
    assert len(stub.requests) == 1
    req = stub.requests[0]
    assert req.file_path == pdf
    assert req.model == "anthropic:claude-fake"
    assert req.title == "Alpha Paper"
    assert req.workspace_path == tmp_path


def test_ws_streams_ingest_events_in_order(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path)
    stub = _StubIngestService(_canned())
    client = TestClient(create_app(ingest_service=stub))  # type: ignore[arg-type]
    started = client.post(
        "/api/ingest",
        json={
            "workspacePath": str(tmp_path),
            "filePath": str(pdf),
            "model": "anthropic:claude-fake",
        },
    )
    assert started.status_code == 200, started.text
    job_id = started.json()["jobId"]

    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        frames = [ws.receive_json() for _ in range(5)]

    assert [f["type"] for f in frames] == [
        "stage_start",
        "stage_end",
        "stage_start",
        "stage_end",
        "finish",
    ]
    assert frames[0]["stage"] == "converting"
    assert frames[2]["stage"] == "analyzing"
    assert frames[4]["slug"] == "alpha-aaaaaaaaaaaa"
    assert frames[4]["title"] == "Alpha Paper"


def test_post_ingest_maps_service_errors_to_422(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path)

    class _Failing(_StubIngestService):
        def start_ingest(self, request: IngestJobRequest) -> str:
            raise FileNotFoundError("file vanished before the job started")

    client = TestClient(create_app(ingest_service=_Failing([])))  # type: ignore[arg-type]
    response = client.post(
        "/api/ingest",
        json={
            "workspacePath": str(tmp_path),
            "filePath": str(pdf),
            "model": "m",
        },
    )
    assert response.status_code == 422
    assert "vanished" in response.text


def test_ws_unknown_job_with_no_translation_service_closes(tmp_path: Path) -> None:
    """No ingest mapping + no translation service → the WS closes (1008)."""
    stub = _StubIngestService(_canned())
    client = TestClient(create_app(ingest_service=stub))  # type: ignore[arg-type]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/jobs/never-started") as ws:
            ws.receive_json()


def test_ingest_jobs_resolve_before_pinned_translation_service(tmp_path: Path) -> None:
    """The ingest by-job map wins for ingest job ids even with a pinned
    translation service; other job ids still fall through to translation."""

    class _TranslationStub:
        async def event_stream(self, job_id: str) -> AsyncIterator[Any]:
            raise KeyError(f"unknown job_id: {job_id}")
            yield  # pragma: no cover — makes this an async generator

    pdf = _make_pdf(tmp_path)
    ingest_stub = _StubIngestService(_canned())
    client = TestClient(
        create_app(
            translation_service=_TranslationStub(),  # type: ignore[arg-type]
            ingest_service=ingest_stub,  # type: ignore[arg-type]
        )
    )
    started = client.post(
        "/api/ingest",
        json={
            "workspacePath": str(tmp_path),
            "filePath": str(pdf),
            "model": "m",
        },
    )
    job_id = started.json()["jobId"]

    # The ingest job streams from the ingest service.
    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        first = ws.receive_json()
    assert first["type"] == "stage_start"

    # An unknown id falls through to the pinned translation service which
    # reports the unknown-job error frame (pre-existing contract).
    with client.websocket_connect("/ws/jobs/some-translate-job") as ws:
        frame = ws.receive_json()
    assert frame["type"] == "error"
    assert "unknown job_id" in frame["message"]
