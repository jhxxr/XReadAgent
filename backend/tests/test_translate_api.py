# SPDX-License-Identifier: AGPL-3.0-or-later
"""``POST /api/translate`` + ``GET /ws/jobs/{job_id}`` tests.

The API is wired through a stub :class:`TranslationService` so we never
spawn a real BabelDOC worker. The stub yields a fixed event sequence so
the test asserts:

- ``POST /api/translate`` returns a ``jobId`` immediately.
- ``/ws/jobs/{job_id}`` streams the events in order.
- Bad workspace / source path returns 422.
- WS for an unknown job_id sends an error frame and closes cleanly.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from xreadagent.api.main import create_app
from xreadagent.translation.events import (
    FinishEvent,
    StageEvent,
    TranslationEvent,
    utc_now_iso,
)
from xreadagent.translation.service import TranslationRequest


class _StubService:
    """Stand-in :class:`TranslationService` for endpoint tests.

    Records the request, returns a fixed ``job_id``, and replays a canned
    event sequence on ``event_stream``. The real service's persistence side
    effects are exercised in ``test_translation_service.py`` — here we only
    care about the FastAPI wiring.
    """

    def __init__(self, events: list[TranslationEvent]) -> None:
        self.events_seq = events
        self.requests: list[TranslationRequest] = []

    def start_translation(self, request: TranslationRequest) -> str:
        self.requests.append(request)
        return "job-123"

    async def event_stream(self, job_id: str) -> AsyncIterator[TranslationEvent]:
        if job_id != "job-123":
            raise KeyError(f"unknown job_id: {job_id}")
        for event in self.events_seq:
            yield event
            # Give the event loop a chance to flush the WS frame.
            await asyncio.sleep(0)


def _make_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "paper.pdf"
    p.write_bytes(b"%PDF-1.4\nfake")
    return p


def _canned() -> list[TranslationEvent]:
    ts = utc_now_iso()
    return [
        StageEvent(type="stage_start", stage="parsing", ts=ts),
        StageEvent(type="stage_end", stage="parsing", ts=ts),
        FinishEvent(
            mono_path="translations/x.mono.pdf",
            dual_path="translations/x.dual.pdf",
            duration_s=1.5,
            ts=ts,
        ),
    ]


def test_post_translate_returns_job_id(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path)
    stub = _StubService(_canned())
    client = TestClient(create_app(translation_service=stub))  # type: ignore[arg-type]
    response = client.post(
        "/api/translate",
        json={
            "workspacePath": str(tmp_path),
            "sourcePath": str(pdf),
            "model": "anthropic:claude-fake",
            "targetLang": "zh",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["jobId"] == "job-123"
    assert len(stub.requests) == 1
    req = stub.requests[0]
    assert req.source_path == pdf
    assert req.target_lang == "zh"
    assert req.model == "anthropic:claude-fake"


def test_post_translate_rejects_missing_source(tmp_path: Path) -> None:
    class _Failing(_StubService):
        def start_translation(self, request: TranslationRequest) -> str:
            raise FileNotFoundError("source not found")

    failing = _Failing(_canned())
    client = TestClient(create_app(translation_service=failing))  # type: ignore[arg-type]
    response = client.post(
        "/api/translate",
        json={
            "workspacePath": str(tmp_path),
            "sourcePath": str(tmp_path / "missing.pdf"),
            "model": "m",
        },
    )
    assert response.status_code == 422
    assert "source not found" in response.text


def test_post_translate_rejects_extra_fields(tmp_path: Path) -> None:
    """Pydantic strict mode rejects unknown body keys (state JSON discipline)."""
    stub = _StubService(_canned())
    client = TestClient(create_app(translation_service=stub))  # type: ignore[arg-type]
    response = client.post(
        "/api/translate",
        json={
            "workspacePath": str(tmp_path),
            "sourcePath": str(tmp_path / "p.pdf"),
            "model": "m",
            "mystery": "forbidden",
        },
    )
    assert response.status_code == 422


def test_ws_streams_events_in_order(tmp_path: Path) -> None:
    stub = _StubService(_canned())
    client = TestClient(create_app(translation_service=stub))  # type: ignore[arg-type]
    with client.websocket_connect("/ws/jobs/job-123") as ws:
        first = ws.receive_json()
        second = ws.receive_json()
        third = ws.receive_json()
    assert first["type"] == "stage_start"
    assert second["type"] == "stage_end"
    assert third["type"] == "finish"
    assert third["mono_path"] == "translations/x.mono.pdf"


def test_ws_streams_events_for_factory_created_service(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path)
    stub = _StubService(_canned())

    def factory(workspace: Any) -> _StubService:
        _ = workspace
        return stub

    client = TestClient(
        create_app(translation_service_factory=factory)  # type: ignore[arg-type]
    )
    response = client.post(
        "/api/translate",
        json={
            "workspacePath": str(tmp_path),
            "sourcePath": str(pdf),
            "model": "anthropic:claude-fake",
            "targetLang": "zh",
        },
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["jobId"]

    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        first = ws.receive_json()
        second = ws.receive_json()
        third = ws.receive_json()

    assert first["type"] == "stage_start"
    assert second["type"] == "stage_end"
    assert third["type"] == "finish"


def test_ws_unknown_job_sends_error_then_closes(tmp_path: Path) -> None:
    stub = _StubService(_canned())
    client = TestClient(create_app(translation_service=stub))  # type: ignore[arg-type]
    with client.websocket_connect("/ws/jobs/does-not-exist") as ws:
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert "unknown job_id" in payload["message"]


def test_translate_endpoint_returns_503_when_no_service_configured(tmp_path: Path) -> None:
    """A fresh app with neither pinned service nor factory rejects translation."""
    client = TestClient(create_app())
    response = client.post(
        "/api/translate",
        json={
            "workspacePath": str(tmp_path),
            "sourcePath": str(tmp_path / "p.pdf"),
            "model": "m",
        },
    )
    assert response.status_code == 503


def test_existing_healthz_and_ws_events_still_work(tmp_path: Path) -> None:
    """The new endpoints didn't break the Phase 1 surface."""
    client = TestClient(create_app())
    health = client.get("/healthz")
    assert health.status_code == 200
    with client.websocket_connect("/ws/events") as ws:
        hello = ws.receive_json()
        assert hello == {"type": "hello"}
        ws.send_text("ping")
        assert ws.receive_text() == "ping"


# Suppress accidental unused-import flake — pytest needs them for fixtures.
_ = (Any, pytest)
