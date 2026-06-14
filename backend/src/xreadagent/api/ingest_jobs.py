# SPDX-License-Identifier: AGPL-3.0-or-later
"""Job-based ingest service + WS event schemas.

Mirrors the translation job pattern (``translation/service.py`` +
``translation/worker.py``) so the frontend consumes one job contract:
``POST /api/ingest`` returns ``{jobId}`` immediately, the ingest runs in a
background thread, and ``/ws/jobs/{job_id}`` streams progress events until a
terminal ``finish`` / ``error`` event.

Casing convention (same as ``translation/events.py``): ``type`` values are
snake_case protocol tokens; field names are snake_case because these are
in-process schemas serialized straight onto the WS stream — they are NOT
state-JSON sidecar files where the camelCase rule applies.

Lazy-import discipline: this module is imported by ``api/wiki_router.py`` at
startup, so it must never import the agent/LangChain chain at module level
(``backend/tests/test_lazy_imports.py`` guards the sidecar startup path).
``IngestAgent`` / ``ingest_source`` are imported inside the job runner only.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
import traceback
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, Union, cast

from pydantic import BaseModel, ConfigDict, Field

from xreadagent.translation.events import ErrorEvent, utc_now_iso
from xreadagent.wiki.log import WikiConversationLog
from xreadagent.wiki.workspace import Workspace

if TYPE_CHECKING:
    from xreadagent.agents.ingest import IngestResult

# Sentinel placed on the queue to signal "stream complete" — same contract as
# the translation worker.
_DONE = "__xreadagent_ingest_done__"


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


# Phase-level pipeline tokens, in execution order. ``converting`` covers the
# markitdown/MinerU conversion, ``analyzing`` the LLM planner call, and
# ``writing`` the deterministic ``apply_plan`` write-out.
IngestStageName = Literal["converting", "analyzing", "writing"]

_STAGE_TOKENS: frozenset[str] = frozenset({"converting", "analyzing", "writing"})


class IngestStageEvent(_Strict):
    """One of ``stage_start`` / ``stage_end`` for an ingest phase."""

    type: Literal["stage_start", "stage_end"]
    stage: IngestStageName
    ts: str


class IngestFinishEvent(_Strict):
    """Terminal success event. Carries the resulting paper identity."""

    type: Literal["finish"] = "finish"
    slug: str
    title: str
    cache_hit: bool = False
    files_touched: list[str] = Field(default_factory=list)
    duration_s: float = 0.0
    ts: str


# The terminal failure event reuses the translation ``ErrorEvent`` shape so
# WS consumers handle one error contract across job kinds.
IngestEvent = Union[IngestStageEvent, IngestFinishEvent, ErrorEvent]


@dataclass(frozen=True)
class IngestJobRequest:
    """Inputs the service needs to start an ingest job.

    ``mode`` selects the pipeline depth:

    - ``"register"`` — convert + record the source only (decoupled import); no
      LLM call, so ``model`` / credentials may be empty.
    - ``"wiki"`` — full ingest (convert + analyze + write wiki pages). Requires
      a resolved ``model``.
    """

    workspace_path: Path
    file_path: Path
    model: str
    mode: Literal["register", "wiki"] = "wiki"
    title: str | None = None
    api_key: str | None = None
    base_url: str | None = None


class IngestJobRunner(Protocol):
    """The unit of work a job executes — injectable so tests skip the LLM.

    The default runner builds an ``IngestAgent`` and drives
    ``agents.orchestrator.ingest_source`` with the phase callback threaded
    through.
    """

    async def __call__(
        self,
        workspace: Workspace,
        request: IngestJobRequest,
        *,
        on_phase: Callable[[str], None],
    ) -> IngestResult: ...


async def _default_runner(
    workspace: Workspace,
    request: IngestJobRequest,
    *,
    on_phase: Callable[[str], None],
) -> IngestResult:
    # Imported lazily: the agent chain loads LangChain, which must never
    # happen on the sidecar startup path (see module docstring).
    if request.mode == "register":
        # Convert-only import — no LLM, no agent, no model required.
        from xreadagent.agents.orchestrator import register_source

        return register_source(
            workspace,
            request.file_path,
            title=request.title,
            on_phase=on_phase,
        )

    from xreadagent.agents.ingest import IngestAgent
    from xreadagent.agents.orchestrator import ingest_source

    agent = IngestAgent(
        workspace,
        model=request.model,
        api_key=request.api_key,
        base_url=request.base_url,
    )
    return await ingest_source(
        workspace,
        request.file_path,
        agent=agent,
        title=request.title,
        on_phase=on_phase,
    )


@dataclass
class _IngestJob:
    """In-memory state for one ingest job.

    ``buffer`` keeps every event already pulled off the queue so a late WS
    subscriber (connects after some events fired) can replay the history —
    same semantics as the translation worker's ``JobRecord``.
    """

    job_id: str
    request: IngestJobRequest
    event_queue: "queue.Queue[object]"
    buffer: list[IngestEvent] = field(default_factory=list)
    finished: bool = False


class IngestJobService:
    """Job façade over the ingest orchestrator for the FastAPI surface.

    Construct one instance per sidecar process. Each job runs the (blocking)
    agent pipeline on its own daemon thread so the event loop stays free —
    the previous synchronous ``POST /api/ingest`` blocked the whole sidecar
    for the duration of the LLM call.
    """

    def __init__(
        self,
        *,
        runner: IngestJobRunner | None = None,
        poll_interval: float = 0.05,
    ) -> None:
        self._runner: IngestJobRunner = runner if runner is not None else _default_runner
        self._poll_interval = poll_interval
        self._jobs: dict[str, _IngestJob] = {}
        self._lock = threading.Lock()

    def start_ingest(self, request: IngestJobRequest) -> str:
        """Validate inputs, kick off the background job, return a ``job_id``."""
        if not request.file_path.exists():
            raise FileNotFoundError(f"file not found: {request.file_path}")
        if not request.file_path.is_file():
            raise ValueError(f"source is not a regular file: {request.file_path}")
        workspace = Workspace.at(request.workspace_path)

        job_id = uuid.uuid4().hex
        job = _IngestJob(job_id=job_id, request=request, event_queue=queue.Queue())
        with self._lock:
            self._jobs[job_id] = job
        thread = threading.Thread(
            target=self._run_job_blocking,
            args=(job, workspace),
            daemon=True,
            name=f"ingest-job-{job_id[:8]}",
        )
        thread.start()
        return job_id

    async def event_stream(self, job_id: str) -> AsyncIterator[IngestEvent]:
        """Yield events for ``job_id`` until the terminal ``finish`` / ``error``.

        Late subscribers see the buffered events first, then the live tail —
        mirrors ``AsyncTranslationWorker.events``.
        """
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"unknown job_id: {job_id}")

        for buffered in list(job.buffer):
            yield buffered
        if job.finished:
            return

        loop = asyncio.get_event_loop()
        while True:
            try:
                payload = await loop.run_in_executor(
                    None, _get_with_timeout, job.event_queue, self._poll_interval
                )
            except queue.Empty:
                if job.finished:
                    break
                continue
            if payload == _DONE:
                job.finished = True
                break
            event = cast(IngestEvent, payload)
            job.buffer.append(event)
            yield event

    def known_jobs(self) -> list[str]:
        return list(self._jobs)

    # ------------------------------------------------------------------
    # Job execution
    # ------------------------------------------------------------------

    def _run_job_blocking(self, job: _IngestJob, workspace: Workspace) -> None:
        asyncio.run(self._run_job(job, workspace))

    async def _run_job(self, job: _IngestJob, workspace: Workspace) -> None:
        active_stage: IngestStageName | None = None

        def on_phase(stage: str) -> None:
            nonlocal active_stage
            if stage not in _STAGE_TOKENS:
                return
            typed_stage = cast(IngestStageName, stage)
            ts = utc_now_iso()
            if active_stage is not None:
                job.event_queue.put(
                    IngestStageEvent(type="stage_end", stage=active_stage, ts=ts)
                )
            active_stage = typed_stage
            job.event_queue.put(
                IngestStageEvent(type="stage_start", stage=typed_stage, ts=ts)
            )

        start = time.monotonic()
        try:
            result = await self._runner(workspace, job.request, on_phase=on_phase)
            if active_stage is not None:
                job.event_queue.put(
                    IngestStageEvent(
                        type="stage_end", stage=active_stage, ts=utc_now_iso()
                    )
                )
            duration_s = (
                result.duration_s
                if result.duration_s > 0
                else time.monotonic() - start
            )
            job.event_queue.put(
                IngestFinishEvent(
                    slug=result.source.slug,
                    title=result.source.title,
                    cache_hit=result.cache_hit,
                    files_touched=list(result.files_touched),
                    duration_s=duration_s,
                    ts=utc_now_iso(),
                )
            )
        except Exception as exc:  # noqa: BLE001 — job error boundary, same as the translation worker
            error = ErrorEvent(
                stage=active_stage,
                message=f"{type(exc).__name__}: {exc}",
                traceback_excerpt=traceback.format_exc()[:2000],
                ts=utc_now_iso(),
            )
            self._log_error(workspace, job, error)
            job.event_queue.put(error)
        finally:
            job.event_queue.put(_DONE)

    def _log_error(
        self, workspace: Workspace, job: _IngestJob, error: ErrorEvent
    ) -> None:
        # Success is already recorded by ``apply_plan`` (``event: ingest``);
        # failures get their own conversation-log record so users can grep
        # the workspace for them — mirrors ``translate_error``.
        WikiConversationLog(workspace).append(
            {
                "event": "ingest_error",
                "job_id": job.job_id,
                "file_path": str(job.request.file_path),
                "model": job.request.model,
                "stage": error.stage,
                "message": error.message,
            }
        )


def _get_with_timeout(event_queue: "queue.Queue[object]", timeout: float) -> object:
    return event_queue.get(timeout=timeout)


__all__ = [
    "IngestEvent",
    "IngestFinishEvent",
    "IngestJobRequest",
    "IngestJobService",
    "IngestStageEvent",
    "IngestStageName",
]
