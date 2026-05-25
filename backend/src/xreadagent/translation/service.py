# SPDX-License-Identifier: AGPL-3.0-or-later
"""Translation orchestrator — the user-facing surface above worker + manifest.

Acts as the single integration point for both CLI (``xreadagent translate``)
and FastAPI (``POST /api/translate`` + ``GET /ws/jobs/{job_id}``):

- Computes the source hash + cache lookup against ``TranslationsIndex``.
- On cache-hit returns a *synthetic* job that immediately emits a finish
  event with the cached paths — no subprocess, no LLM call.
- On cache-miss spawns the worker subprocess and decorates the worker's
  event stream so that on ``finish`` the manifest is written, ``log.md``
  gets a ``translate`` op entry, and the conversation log gets an event.

D4-style isolation: translation only touches ``translations/`` + the two
log files (``wiki/log.md`` is the synthesis ledger; ``state/conversation-log.jsonl``
is the audit trail). ``wiki/papers/``, ``wiki/concepts/``, ``state/sources.json``,
``state/by-source/`` are NEVER written by this module. The
``test_translation_isolation`` test in
``backend/tests/test_translation_service.py`` enforces it.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from xreadagent.translation.babeldoc_adapter import AdapterConfig
from xreadagent.translation.events import (
    ErrorEvent,
    FinishEvent,
    TranslationEvent,
    utc_now_iso,
)
from xreadagent.translation.manifest import (
    TranslationEntry,
    TranslationsIndex,
)
from xreadagent.translation.worker import (
    AsyncTranslationWorker,
    ChatConfig,
    WorkerJobConfig,
)
from xreadagent.wiki.log import WikiConversationLog
from xreadagent.wiki.sources import compute_content_hash
from xreadagent.wiki.workspace import Workspace

_BABELDOC_VERSION_DEFAULT = "0.6.2"


@dataclass(frozen=True)
class TranslationRequest:
    """Inputs the service needs to start a translation."""

    source_path: Path
    model: str
    target_lang: str = "zh"
    source_lang: str = "en"
    mono: bool = True
    dual: bool = True
    api_key: str | None = None
    base_url: str | None = None
    default_headers: dict[str, str] = field(default_factory=dict)
    max_tokens: int | None = None


@dataclass
class _ActiveJob:
    """In-memory state for a job the service is tracking.

    Differs from the worker's :class:`JobRecord` because the *service* layer
    also tracks whether the job is a cache-hit synthetic stream (which has no
    backing subprocess).
    """

    job_id: str
    request: TranslationRequest
    source_slug: str
    source_hash: str
    cache_hit: bool
    finish_event: FinishEvent | None = None
    error_event: ErrorEvent | None = None


class TranslationService:
    """High-level façade used by the FastAPI / CLI surfaces.

    Construct one instance per sidecar process. Tests pass a stubbed
    :class:`AsyncTranslationWorker` so the real subprocess is never spawned.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        worker: AsyncTranslationWorker | None = None,
        babeldoc_version: str = _BABELDOC_VERSION_DEFAULT,
    ) -> None:
        self._workspace = workspace
        self._worker = worker if worker is not None else AsyncTranslationWorker()
        self._babeldoc_version = babeldoc_version
        self._jobs: dict[str, _ActiveJob] = {}

    def start_translation(self, request: TranslationRequest) -> str:
        """Kick off a translation. Returns a ``job_id`` immediately.

        Cache-hit short-circuit: if ``TranslationsIndex.find(hash, lang, model)``
        returns a row whose on-disk PDFs still exist, we register a synthetic
        job that the consumer's ``event_stream`` will drain in one event.
        """
        if not request.source_path.exists():
            raise FileNotFoundError(f"source file not found: {request.source_path}")
        if not request.source_path.is_file():
            raise ValueError(f"source is not a regular file: {request.source_path}")

        self._workspace.ensure_layout()

        source_hash = compute_content_hash(request.source_path)
        source_slug = _stable_translation_slug(request.source_path, source_hash)

        index = TranslationsIndex.load(self._workspace)
        cached = index.find(source_hash, request.target_lang, request.model)
        if cached is not None and _entry_paths_exist(self._workspace, cached):
            job_id = uuid.uuid4().hex
            cache_finish = FinishEvent(
                mono_path=cached.monoPath,
                dual_path=cached.dualPath,
                duration_s=cached.durationS,
                cached=True,
                ts=utc_now_iso(),
            )
            self._jobs[job_id] = _ActiveJob(
                job_id=job_id,
                request=request,
                source_slug=cached.sourceSlug,
                source_hash=source_hash,
                cache_hit=True,
                finish_event=cache_finish,
            )
            return job_id

        # Cache-miss: build the worker config and start the subprocess.
        job_id = uuid.uuid4().hex
        adapter_cfg = AdapterConfig(
            input_path=request.source_path,
            output_dir=self._workspace.translations_dir,
            target_lang=request.target_lang,
            source_lang=request.source_lang,
            no_mono=not request.mono,
            no_dual=not request.dual,
            babeldoc_version=self._babeldoc_version,
        )
        chat_cfg = ChatConfig(
            model=request.model,
            api_key=request.api_key,
            base_url=request.base_url,
            default_headers=dict(request.default_headers),
            max_tokens=request.max_tokens,
        )
        worker_cfg = WorkerJobConfig(
            adapter=adapter_cfg,
            chat=chat_cfg,
            job_id=job_id,
            babeldoc_version=self._babeldoc_version,
        )
        self._worker.start(worker_cfg)
        self._jobs[job_id] = _ActiveJob(
            job_id=job_id,
            request=request,
            source_slug=source_slug,
            source_hash=source_hash,
            cache_hit=False,
        )
        return job_id

    async def event_stream(self, job_id: str) -> AsyncIterator[TranslationEvent]:
        """Yield events for ``job_id`` until ``finish`` / ``error``.

        On ``finish``, the manifest is written, ``wiki/log.md`` gets a
        ``translate`` entry, and the conversation log gets one record. On
        ``error`` we still log the failure to the conversation log so users
        can grep their workspace for it.
        """
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"unknown job_id: {job_id}")

        if job.cache_hit:
            finish = job.finish_event
            if finish is None:
                # Defensive — start_translation always sets finish for cache hits.
                raise RuntimeError("cache-hit job has no finish event")
            self._log_cache_hit(job, finish)
            yield finish
            return

        start = time.monotonic()
        async for event in self._worker.events(job_id):
            if isinstance(event, FinishEvent):
                job.finish_event = self._persist_finish(job, event, start)
                yield job.finish_event
                continue
            if isinstance(event, ErrorEvent):
                job.error_event = event
                self._log_error(job, event)
                yield event
                return
            yield event

    def cancel(self, job_id: str) -> None:
        self._worker.cancel(job_id)

    def drop(self, job_id: str) -> None:
        self._worker.drop(job_id)
        self._jobs.pop(job_id, None)

    def known_jobs(self) -> list[str]:
        return list(self._jobs)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _persist_finish(
        self, job: _ActiveJob, finish: FinishEvent, start_monotonic: float
    ) -> FinishEvent:
        """Atomically write the manifest entry + log entries on translation finish.

        Returns a finish event that has been amended with workspace-relative
        paths (the worker emits absolute paths because BabelDOC writes them
        as absolute on Windows). The caller forwards the returned event to
        consumers so the WS stream sees relative paths too.
        """
        mono_rel = _relativise(self._workspace, finish.mono_path)
        dual_rel = _relativise(self._workspace, finish.dual_path)
        duration_s = (
            finish.duration_s
            if finish.duration_s > 0
            else time.monotonic() - start_monotonic
        )

        index = TranslationsIndex.load(self._workspace)
        entry = TranslationEntry(
            sourceSlug=job.source_slug,
            sourceHash=job.source_hash,
            targetLang=job.request.target_lang,
            model=job.request.model,
            monoPath=mono_rel,
            dualPath=dual_rel,
            translatedAt=utc_now_iso(),
            durationS=duration_s,
            babeldocVersion=self._babeldoc_version,
        )
        index.add(entry)
        index.save()

        # Translation does NOT touch the wiki synthesis zone (it only writes
        # to translations/), so we skip wiki/log.md per the logging spec.
        # The conversation log records the full audit trail.
        WikiConversationLog(self._workspace).append(
            {
                "event": "translate",
                "job_id": job.job_id,
                "source_slug": job.source_slug,
                "source_hash": job.source_hash,
                "target_lang": job.request.target_lang,
                "model": job.request.model,
                "mono_path": mono_rel,
                "dual_path": dual_rel,
                "duration_s": duration_s,
                "cached": False,
            }
        )

        return finish.model_copy(
            update={"mono_path": mono_rel, "dual_path": dual_rel, "duration_s": duration_s}
        )

    def _log_cache_hit(self, job: _ActiveJob, finish: FinishEvent) -> None:
        # Cache-hit means the manifest already records this triple. We append
        # to the conversation log only (no wiki/log.md entry — that ledger is
        # for *operations that changed the wiki state*, and a cache hit
        # changed nothing).
        WikiConversationLog(self._workspace).append(
            {
                "event": "translate",
                "job_id": job.job_id,
                "source_slug": job.source_slug,
                "source_hash": job.source_hash,
                "target_lang": job.request.target_lang,
                "model": job.request.model,
                "mono_path": finish.mono_path,
                "dual_path": finish.dual_path,
                "duration_s": finish.duration_s,
                "cached": True,
            }
        )

    def _log_error(self, job: _ActiveJob, error: ErrorEvent) -> None:
        WikiConversationLog(self._workspace).append(
            {
                "event": "translate_error",
                "job_id": job.job_id,
                "source_slug": job.source_slug,
                "source_hash": job.source_hash,
                "target_lang": job.request.target_lang,
                "model": job.request.model,
                "stage": error.stage,
                "message": error.message,
            }
        )

    @property
    def worker(self) -> AsyncTranslationWorker:
        """Access the underlying worker (mainly for tests)."""
        return self._worker


def _stable_translation_slug(source_path: Path, source_hash: str) -> str:
    """Derive a stable per-source slug for translation outputs.

    Mirrors :func:`xreadagent.wiki.paths.stable_source_slug` shape so that the
    translation slug matches the wiki paper slug when ingest + translate both
    run on the same file.
    """
    from xreadagent.wiki.paths import stable_source_slug

    return stable_source_slug(source_path.stem, source_hash)


def _entry_paths_exist(workspace: Workspace, entry: TranslationEntry) -> bool:
    """Validate that the on-disk PDFs for ``entry`` are still present.

    A manifest entry without surviving files is not a cache hit — the user
    may have manually deleted the PDF to force a re-run. We treat that as
    "cache miss" rather than "manifest corruption" because the corrective
    action is the same either way: run BabelDOC again.
    """
    mono_ok = (
        entry.monoPath is None or (workspace.root / entry.monoPath).exists()
    )
    dual_ok = (
        entry.dualPath is None or (workspace.root / entry.dualPath).exists()
    )
    # At least one of mono / dual must be present and on disk.
    if entry.monoPath is None and entry.dualPath is None:
        return False
    return mono_ok and dual_ok


def _relativise(workspace: Workspace, path: str | None) -> str | None:
    """Convert ``path`` to a workspace-relative POSIX string if possible.

    Best-effort: returns the original string if the path doesn't resolve
    under ``workspace.root`` (which happens when BabelDOC writes to a temp
    dir during tests). Either way the caller can safely persist the value.
    """
    if not path:
        return None
    try:
        resolved = Path(path).resolve()
        rel = resolved.relative_to(workspace.root.resolve())
    except (ValueError, OSError):
        return path
    return rel.as_posix()


async def collect_events(stream: AsyncIterator[TranslationEvent]) -> list[TranslationEvent]:
    """Drain ``stream`` into a list — convenience for CLI / tests."""
    events: list[TranslationEvent] = []
    async for event in stream:
        events.append(event)
    return events


def collect_events_blocking(
    stream: AsyncIterator[TranslationEvent],
) -> list[TranslationEvent]:
    """Blocking wrapper around :func:`collect_events`."""
    return asyncio.run(collect_events(stream))


# Aliased exports for the public surface.
__all__: list[str] = [
    "TranslationRequest",
    "TranslationService",
    "collect_events",
    "collect_events_blocking",
]
