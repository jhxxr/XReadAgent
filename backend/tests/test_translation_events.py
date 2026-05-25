# SPDX-License-Identifier: AGPL-3.0-or-later
"""Translation event schema tests — strict mode, discriminator typing."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from xreadagent.translation.events import (
    ErrorEvent,
    FinishEvent,
    ModelDownloadEvent,
    StageEvent,
    utc_now_iso,
)


def test_utc_now_iso_format() -> None:
    ts = utc_now_iso()
    # YYYY-MM-DDTHH:MM:SSZ — 20 chars, ends with Z.
    assert len(ts) == 20
    assert ts.endswith("Z")
    assert "T" in ts


def test_stage_event_minimal() -> None:
    event = StageEvent(type="stage_start", stage="parsing", ts="2026-01-01T00:00:00Z")
    payload = event.model_dump(mode="json")
    assert payload["type"] == "stage_start"
    assert payload["stage"] == "parsing"
    assert payload["payload"] == {}


def test_stage_event_with_page_and_percent() -> None:
    event = StageEvent(
        type="stage_progress",
        stage="translation",
        page=3,
        percent=42.5,
        payload={"foo": "bar"},
        ts="2026-01-01T00:00:00Z",
    )
    assert event.page == 3
    assert event.percent == pytest.approx(42.5)
    assert event.payload == {"foo": "bar"}


def test_stage_event_rejects_unknown_stage() -> None:
    with pytest.raises(ValidationError):
        StageEvent(type="stage_start", stage="bogus", ts="t")  # type: ignore[arg-type]


def test_stage_event_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        StageEvent(type="finish", stage="parsing", ts="t")  # type: ignore[arg-type]


def test_stage_event_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        StageEvent(  # type: ignore[call-arg]
            type="stage_start",
            stage="parsing",
            ts="t",
            mystery="forbidden",
        )


def test_model_download_event_optional_byte_counts() -> None:
    event = ModelDownloadEvent(
        type="model_download_start", asset="layout-yolo", ts="t"
    )
    assert event.bytes_downloaded is None
    assert event.bytes_total is None


def test_model_download_event_with_bytes() -> None:
    event = ModelDownloadEvent(
        type="model_download_progress",
        asset="layout-yolo",
        bytes_downloaded=1024,
        bytes_total=4096,
        ts="t",
    )
    assert event.bytes_downloaded == 1024
    assert event.bytes_total == 4096


def test_finish_event_defaults() -> None:
    event = FinishEvent(duration_s=12.3, ts="t")
    assert event.type == "finish"
    assert event.cached is False
    assert event.mono_path is None
    assert event.dual_path is None


def test_finish_event_with_paths() -> None:
    event = FinishEvent(
        mono_path="translations/x.mono.pdf",
        dual_path="translations/x.dual.pdf",
        duration_s=1.0,
        cached=True,
        ts="t",
    )
    payload = event.model_dump(mode="json")
    assert payload["mono_path"] == "translations/x.mono.pdf"
    assert payload["cached"] is True


def test_error_event_optional_fields() -> None:
    event = ErrorEvent(message="boom", ts="t")
    assert event.stage is None
    assert event.traceback_excerpt is None


def test_error_event_with_stage_and_trace() -> None:
    event = ErrorEvent(
        stage="parsing",
        message="oops",
        traceback_excerpt="Traceback (most recent call last):\n  ...",
        ts="t",
    )
    assert event.stage == "parsing"
    assert "Traceback" in (event.traceback_excerpt or "")
