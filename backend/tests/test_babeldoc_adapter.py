# SPDX-License-Identifier: AGPL-3.0-or-later
"""BabelDOC adapter — event translation, error surfacing, and stage mapping.

All tests use the ``raw_event_source`` parameter of
:func:`iter_translation_events` to inject canned BabelDOC-style dicts.
``babeldoc`` is NEVER imported here — that's the whole point of the lazy
import + injectable iterator pattern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from xreadagent.translation.babeldoc_adapter import (
    AdapterConfig,
    iter_translation_events,
    make_translator,
)
from xreadagent.translation.events import (
    ErrorEvent,
    FinishEvent,
    ModelDownloadEvent,
    StageEvent,
)


def _config(tmp_path: Path) -> AdapterConfig:
    src = tmp_path / "paper.pdf"
    src.write_bytes(b"%PDF-1.4 not actually a pdf")
    return AdapterConfig(
        input_path=src,
        output_dir=tmp_path / "translations",
    )


def _fake_translator(text: str, src: str, dst: str) -> str:
    return f"[{src}->{dst}] {text}"


def _collect(events: Iterator[Any]) -> list[Any]:
    return list(events)


def test_adapter_maps_progress_lifecycle(tmp_path: Path) -> None:
    raw = iter(
        [
            {"type": "progress_start", "stage": "Parsing", "stage_total": 10},
            {
                "type": "progress_update",
                "stage": "Parsing",
                "stage_progress": 50.0,
                "overall_progress": 5.0,
            },
            {"type": "progress_end", "stage": "Parsing", "stage_progress": 100.0},
            {
                "type": "finish",
                "translate_result": {
                    "mono_pdf_path": "/tmp/x.mono.pdf",
                    "dual_pdf_path": "/tmp/x.dual.pdf",
                },
                "total_seconds": 9.5,
            },
        ]
    )

    events = _collect(
        iter_translation_events(_config(tmp_path), _fake_translator, raw_event_source=raw)
    )
    types = [e.type for e in events]
    assert types == ["stage_start", "stage_progress", "stage_end", "finish"]
    assert isinstance(events[0], StageEvent)
    assert events[0].stage == "parsing"
    assert events[1].percent == 5.0
    finish = events[-1]
    assert isinstance(finish, FinishEvent)
    assert finish.mono_path == "/tmp/x.mono.pdf"
    assert finish.dual_path == "/tmp/x.dual.pdf"
    # ``total_seconds`` is the BabelDOC name we accept.
    assert finish.duration_s == 9.5


def test_adapter_maps_sub_stage_names(tmp_path: Path) -> None:
    """BabelDOC's sub-stage names collapse onto our canonical 9 tokens."""
    raw = iter(
        [
            {"type": "progress_start", "stage": "LayoutParser"},
            {"type": "progress_start", "stage": "ParagraphFinder"},
            {"type": "progress_start", "stage": "ILTranslator"},
            {"type": "progress_start", "stage": "Typesetting"},
            {"type": "progress_start", "stage": "FontMapper"},
            {"type": "progress_start", "stage": "PDFCreater"},
            {"type": "progress_start", "stage": "Save PDF"},
        ]
    )
    events = _collect(
        iter_translation_events(_config(tmp_path), _fake_translator, raw_event_source=raw)
    )
    # All seven map onto the canonical vocabulary, then a synthetic finish appears.
    stage_events = [e for e in events if isinstance(e, StageEvent)]
    assert [e.stage for e in stage_events] == [
        "layout",
        "layout",
        "translation",
        "typesetting",
        "typesetting",
        "rendering",
        "saving",
    ]
    # Synthetic finish at the tail.
    assert isinstance(events[-1], FinishEvent)


def test_adapter_surfaces_model_download_events(tmp_path: Path) -> None:
    raw = iter(
        [
            {"type": "model_download_start", "asset": "layout-yolo"},
            {
                "type": "model_download_progress",
                "asset": "layout-yolo",
                "bytes_downloaded": 1024,
                "bytes_total": 4096,
            },
            {"type": "model_download_done", "asset": "layout-yolo"},
            {"type": "finish", "total_seconds": 1.0},
        ]
    )
    events = _collect(
        iter_translation_events(_config(tmp_path), _fake_translator, raw_event_source=raw)
    )
    download = [e for e in events if isinstance(e, ModelDownloadEvent)]
    assert [e.type for e in download] == [
        "model_download_start",
        "model_download_progress",
        "model_download_done",
    ]
    assert download[1].bytes_downloaded == 1024
    assert download[1].bytes_total == 4096


def test_adapter_surfaces_error_event(tmp_path: Path) -> None:
    raw = iter(
        [
            {"type": "progress_start", "stage": "OCR"},
            {
                "type": "error",
                "error": "subprocess crashed",
                "details": "Traceback ...",
                "stage": "OCR",
            },
        ]
    )
    events = _collect(
        iter_translation_events(_config(tmp_path), _fake_translator, raw_event_source=raw)
    )
    assert any(isinstance(e, ErrorEvent) for e in events)
    err = [e for e in events if isinstance(e, ErrorEvent)][0]
    assert "subprocess crashed" in err.message
    assert err.stage == "ocr"
    # Adapter must STOP after an error event — no further events follow.
    error_index = next(i for i, e in enumerate(events) if isinstance(e, ErrorEvent))
    assert error_index == len(events) - 1


def test_adapter_catches_iterator_exception(tmp_path: Path) -> None:
    """A raising ``raw_event_source`` becomes a synthetic ErrorEvent."""

    def _bad_source() -> Iterator[dict[str, Any]]:
        yield {"type": "progress_start", "stage": "Parsing"}
        raise RuntimeError("upstream went boom")

    events = _collect(
        iter_translation_events(
            _config(tmp_path), _fake_translator, raw_event_source=_bad_source()
        )
    )
    # We got the stage event + the synthetic error.
    assert isinstance(events[0], StageEvent)
    assert isinstance(events[-1], ErrorEvent)
    assert "upstream went boom" in events[-1].message


def test_adapter_synthesizes_finish_when_stream_ends_silently(tmp_path: Path) -> None:
    raw = iter(
        [
            {"type": "progress_start", "stage": "Parsing"},
            {"type": "progress_end", "stage": "Parsing"},
        ]
    )
    events = _collect(
        iter_translation_events(_config(tmp_path), _fake_translator, raw_event_source=raw)
    )
    assert isinstance(events[-1], FinishEvent)
    # Paths default to None when BabelDOC didn't tell us.
    assert events[-1].mono_path is None
    assert events[-1].dual_path is None


def test_adapter_skips_unknown_event_types(tmp_path: Path) -> None:
    raw = iter(
        [
            {"type": "completely_unknown", "stage": "Parsing"},
            {"type": "progress_start", "stage": "Parsing"},
            {"type": "finish", "total_seconds": 0.1},
        ]
    )
    events = _collect(
        iter_translation_events(_config(tmp_path), _fake_translator, raw_event_source=raw)
    )
    # Unknown event types are silently skipped.
    types = [e.type for e in events]
    assert "stage_start" in types
    assert "finish" in types


def test_make_translator_wires_chat_invoke() -> None:
    """``make_translator`` returns a callable that calls ``chat.invoke``."""

    class _FakeChat:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def invoke(self, prompt: str) -> Any:
            self.calls.append(prompt)
            return "translated body"

    chat = _FakeChat()
    translator = make_translator(chat)
    out = translator("hello", "en", "zh")
    assert out == "translated body"
    assert len(chat.calls) == 1
    assert "from en to zh" in chat.calls[0]
    assert "hello" in chat.calls[0]


def test_make_translator_handles_anthropic_content_blocks() -> None:
    """LangChain's list-of-blocks content shape is correctly unwrapped."""

    class _Msg:
        content = [{"type": "text", "text": "Salut"}, {"type": "text", "text": " monde"}]

    class _FakeChat:
        def invoke(self, prompt: str) -> Any:
            return _Msg()

    translator = make_translator(_FakeChat())
    out = translator("Hello world", "en", "fr")
    assert out == "Salut monde"
