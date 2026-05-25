# SPDX-License-Identifier: AGPL-3.0-or-later
"""WebSocket event schemas for the translation subsystem.

Per Q3 decision in ``prd.md``: the wire format is a discriminated union of
stage / model-download / finish / error events. Each event carries a
``type`` literal that the frontend uses to dispatch.

Casing convention (resolved at the boundary of state-JSON vs in-process):

- The ``type`` *values* are snake_case **protocol tokens** (``stage_start``,
  ``model_download_progress``, ``finish``). These mirror BabelDOC's own
  vocabulary, so we keep them stable across the wire.
- Field *names* (``bytes_downloaded``, ``traceback_excerpt``) are snake_case
  because these are in-process Python schemas that get serialized to JSON
  for the WS stream — they are NOT written to a state-JSON sidecar where
  the camelCase rule would apply.

If a future iteration persists buffered events to a job log under ``state/``
(e.g. for replay after a sidecar restart), that file gets a camelCase
mirror schema; the in-process protocol shape stays as-is.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    """Return ``YYYY-MM-DDTHH:MM:SSZ`` — the canonical UTC stamp format."""
    return (
        datetime.now(tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


# BabelDOC's 13-stage pipeline collapsed onto stable protocol tokens. Sub-stages
# the engine emits (e.g. ``ParagraphFinder``, ``StylesAndFormulas``) are
# normalised by the adapter into the closest canonical stage so the frontend
# can render a fixed checklist instead of an evolving one.
StageName = Literal[
    "loading",
    "parsing",
    "ocr",
    "layout",
    "translation",
    "typesetting",
    "rendering",
    "saving",
    "finalize",
]


class StageEvent(_Strict):
    """One of ``stage_start`` / ``stage_progress`` / ``stage_end``."""

    type: Literal["stage_start", "stage_progress", "stage_end"]
    stage: StageName
    page: int | None = None
    percent: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: str


class ModelDownloadEvent(_Strict):
    """Lazy first-run asset download progress events.

    Emitted before ``stage_start parsing`` on the very first translation.
    Subsequent jobs (model already on disk) skip these entirely.
    """

    type: Literal[
        "model_download_start", "model_download_progress", "model_download_done"
    ]
    asset: str
    bytes_downloaded: int | None = None
    bytes_total: int | None = None
    ts: str


class FinishEvent(_Strict):
    """Terminal success event. Carries final mono / dual paths."""

    type: Literal["finish"] = "finish"
    mono_path: str | None = None
    dual_path: str | None = None
    duration_s: float
    cached: bool = False
    ts: str


class ErrorEvent(_Strict):
    """Terminal failure event.

    ``traceback_excerpt`` is truncated upstream (in ``babeldoc_adapter``) to
    keep the WS payload bounded; consumers that want a full trace must
    inspect the sidecar process stderr.
    """

    type: Literal["error"] = "error"
    stage: str | None = None
    message: str
    traceback_excerpt: str | None = None
    ts: str


TranslationEvent = Union[StageEvent, ModelDownloadEvent, FinishEvent, ErrorEvent]


__all__ = [
    "ErrorEvent",
    "FinishEvent",
    "ModelDownloadEvent",
    "StageEvent",
    "StageName",
    "TranslationEvent",
    "utc_now_iso",
]
