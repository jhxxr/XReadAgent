# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure-Python wrapper around BabelDOC's ``async_translate``.

This module is the boundary between our event protocol (``events.py``) and
BabelDOC's own emitted dicts. The actual ``babeldoc`` package is imported
**lazily** inside the worker function so machines without the heavy ML deps
can still import the rest of XReadAgent.

Architecture:

::

    BabelDOC                   our adapter                     our protocol
    --------                   -----------                     ------------
    async_translate            iter_translation_events()       TranslationEvent
    (yields dicts)             yields StageEvent/Finish/Error  (serialized to WS)

The adapter also exposes :func:`make_translator` — a factory that turns a
LangChain ``chat`` model into the ``Callable[[str, str, str], str]`` shape
BabelDOC expects for its ``translator`` config slot. The chat model is the
only place LangChain leaks into ``xreadagent.translation`` (the layering
rule is explicitly relaxed in :file:`.trellis/spec/backend/quality-guidelines.md`
for this package — translation needs a chat client just like the agent
layer does).

Real-time streaming: ``_build_babeldoc_source`` runs BabelDOC's async
generator inside a dedicated thread that owns its own asyncio loop, pushing
each yielded dict onto a synchronous ``queue.Queue`` as it arrives. The
outer iterator pulls events from the queue without ever calling
``asyncio.run`` itself, so the worker subprocess sees each event within
milliseconds of BabelDOC emitting it (rather than after the whole pipeline
finishes, as the prior buffered implementation did).

Warmup: before kicking off the translation we call
``babeldoc.format.pdf.high_level.init()`` (cheap, creates cache dir) and
``babeldoc.assets.assets.async_warmup()`` (downloads ~80 MB of ONNX + fonts
on first run; idempotent on subsequent runs). During warmup we install a
scoped monkey-patch on ``babeldoc.assets.assets.httpx.AsyncClient`` so each
file download surfaces as ``model_download_*`` events on the same queue.
The patch is restored in a try/finally so it cannot leak.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xreadagent.translation.babeldoc_meta import installed_babeldoc_version
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
    babeldoc_version: str = field(default_factory=installed_babeldoc_version)
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
    ``async_translate`` from a background-thread asyncio loop via
    :func:`_build_babeldoc_source`, which exposes a synchronous iterator
    that the subprocess worker can pump onto a multiprocessing queue.
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
    # actually loaded. ``async_translate`` is BabelDOC 0.6.2's actual streaming
    # entry point — earlier draft code referenced a ``do_translate_async_stream``
    # symbol that does not exist in 0.6.2.
    from babeldoc.format.pdf.high_level import (
        async_translate,
    )
    from babeldoc.format.pdf.high_level import (
        init as _babeldoc_init,
    )

    _babeldoc_init()
    last_stage: StageName | None = None
    start = time.monotonic()
    finish_seen = False
    try:
        # Async path: warmup + stream are both async, so we run them inline.
        async for raw in _async_warmup_with_progress():
            event, last_stage = _convert_event(raw, last_stage=last_stage)
            if event is None:
                continue
            yield event
            if isinstance(event, ErrorEvent):
                return
        # Build the TranslationConfig AFTER warmup so the ONNX model file is
        # on disk when ``DocLayoutModel.load_onnx()`` reads it.
        bcfg = _build_translation_config(config, translator)
        async for raw in async_translate(bcfg):
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


def _build_translation_config(
    config: AdapterConfig,
    translator: Callable[[str, str, str], str],
) -> Any:
    """Construct a real ``babeldoc.format.pdf.translation_config.TranslationConfig``.

    Wraps the user's ``Callable[[str, str, str], str]`` into a
    :class:`BaseTranslator` subclass (BabelDOC's actual config type) and
    loads the ONNX layout model from disk via ``DocLayoutModel.load_onnx()``
    — both required arguments of ``TranslationConfig.__init__``.

    Must be called AFTER warmup so the ONNX model file is on disk when
    ``load_onnx()`` looks for it.
    """
    from babeldoc.docvision.base_doclayout import DocLayoutModel
    from babeldoc.format.pdf.translation_config import TranslationConfig

    layout_model = DocLayoutModel.load_onnx()
    bcfg_translator = _make_base_translator(
        translator, config.source_lang, config.target_lang
    )
    return TranslationConfig(
        translator=bcfg_translator,
        input_file=str(config.input_path),
        lang_in=config.source_lang,
        lang_out=config.target_lang,
        doc_layout_model=layout_model,
        output_dir=str(config.output_dir),
        no_mono=config.no_mono,
        no_dual=config.no_dual,
        **config.extra,
    )


def _make_base_translator(
    callback: Callable[[str, str, str], str],
    lang_in: str,
    lang_out: str,
) -> Any:
    """Adapt a ``Callable[[str, str, str], str]`` into BabelDOC's ``BaseTranslator``.

    BabelDOC 0.6.2 requires the ``translator`` config slot to be a
    :class:`babeldoc.translator.translator.BaseTranslator` instance (not a
    plain callable). We construct the wrapper class lazily inside this
    function so importing the adapter module does not pull babeldoc; the
    class is fresh per call which keeps the rest of the adapter framework-
    agnostic at import time.

    Callers (worker subprocess, integration test) only need to provide a
    ``def translate(text, src, dst) -> str``; they should not have to know
    about BabelDOC's class hierarchy or its cache plumbing.
    """
    from babeldoc.translator.translator import BaseTranslator

    class _CallableTranslator(BaseTranslator):  # type: ignore[misc]
        # ``name`` must be ≤ 20 chars — see BabelDOC's TranslationCache schema.
        name = "xreadagent"

        def __init__(self) -> None:
            super().__init__(lang_in, lang_out, ignore_cache=True)
            self._callback = callback
            # ``model`` is referenced by BaseTranslator.__str__; pin a stable
            # constant so logs don't crash.
            self.model = "callable"

        def do_translate(self, text: str, rate_limit_params: Any = None) -> str:
            _ = rate_limit_params
            return self._callback(text, self.lang_in, self.lang_out)

        def do_llm_translate(self, text: str, rate_limit_params: Any = None) -> str:
            return self.do_translate(text, rate_limit_params)

    return _CallableTranslator()


def _build_babeldoc_source(
    config: AdapterConfig,
    translator: Callable[[str, str, str], str],
) -> Iterator[dict[str, Any]]:
    """Stream BabelDOC events from a background-thread asyncio loop.

    BabelDOC's API is async-only, so we drive ``async_translate`` from a
    daemon thread that owns its own ``asyncio.new_event_loop()`` and push
    each yielded dict onto a ``queue.Queue`` as it arrives. The outer
    iterator drains the queue synchronously, which means the worker
    subprocess sees each event within milliseconds of BabelDOC emitting
    it.

    The loop is **private to the thread** — pytest's event-loop policy is
    not affected because we never call ``asyncio.run`` from the caller's
    context, and the loop is closed in a finally before the thread exits.

    Warmup runs first (downloading ~80 MB of assets on first translate; a
    no-op on subsequent runs because BabelDOC caches them in
    ``~/.cache/babeldoc/``). During warmup we install a scoped monkey-patch
    on ``babeldoc.assets.assets.httpx.AsyncClient`` so each file download
    surfaces as ``model_download_*`` events on the same queue. The patch is
    restored on exit so it never leaks across translations or tests.

    Order matters: ``init()`` → warmup (assets land on disk) → load ONNX
    layout model → build ``TranslationConfig`` → ``async_translate``.
    Constructing the config before warmup would crash because
    ``DocLayoutModel.load_onnx()`` reads the file warmup just downloaded.
    """
    import queue as _queue
    import threading as _threading

    from babeldoc.format.pdf.high_level import (
        init as _babeldoc_init,
    )

    # Cheap (creates the cache dir if missing). Idempotent across runs.
    _babeldoc_init()

    event_queue: _queue.Queue[Any] = _queue.Queue()

    def _on_progress(payload: dict[str, Any]) -> None:
        event_queue.put(payload)

    def _runner() -> None:
        import asyncio as _asyncio

        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_drive(config, translator, _on_progress))
        finally:
            try:
                loop.close()
            finally:
                event_queue.put(_THREAD_DONE)

    thread = _threading.Thread(target=_runner, daemon=True, name="babeldoc-stream")
    thread.start()

    while True:
        item = event_queue.get()
        if item is _THREAD_DONE:
            return
        if isinstance(item, dict):
            yield item


# Sentinel placed on the queue when the worker thread is done. Using a
# module-level object means ``is``-comparison is safe and uniquely identifies
# the end-of-stream condition without colliding with any dict payload.
_THREAD_DONE = object()


async def _drive(
    config: AdapterConfig,
    translator: Callable[[str, str, str], str],
    on_progress: Callable[[dict[str, Any]], None],
) -> None:
    """Run warmup → build config → translate, pushing each dict to ``on_progress``.

    Runs inside the background thread's asyncio loop. Any exception is
    caught and surfaced as an ``error`` event so the consumer sees a
    terminal state instead of a silent thread death.
    """
    from babeldoc.format.pdf.high_level import async_translate

    try:
        async for raw in _async_warmup_with_progress():
            on_progress(raw)
        bcfg = _build_translation_config(config, translator)
        async for raw in async_translate(bcfg):
            if isinstance(raw, dict):
                on_progress(raw)
    except Exception as exc:  # noqa: BLE001 — error boundary inside the thread
        on_progress(
            {
                "type": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "details": _truncate(traceback.format_exc(), _TRACEBACK_MAX_CHARS),
            }
        )


async def _async_warmup_with_progress() -> AsyncIterator[dict[str, Any]]:
    """Run BabelDOC's ``async_warmup`` with per-file download events.

    Yields raw BabelDOC-shaped dicts (``model_download_start`` /
    ``_progress`` / ``_done``) as each individual asset download begins
    and completes, so the caller can push them onto the same queue as
    stage events without waiting for the whole warmup to finish.

    Emits no per-file events when the assets are already on disk
    (BabelDOC's own cache short-circuits the httpx calls entirely — the
    monkey-patched client is never instantiated for those paths).

    Implementation: monkey-patches ``babeldoc.assets.assets.httpx.AsyncClient``
    with a thin subclass that records every ``.get()`` call via an
    ``asyncio.Queue``. The patch is scoped — installed before
    ``async_warmup()`` runs and unconditionally restored in a try/finally
    so it can't leak into other code paths.

    BabelDOC 0.6.2 does **not** stream chunks — it calls
    ``await client.get(url)`` and then reads ``response.content`` in a
    single blocking step. Per-byte chunk progress is therefore not
    achievable without forking BabelDOC; we emit one ``_start`` per file
    request and one ``_done`` per response so the UI sees each download
    individually ticking. ``bytes_total`` comes from the response's
    ``content-length`` header when present.
    """
    import asyncio as _asyncio

    from babeldoc.assets import assets as _assets

    event_q: _asyncio.Queue[dict[str, Any] | object] = _asyncio.Queue()
    _WARMUP_DONE = object()

    original_client_cls = _assets.httpx.AsyncClient

    class _InstrumentedClient(original_client_cls):  # type: ignore[misc, valid-type]
        async def get(self, url: Any, *args: Any, **kwargs: Any) -> Any:
            asset_name = _asset_name_from_url(url)
            await event_q.put(
                {
                    "type": "model_download_start",
                    "asset": asset_name,
                }
            )
            response = await super().get(url, *args, **kwargs)
            try:
                content_length = response.headers.get("content-length")
                bytes_total = int(content_length) if content_length else None
            except (TypeError, ValueError):
                bytes_total = None
            try:
                bytes_downloaded = len(response.content)
            except Exception:  # noqa: BLE001
                bytes_downloaded = None
            await event_q.put(
                {
                    "type": "model_download_progress",
                    "asset": asset_name,
                    "bytes_downloaded": bytes_downloaded,
                    "bytes_total": bytes_total,
                }
            )
            await event_q.put(
                {
                    "type": "model_download_done",
                    "asset": asset_name,
                }
            )
            return response

    yield {"type": "model_download_start", "asset": "engine assets"}

    _assets.httpx.AsyncClient = _InstrumentedClient

    async def _runner() -> None:
        try:
            await _assets.async_warmup()
        except Exception as exc:  # noqa: BLE001
            await event_q.put(
                {
                    "type": "error",
                    "error": f"warmup failed: {type(exc).__name__}: {exc}",
                    "details": _truncate(
                        traceback.format_exc(), _TRACEBACK_MAX_CHARS
                    ),
                }
            )
        finally:
            await event_q.put(_WARMUP_DONE)

    task = _asyncio.create_task(_runner())
    saw_error = False
    try:
        while True:
            item = await event_q.get()
            if item is _WARMUP_DONE:
                break
            assert isinstance(item, dict)
            if item.get("type") == "error":
                saw_error = True
            yield item
    finally:
        _assets.httpx.AsyncClient = original_client_cls
        # Ensure the runner is fully awaited so any pending exception
        # surfaces here rather than leaking as an "unretrieved task".
        try:
            await task
        except Exception:  # noqa: BLE001 — already surfaced via event queue
            pass

    if not saw_error:
        yield {"type": "model_download_done", "asset": "engine assets"}


def _asset_name_from_url(url: Any) -> str:
    """Pick a stable display name out of an httpx URL.

    Used by the warmup wrapper to label each ``model_download_*`` event.
    Falls back to ``"asset"`` for shapes we can't introspect — better a
    constant than a crash inside the monkey-patch.
    """
    try:
        text = str(url)
    except Exception:  # noqa: BLE001
        return "asset"
    if not text:
        return "asset"
    # Strip query string, keep last path segment.
    cleaned = text.split("?", 1)[0]
    segment = cleaned.rsplit("/", 1)[-1]
    return segment or "asset"


__all__ = [
    "AdapterConfig",
    "aiter_translation_events",
    "iter_translation_events",
    "make_translator",
]
