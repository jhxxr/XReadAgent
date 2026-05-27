# SPDX-License-Identifier: AGPL-3.0-or-later
"""Real-engine smoke test for the BabelDOC translation adapter.

Runs the actual ``babeldoc==0.6.2`` engine — including ``init()`` +
``async_warmup()`` + a one-page round-trip through ``async_translate`` —
against a synthetic PDF generated at runtime. No LLM call, no network for
translation (the identity translator returns the input unchanged).

Opt-in only::

    pytest -m babeldoc backend/tests/integration/

First run downloads ~80 MB of model + font assets from BabelDOC's
upstream mirrors into ``~/.cache/babeldoc/``; subsequent runs hit the
cache and finish in a few seconds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from xreadagent.translation.babeldoc_adapter import (
    AdapterConfig,
    iter_translation_events,
)
from xreadagent.translation.events import (
    ErrorEvent,
    FinishEvent,
    StageEvent,
    TranslationEvent,
)

pytestmark = pytest.mark.babeldoc


def _identity_translator(text: str, src: str, dst: str) -> str:
    """No-op translator — returns the input text unchanged.

    Avoids hitting any LLM provider so the test is reproducible without
    API keys and isolates "does the engine itself work" from "does our
    LLM gateway work".
    """
    _ = src
    _ = dst
    return text


def _make_synthetic_pdf(target: Path) -> None:
    """Generate a minimal one-page PDF with real text content.

    pymupdf is already an installed transitive dependency of babeldoc,
    so no extra dependency is introduced. Writing a real text element
    ensures BabelDOC has paragraphs to detect rather than skipping the
    document as a blank page.
    """
    import pymupdf  # type: ignore[import-not-found]

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world. This is a test.", fontsize=12)
    doc.save(str(target))
    doc.close()


def test_real_translate_smoke(tmp_path: Path) -> None:
    """End-to-end: warmup + translate + dual PDF lands on disk.

    Asserts (in order):
    - The adapter does not raise.
    - At least one ``stage_start`` event fires (proves real-time streaming
      is wired correctly — the buffered implementation would have produced
      no events until the whole pipeline finished).
    - Exactly one ``FinishEvent`` is emitted with a non-empty ``dual_path``.
    - The ``dual_path`` file exists on disk and has at least one page.
    - No ``ErrorEvent`` slipped through (warmup or translate failure).
    """
    source = tmp_path / "smoke.pdf"
    _make_synthetic_pdf(source)
    output_dir = tmp_path / "translations"
    output_dir.mkdir()

    config = AdapterConfig(
        input_path=source,
        output_dir=output_dir,
        target_lang="zh",
        source_lang="en",
        no_mono=True,
        no_dual=False,
    )

    events: list[TranslationEvent] = []
    for event in iter_translation_events(config, _identity_translator):
        events.append(event)

    # No error events.
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert not errors, f"unexpected error events: {[e.message for e in errors]}"

    # Stage events arrived — proves the queue/thread streaming worked.
    stage_starts = [
        e for e in events if isinstance(e, StageEvent) and e.type == "stage_start"
    ]
    assert stage_starts, "expected at least one stage_start event, got none"

    # Exactly one finish event with a usable dual path.
    finishes = [e for e in events if isinstance(e, FinishEvent)]
    assert len(finishes) == 1, f"expected one FinishEvent, got {len(finishes)}"
    finish = finishes[0]
    assert finish.dual_path, "finish event missing dual_path"

    dual = Path(finish.dual_path)
    assert dual.exists(), f"dual PDF not on disk: {dual}"

    # The output is a real, openable PDF with >= 1 page.
    import pymupdf  # type: ignore[import-not-found]

    out_doc = pymupdf.open(str(dual))
    try:
        assert out_doc.page_count >= 1
    finally:
        out_doc.close()


def test_warmup_monkeypatch_restores_httpx_async_client() -> None:
    """The scoped monkey-patch on ``httpx.AsyncClient`` must be torn down.

    Runs the warmup helper directly (without translating anything) and
    verifies that ``babeldoc.assets.assets.httpx.AsyncClient`` is the
    original class after the helper returns.

    This proves the try/finally restoration works even when warmup
    completes successfully — guarding against a regression where the
    patch leaks into subsequent tests / translations and silently
    instruments unrelated httpx clients.
    """
    import asyncio

    from babeldoc.assets import assets as _assets

    from xreadagent.translation.babeldoc_adapter import (
        _async_warmup_with_progress,
    )

    original = _assets.httpx.AsyncClient

    async def _drain() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        async for evt in _async_warmup_with_progress():
            out.append(evt)
        return out

    _ = asyncio.run(_drain())

    assert _assets.httpx.AsyncClient is original, (
        "scoped monkey-patch did not restore the original httpx.AsyncClient"
    )
