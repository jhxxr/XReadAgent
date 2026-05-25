# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure-Python wrapper around BabelDOC's ``do_translate_async_stream``.

This module is the boundary between our event protocol (``events.py``) and
BabelDOC's own emitted dicts. The actual ``babeldoc`` package is imported
**lazily** inside the worker function so machines without the heavy ML deps
can still import the rest of XReadAgent.

Architecture:

::

    BabelDOC                   our adapter                     our protocol
    --------                   -----------                     ------------
    do_translate_async_stream  iter_translation_events()       TranslationEvent
    (yields dicts)             yields StageEvent/Finish/Error  (serialized to WS)

The adapter also exposes :func:`make_translator` — a factory that turns a
LangChain ``chat`` model into the ``Callable[[str, str, str], str]`` shape
BabelDOC expects for its ``translator`` config slot. The chat model is the
only place LangChain leaks into ``xreadagent.translation`` (the layering
rule is explicitly relaxed in :file:`.trellis/spec/backend/quality-guidelines.md`
for this package — translation needs a chat client just like the agent
layer does).
"""

from __future__ import annotations

import time
import traceback
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xreadagent.translation.events import (
    ErrorEvent,
    FinishEvent,
    ModelDownloadEvent,
    StageEvent,
    StageName,
    TranslationEvent,
    utc_now_iso,
)

# Mapping from BabelDOC's stage names to our canonical 9-token stage vocabulary.
# Keep keys lowercase — we lower the upstream value before lookup.
_STAGE_MAP: dict[str, StageName] = {
    "loading": "loading",
    "parsing": "parsing",
    "parse": "parsing",
    "parsepdf": "parsing",
    "detectscannedfile": "ocr",
    "ocr": "ocr",
    "layoutparser": "layout",
    "layout": "layout",
    "tableparser": "layout",
    "paragraphfinder": "layout",
    "stylesandformulas": "layout",
    "automatictermextractor": "translation",
    "iltranslator": "translation",
    "translate": "translation",
    "translation": "translation",
    "typesetting": "typesetting",
    "typeset": "typesetting",
    "fontmapper": "typesetting",
    "pdfcreater": "rendering",
    "rendering": "rendering",
    "render": "rendering",
    "subset font": "rendering",
    "subsetfont": "rendering",
    "save pdf": "saving",
    "savepdf": "saving",
    "saving": "saving",
    "save": "saving",
    "finalize": "finalize",
    "finalise": "finalize",
}

_TRACEBACK_MAX_CHARS = 2000


def _normalise_stage(name: str | None) -> StageName | None:
    """Coerce a BabelDOC stage string into our canonical enum.

    Returns ``None`` when the upstream value is missing — callers fall back
    to the previous stage or skip the event.
    """
    if not name:
        return None
    key = name.strip().lower()
    if key in _STAGE_MAP:
        return _STAGE_MAP[key]
    # Fallback: collapse to the closest match by substring. Order matters —
    # check most specific keys first.
    for needle, target in _STAGE_MAP.items():
        if needle in key:
            return target
    return None


@dataclass(frozen=True)
class AdapterConfig:
    """Inputs the adapter needs to call BabelDOC.

    Kept as a plain dataclass so it remains picklable for the
    ProcessPoolExecutor handoff in :mod:`xreadagent.translation.worker`.
    """

    input_path: Path
    output_dir: Path
    target_lang: str = "zh"
    source_lang: str = "en"
    no_mono: bool = False
    no_dual: bool = False
    babeldoc_version: str = "0.6.2"
    extra: dict[str, Any] = field(default_factory=dict)


def _extract_chat_text(raw: Any) -> str:
    """Pull the textual body out of whatever the chat model returned.

    LangChain ``invoke`` typically returns an ``AIMessage`` with a ``content``
    attribute that may be a string OR a list of content blocks. We handle
    both shapes plus the plain-string case some fakes use in tests.

    Duplicated here (instead of importing from ``agents.json_planner``) because
    the layering rule forbids ``translation/`` from importing ``agents/``.
    """
    if isinstance(raw, str):
        return raw
    content = getattr(raw, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if isinstance(block, dict):
                text_field = block.get("text")
                if isinstance(text_field, str):
                    parts.append(text_field)
        return "".join(parts)
    return str(raw)


def make_translator(chat: Any) -> Callable[[str, str, str], str]:
    """Adapt a LangChain ``chat`` model into BabelDOC's translator callable.

    BabelDOC expects ``Callable[[text, source_lang, target_lang], translated_text]``.
    We send a minimal "translate only, no commentary" prompt and extract the
    text using the same content-block walker the agents use, so chat models
    that emit list-of-blocks (Anthropic) and string-content (OpenAI) both work.
    """

    def _translate(text: str, src: str, dst: str) -> str:
        prompt = (
            f"Translate the following text from {src} to {dst}. "
            "Return only the translation — no preamble, no commentary, no "
            "markdown formatting beyond what is in the source.\n\n"
            f"{text}"
        )
        raw = chat.invoke(prompt)
        return _extract_chat_text(raw).strip()

    return _translate


def _convert_event(
    raw: dict[str, Any], *, last_stage: StageName | None
) -> tuple[TranslationEvent | None, StageName | None]:
    """Translate one BabelDOC event dict into a :class:`TranslationEvent`.

    Returns ``(event, new_last_stage)`` — ``event`` may be ``None`` for
    events we deliberately skip (unknown stage, no useful payload).
    """
    raw_type = str(raw.get("type") or "").strip().lower()
    stage_raw = raw.get("stage") or raw.get("stage_name") or raw.get("name")
    stage = _normalise_stage(stage_raw if isinstance(stage_raw, str) else None)
    if stage is None:
        stage = last_stage
    ts = utc_now_iso()

    # Engine-asset download events.
    if raw_type in {"model_download_start", "model_download_progress", "model_download_done"}:
        asset = str(raw.get("asset") or raw.get("name") or "asset")
        bytes_done = _coerce_int(raw.get("bytes_downloaded") or raw.get("downloaded"))
        bytes_total = _coerce_int(raw.get("bytes_total") or raw.get("total"))
        return (
            ModelDownloadEvent(
                type=raw_type,  # type: ignore[arg-type]
                asset=asset,
                bytes_downloaded=bytes_done,
                bytes_total=bytes_total,
                ts=ts,
            ),
            stage,
        )

    # Terminal events surfaced by BabelDOC.
    if raw_type == "finish":
        result = raw.get("translate_result") or {}
        mono = _result_path(result, "mono_pdf_path") or _coerce_str(raw.get("mono_path"))
        dual = _result_path(result, "dual_pdf_path") or _coerce_str(raw.get("dual_path"))
        duration = _coerce_float(raw.get("duration_s") or raw.get("total_seconds")) or 0.0
        return (
            FinishEvent(
                mono_path=mono,
                dual_path=dual,
                duration_s=duration,
                ts=ts,
            ),
            stage,
        )
    if raw_type == "error":
        message = str(raw.get("error") or raw.get("message") or "unknown error")
        details = raw.get("details")
        excerpt = (
            _truncate(str(details), _TRACEBACK_MAX_CHARS) if details else None
        )
        return (
            ErrorEvent(
                stage=stage,
                message=message,
                traceback_excerpt=excerpt,
                ts=ts,
            ),
            stage,
        )

    # Stage lifecycle events. BabelDOC uses ``progress_start`` / ``_update`` /
    # ``_end`` — translate them into our canonical names.
    if raw_type in {"progress_start", "stage_start"}:
        if stage is None:
            return None, last_stage
        return (
            StageEvent(
                type="stage_start",
                stage=stage,
                page=_coerce_int(raw.get("page") or raw.get("page_idx")),
                percent=_coerce_float(raw.get("stage_progress") or raw.get("percent")),
                payload=_keep_payload(raw),
                ts=ts,
            ),
            stage,
        )
    if raw_type in {"progress_update", "stage_progress"}:
        if stage is None:
            return None, last_stage
        return (
            StageEvent(
                type="stage_progress",
                stage=stage,
                page=_coerce_int(raw.get("page") or raw.get("page_idx")),
                percent=_coerce_float(
                    raw.get("overall_progress")
                    or raw.get("stage_progress")
                    or raw.get("percent")
                ),
                payload=_keep_payload(raw),
                ts=ts,
            ),
            stage,
        )
    if raw_type in {"progress_end", "stage_end"}:
        if stage is None:
            return None, last_stage
        return (
            StageEvent(
                type="stage_end",
                stage=stage,
                page=_coerce_int(raw.get("page") or raw.get("page_idx")),
                percent=_coerce_float(
                    raw.get("stage_progress") or raw.get("percent")
                ),
                payload=_keep_payload(raw),
                ts=ts,
            ),
            stage,
        )

    return None, last_stage


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _result_path(result: Any, key: str) -> str | None:
    """Pull ``key`` out of a ``TranslateResult`` (dataclass or dict)."""
    if result is None:
        return None
    if isinstance(result, dict):
        value = result.get(key)
    else:
        value = getattr(result, key, None)
    if value is None:
        return None
    return str(value)


def _keep_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Surface a stable subset of BabelDOC's event payload to the frontend.

    Drops the keys we explicitly model (``type``, ``stage``, ``page``,
    ``percent``) plus heavyweight fields (``translate_result``) so the WS
    payload stays small. Anything else passes through for debug visibility.
    """
    drop = {
        "type",
        "stage",
        "stage_name",
        "name",
        "page",
        "page_idx",
        "percent",
        "stage_progress",
        "overall_progress",
        "translate_result",
        "error",
        "message",
        "details",
        "duration_s",
        "total_seconds",
    }
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key in drop:
            continue
        # Best-effort JSON-friendliness; non-serializables become ``str``.
        if isinstance(value, (str, int, float, bool, type(None), list, dict)):
            out[key] = value
        else:
            out[key] = str(value)
    return out


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


def iter_translation_events(
    config: AdapterConfig,
    translator: Callable[[str, str, str], str],
    *,
    raw_event_source: Iterator[dict[str, Any]] | None = None,
) -> Iterator[TranslationEvent]:
    """Yield :class:`TranslationEvent` for one BabelDOC translation.

    ``raw_event_source`` exists for tests — when provided, the adapter
    consumes that iterator instead of importing / invoking BabelDOC. The
    production code path imports BabelDOC lazily and drives
    ``do_translate_async_stream`` through ``asyncio.run`` to keep this
    function synchronous (it runs inside the subprocess worker, not the
    sidecar event loop).
    """
    start = time.monotonic()
    last_stage: StageName | None = None
    finish_seen = False
    if raw_event_source is None:
        raw_event_source = _build_babeldoc_source(config, translator)
    try:
        for raw in raw_event_source:
            event, last_stage = _convert_event(raw, last_stage=last_stage)
            if event is None:
                continue
            if isinstance(event, FinishEvent):
                finish_seen = True
                # Surface engine duration if BabelDOC didn't report one.
                if event.duration_s <= 0.0:
                    event = event.model_copy(
                        update={"duration_s": time.monotonic() - start}
                    )
            yield event
            if isinstance(event, ErrorEvent):
                return
    except Exception as exc:  # noqa: BLE001 — adapter is the error boundary
        yield ErrorEvent(
            stage=last_stage,
            message=f"{type(exc).__name__}: {exc}",
            traceback_excerpt=_truncate(traceback.format_exc(), _TRACEBACK_MAX_CHARS),
            ts=utc_now_iso(),
        )
        return
    if not finish_seen:
        # BabelDOC closed the stream without a finish event — synthesize one
        # so consumers can complete cleanly. Paths are read from disk by the
        # service layer when the adapter omits them.
        yield FinishEvent(
            mono_path=None,
            dual_path=None,
            duration_s=time.monotonic() - start,
            ts=utc_now_iso(),
        )


async def aiter_translation_events(
    config: AdapterConfig,
    translator: Callable[[str, str, str], str],
) -> AsyncIterator[TranslationEvent]:
    """Async variant — wraps the BabelDOC async generator directly.

    Used by the FastAPI WS handler in tests with stub adapters; the worker
    subprocess uses the synchronous ``iter_translation_events`` because it
    consumes a generator inside a single subprocess and ships dicts back
    over a multiprocessing queue.
    """
    # Lazy import keeps the worker subprocess as the only place BabelDOC is
    # actually loaded.
    from babeldoc.format.pdf.high_level import (
        do_translate_async_stream,
    )
    from babeldoc.format.pdf.translation_config import (
        TranslationConfig,
    )

    bcfg = TranslationConfig(
        input_file=str(config.input_path),
        output_dir=str(config.output_dir),
        lang_in=config.source_lang,
        lang_out=config.target_lang,
        no_mono=config.no_mono,
        no_dual=config.no_dual,
        translator=translator,
        **config.extra,
    )
    last_stage: StageName | None = None
    start = time.monotonic()
    finish_seen = False
    try:
        async for raw in do_translate_async_stream(bcfg):
            event, last_stage = _convert_event(raw, last_stage=last_stage)
            if event is None:
                continue
            if isinstance(event, FinishEvent):
                finish_seen = True
                if event.duration_s <= 0.0:
                    event = event.model_copy(
                        update={"duration_s": time.monotonic() - start}
                    )
            yield event
            if isinstance(event, ErrorEvent):
                return
    except Exception as exc:  # noqa: BLE001
        yield ErrorEvent(
            stage=last_stage,
            message=f"{type(exc).__name__}: {exc}",
            traceback_excerpt=_truncate(traceback.format_exc(), _TRACEBACK_MAX_CHARS),
            ts=utc_now_iso(),
        )
        return
    if not finish_seen:
        yield FinishEvent(
            mono_path=None,
            dual_path=None,
            duration_s=time.monotonic() - start,
            ts=utc_now_iso(),
        )


def _build_babeldoc_source(
    config: AdapterConfig,
    translator: Callable[[str, str, str], str],
) -> Iterator[dict[str, Any]]:
    """Synchronous bridge to BabelDOC's async generator.

    Runs the async stream to completion inside the calling subprocess. The
    BabelDOC API is async-only, so we drive it through ``asyncio.run`` and
    return a synchronous iterator the worker can pump into a
    ``multiprocessing.Queue`` one dict at a time.

    Implementation detail: we collect dicts into a buffer rather than
    yielding from inside the async loop because mixing async + sync
    generator semantics across the asyncio bridge is fragile under pytest's
    event-loop policy. This is fine — BabelDOC's stream has tens of events
    per page, not millions.
    """
    import asyncio

    from babeldoc.format.pdf.high_level import (
        do_translate_async_stream,
    )
    from babeldoc.format.pdf.translation_config import (
        TranslationConfig,
    )

    bcfg = TranslationConfig(
        input_file=str(config.input_path),
        output_dir=str(config.output_dir),
        lang_in=config.source_lang,
        lang_out=config.target_lang,
        no_mono=config.no_mono,
        no_dual=config.no_dual,
        translator=translator,
        **config.extra,
    )

    async def _collect() -> list[dict[str, Any]]:
        buffer: list[dict[str, Any]] = []
        async for raw in do_translate_async_stream(bcfg):
            if isinstance(raw, dict):
                buffer.append(raw)
        return buffer

    events = asyncio.run(_collect())
    return iter(events)


__all__ = [
    "AdapterConfig",
    "aiter_translation_events",
    "iter_translation_events",
    "make_translator",
]
