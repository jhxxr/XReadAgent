# SPDX-License-Identifier: AGPL-3.0-or-later
"""``TranslationService`` orchestrator tests.

We never spawn a real BabelDOC subprocess — every test injects an
``AsyncTranslationWorker`` whose ``_worker_entry`` is patched to emit canned
events. The service-layer assertions cover:

- Cache-hit short-circuit: second call with matching ``(hash, lang, model)``
  returns ``cached=true`` without invoking the worker.
- Manifest and ``state/conversation-log.jsonl`` writes on finish.
- D4-style isolation: the synthesis zone is byte-identical before/after a
  translation. Only ``translations/`` + the log files change.
- Error events feed the conversation log but never touch the manifest.
"""

from __future__ import annotations

import hashlib
import json
import queue
from pathlib import Path
from typing import Any

import pytest

from xreadagent.schemas.wiki_pages import ConceptFrontmatter, PaperFrontmatter
from xreadagent.translation.events import (
    ErrorEvent,
    FinishEvent,
    StageEvent,
    utc_now_iso,
)
from xreadagent.translation.manifest import (
    TranslationsIndex,
)
from xreadagent.translation.service import TranslationRequest, TranslationService
from xreadagent.translation.worker import (
    _DONE,
    AsyncTranslationWorker,
    WorkerJobConfig,
    thread_runner,
)
from xreadagent.wiki.pages import write_concept_page, write_paper_page
from xreadagent.wiki.workspace import Workspace


def _seed_workspace(tmp_path: Path) -> Workspace:
    workspace = Workspace.at(tmp_path / "ws")
    workspace.init_empty("Service Test")
    write_paper_page(
        workspace,
        "alpha-aaa",
        PaperFrontmatter(title="Alpha", source="raw/alpha.pdf", source_hash="aaa"),
        {
            "Background": "alpha bg",
            "Challenges": "ch",
            "Solution": "sol",
            "Positioning": "pos",
            "Key Concepts": "- [[concepts/transformer|Transformer]]",
            "Experiments": "ex",
            "Open Questions": "oq",
        },
    )
    write_concept_page(
        workspace,
        "transformer",
        ConceptFrontmatter(title="Transformer", aliases=["xformer"]),
        {"Summary": "T summary."},
    )
    return workspace


def _make_pdf(tmp_path: Path, name: str = "paper.pdf") -> Path:
    p = tmp_path / "raw" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"%PDF-1.4\nfake pdf bytes for testing")
    return p


def _build_worker_with_events(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, Any]],
    call_counter: dict[str, int] | None = None,
) -> AsyncTranslationWorker:
    def fake_entry(config: WorkerJobConfig, event_queue: "queue.Queue[Any]") -> None:
        if call_counter is not None:
            call_counter["n"] = call_counter.get("n", 0) + 1
        for evt in events:
            event_queue.put(evt)
        event_queue.put(_DONE)

    monkeypatch.setattr("xreadagent.translation.worker._worker_entry", fake_entry)
    return AsyncTranslationWorker(
        runner=thread_runner, queue_factory=lambda: queue.Queue()
    )


async def _drain(service: TranslationService, job_id: str) -> list[Any]:
    out: list[Any] = []
    async for event in service.event_stream(job_id):
        out.append(event)
    return out


def _canned_run(tmp_path: Path, slug: str) -> list[dict[str, Any]]:
    """Produce a complete event stream that ends with the on-disk pdfs."""
    translations_dir = tmp_path / "ws" / "translations"
    translations_dir.mkdir(parents=True, exist_ok=True)
    mono = translations_dir / f"{slug}.mono.pdf"
    dual = translations_dir / f"{slug}.dual.pdf"
    mono.write_bytes(b"%PDF-1.4 mono")
    dual.write_bytes(b"%PDF-1.4 dual")
    ts = utc_now_iso()
    return [
        StageEvent(type="stage_start", stage="parsing", ts=ts).model_dump(mode="json"),
        StageEvent(type="stage_end", stage="parsing", ts=ts).model_dump(mode="json"),
        FinishEvent(
            mono_path=str(mono),
            dual_path=str(dual),
            duration_s=2.5,
            ts=ts,
        ).model_dump(mode="json"),
    ]


# ---------------------------------------------------------------------------
# Happy path: end-to-end translation persists manifest + logs
# ---------------------------------------------------------------------------


async def test_service_writes_manifest_and_logs_on_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _seed_workspace(tmp_path)
    pdf = _make_pdf(workspace.root, "paper.pdf")

    # Build a fixed source hash for the canned events to share with the index.
    from xreadagent.translation.service import _stable_translation_slug

    source_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    slug = _stable_translation_slug(pdf, source_hash)

    worker = _build_worker_with_events(monkeypatch, _canned_run(tmp_path, slug))
    service = TranslationService(workspace, worker=worker)

    job_id = service.start_translation(
        TranslationRequest(
            source_path=pdf,
            model="anthropic:claude-fake",
            target_lang="zh",
        )
    )

    events = await _drain(service, job_id)
    assert any(isinstance(e, FinishEvent) for e in events)
    finish = next(e for e in events if isinstance(e, FinishEvent))
    assert finish.cached is False
    assert finish.mono_path == f"translations/{slug}.mono.pdf"
    assert finish.dual_path == f"translations/{slug}.dual.pdf"

    # Manifest persisted.
    reloaded = TranslationsIndex.load(workspace)
    rows = reloaded.all()
    assert len(rows) == 1
    assert rows[0].sourceHash == source_hash
    assert rows[0].targetLang == "zh"

    # wiki/log.md is NOT touched by translation (per logging spec: "Translation
    # done | No — translation doesn't touch the wiki"). Only conversation-log.jsonl
    # gets an entry.
    log_text = workspace.log_md_path.read_text(encoding="utf-8")
    assert "translate" not in log_text

    # conversation-log.jsonl got one translate event.
    convlog = workspace.conversation_log_path.read_text(encoding="utf-8").splitlines()
    translate_events = [
        json.loads(line) for line in convlog if '"event"' in line
    ]
    assert any(e.get("event") == "translate" for e in translate_events)


# ---------------------------------------------------------------------------
# Cache-hit short-circuit
# ---------------------------------------------------------------------------


async def test_cache_hit_skips_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _seed_workspace(tmp_path)
    pdf = _make_pdf(workspace.root)

    from xreadagent.translation.service import _stable_translation_slug

    source_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    slug = _stable_translation_slug(pdf, source_hash)

    call_counter = {"n": 0}
    worker = _build_worker_with_events(
        monkeypatch, _canned_run(tmp_path, slug), call_counter=call_counter
    )
    service = TranslationService(workspace, worker=worker)

    first_id = service.start_translation(
        TranslationRequest(
            source_path=pdf, model="anthropic:claude-fake", target_lang="zh"
        )
    )
    await _drain(service, first_id)
    assert call_counter["n"] == 1

    # Second call with identical (hash, lang, model) — cache-hit short-circuit.
    second_id = service.start_translation(
        TranslationRequest(
            source_path=pdf, model="anthropic:claude-fake", target_lang="zh"
        )
    )
    events = await _drain(service, second_id)
    assert call_counter["n"] == 1, "worker should NOT have been invoked again"
    finish_events = [e for e in events if isinstance(e, FinishEvent)]
    assert len(finish_events) == 1
    assert finish_events[0].cached is True


async def test_cache_miss_when_model_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _seed_workspace(tmp_path)
    pdf = _make_pdf(workspace.root)

    from xreadagent.translation.service import _stable_translation_slug

    source_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    slug = _stable_translation_slug(pdf, source_hash)

    call_counter = {"n": 0}
    worker = _build_worker_with_events(
        monkeypatch, _canned_run(tmp_path, slug), call_counter=call_counter
    )
    service = TranslationService(workspace, worker=worker)

    first = service.start_translation(
        TranslationRequest(source_path=pdf, model="model-A", target_lang="zh")
    )
    await _drain(service, first)
    second = service.start_translation(
        TranslationRequest(source_path=pdf, model="model-B", target_lang="zh")
    )
    await _drain(service, second)
    assert call_counter["n"] == 2


async def test_cache_miss_when_target_lang_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _seed_workspace(tmp_path)
    pdf = _make_pdf(workspace.root)
    from xreadagent.translation.service import _stable_translation_slug

    source_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    slug = _stable_translation_slug(pdf, source_hash)

    call_counter = {"n": 0}
    worker = _build_worker_with_events(
        monkeypatch, _canned_run(tmp_path, slug), call_counter=call_counter
    )
    service = TranslationService(workspace, worker=worker)
    first = service.start_translation(
        TranslationRequest(source_path=pdf, model="m", target_lang="zh")
    )
    await _drain(service, first)
    second = service.start_translation(
        TranslationRequest(source_path=pdf, model="m", target_lang="ja")
    )
    await _drain(service, second)
    assert call_counter["n"] == 2


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------


async def test_service_logs_error_event_to_conversation_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _seed_workspace(tmp_path)
    pdf = _make_pdf(workspace.root)
    ts = utc_now_iso()
    canned = [
        StageEvent(type="stage_start", stage="parsing", ts=ts).model_dump(mode="json"),
        ErrorEvent(stage="parsing", message="subprocess crashed", ts=ts).model_dump(
            mode="json"
        ),
    ]
    worker = _build_worker_with_events(monkeypatch, canned)
    service = TranslationService(workspace, worker=worker)
    job_id = service.start_translation(
        TranslationRequest(source_path=pdf, model="m")
    )
    events = await _drain(service, job_id)
    assert any(isinstance(e, ErrorEvent) for e in events)

    # No manifest entry on failure.
    assert TranslationsIndex.load(workspace).all() == []

    # Conversation log has a translate_error event.
    lines = workspace.conversation_log_path.read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines if line.strip()]
    assert any(p.get("event") == "translate_error" for p in parsed)


async def test_start_translation_requires_existing_file(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path)
    service = TranslationService(workspace)
    with pytest.raises(FileNotFoundError):
        service.start_translation(
            TranslationRequest(
                source_path=tmp_path / "missing.pdf", model="m"
            )
        )


# ---------------------------------------------------------------------------
# D4 isolation: synthesis zone unchanged after a translation
# ---------------------------------------------------------------------------


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_synthesis_zone(workspace: Workspace) -> dict[str, str]:
    """Digest every file the translation MUST NOT modify.

    Includes: index.md, log.md, overview.md, open-questions.md, papers/,
    concepts/, state/sources.json, state/by-source/. Only
    conversation-log.jsonl and the translations/ directory may change.
    """
    snapshot: dict[str, str] = {}
    static_files = [
        workspace.index_md_path,
        workspace.log_md_path,
        workspace.overview_md_path,
        workspace.open_questions_md_path,
        workspace.sources_json_path,
        workspace.compile_summary_json_path,
    ]
    for path in static_files:
        if path.exists():
            snapshot[path.relative_to(workspace.root).as_posix()] = _digest_file(path)
    for directory in (
        workspace.papers_dir,
        workspace.concepts_dir,
        workspace.queries_dir,
        workspace.state_by_source_dir,
    ):
        if not directory.exists():
            continue
        for entry in directory.rglob("*"):
            if entry.is_file():
                snapshot[entry.relative_to(workspace.root).as_posix()] = _digest_file(
                    entry
                )
    return snapshot


async def test_translation_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The synthesis zone is byte-identical before/after a translation.

    Mirrors :func:`test_query_does_not_modify_synthesis_zone` for the
    translation subsystem (D4-style isolation extension per the task PRD).
    """
    workspace = _seed_workspace(tmp_path)
    pdf = _make_pdf(workspace.root)

    from xreadagent.translation.service import _stable_translation_slug

    source_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    slug = _stable_translation_slug(pdf, source_hash)

    before = _snapshot_synthesis_zone(workspace)

    worker = _build_worker_with_events(monkeypatch, _canned_run(tmp_path, slug))
    service = TranslationService(workspace, worker=worker)
    job_id = service.start_translation(
        TranslationRequest(source_path=pdf, model="m")
    )
    await _drain(service, job_id)

    after = _snapshot_synthesis_zone(workspace)
    assert before == after, (
        "Translation modified synthesis-zone files! diff="
        f"{ {k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k)} }"  # noqa: E501
    )
