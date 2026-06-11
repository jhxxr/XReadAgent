# SPDX-License-Identifier: AGPL-3.0-or-later
"""ProcessPoolExecutor-based translation worker.

Subprocess isolation per ``quality-guidelines.md`` "Subprocess isolation for
crashing converters". The BabelDOC engine loads ~80 MB of ONNX model state
and runs C extensions (PyMuPDF, hyperscan) that can SIGSEGV on malformed
PDFs — keeping that inside a child process means a bad input only fails
one job, never takes down the FastAPI sidecar.

Implementation shape:

::

    AsyncTranslationWorker
        ├── _spawn_ctx           multiprocessing.get_context("spawn")
        ├── _jobs[job_id]        active job state (queue + process handle)
        ├── start(config)        kicks off a subprocess, returns job_id
        └── events(job_id)       async iterator over events from the queue

Tests subclass / patch this class via the ``runner`` constructor arg — the
default ``_default_runner`` uses ``multiprocessing.get_context("spawn").Process``
but the tests inject an in-process thread-runner to avoid the spawn cost
and the pickle-correctness checks (LangChain chat models pickle fine, but
the subprocess startup alone is ~2 s on Windows).

The job_id is a uuid4 hex string — no semantic meaning, the only consumer
that needs to map it is the FastAPI WS handler in ``api/main.py``.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import queue
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from multiprocessing.context import BaseContext
from multiprocessing.queues import Queue as MpQueue
from typing import Any, Protocol

from xreadagent.translation.babeldoc_adapter import AdapterConfig
from xreadagent.translation.babeldoc_meta import installed_babeldoc_version
from xreadagent.translation.events import (
    ErrorEvent,
    TranslationEvent,
    utc_now_iso,
)

# Sentinel placed on the queue to signal "stream complete".
_DONE = "__xreadagent_translation_done__"


@dataclass
class WorkerJobConfig:
    """Spawn-picklable bundle threaded into the subprocess.

    Plain dataclass — no Pydantic so that ``multiprocessing`` (which pickles
    via the default ``copyreg`` path) doesn't trip on Pydantic's ``__init__``
    metadata. ``ChatConfig`` carries enough to rebuild a LangChain chat model
    inside the child without sharing the live object across processes.
    """

    adapter: AdapterConfig
    chat: ChatConfig
    job_id: str
    babeldoc_version: str = field(default_factory=installed_babeldoc_version)


@dataclass
class ChatConfig:
    """Picklable description of the LLM the subprocess should construct.

    The chat model itself is NOT picklable (it carries httpx clients, locks,
    etc.), so we ship the inputs and rebuild via ``langchain.chat_models.init_chat_model``
    inside the child.
    """

    model: str
    api_key: str | None = None
    base_url: str | None = None
    default_headers: dict[str, str] = field(default_factory=dict)
    max_tokens: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class WorkerRunner(Protocol):
    """Strategy for actually running the worker function.

    Production uses a real ``multiprocessing.Process`` (spawn on Windows).
    Tests inject a thread-based runner to avoid spawn overhead + pickle
    surface; the inner contract — push event dicts onto a queue and a final
    ``_DONE`` sentinel — is identical either way.
    """

    def __call__(
        self,
        *,
        target: Callable[..., None],
        args: tuple[Any, ...],
        event_queue: "MpQueue[Any] | queue.Queue[Any]",
    ) -> "RunnerHandle": ...


@dataclass
class RunnerHandle:
    """Bookkeeping the worker keeps for an in-flight job."""

    join: Callable[[float | None], None]
    terminate: Callable[[], None]
    is_alive: Callable[[], bool]
    exitcode: Callable[[], int | None]


@dataclass
class JobRecord:
    """In-memory state for one active job.

    ``buffer`` captures the events we've already emitted so a late
    subscriber (the WS client connects after some events fired) can replay.
    The buffer is cleared once ``finished`` flips true and no readers remain;
    the service layer drives that cleanup.
    """

    job_id: str
    event_queue: "MpQueue[Any] | queue.Queue[Any]"
    handle: RunnerHandle
    buffer: list[TranslationEvent] = field(default_factory=list)
    finished: bool = False
    error: TranslationEvent | None = None
    final_event: TranslationEvent | None = None


def _default_runner_factory(ctx: BaseContext) -> WorkerRunner:
    """Return a runner that spawns a real subprocess using ``ctx``."""

    def _run(
        *,
        target: Callable[..., None],
        args: tuple[Any, ...],
        event_queue: "MpQueue[Any] | queue.Queue[Any]",
    ) -> RunnerHandle:
        # ``event_queue`` for the real runner must be a multiprocessing Queue;
        # the caller is responsible for constructing the right type. We do
        # NOT assert isinstance here because the runner abstraction must
        # accept both shapes for the thread-based test runner.
        # ``ctx.Process`` exists on every standard multiprocessing context
        # (Process, ForkProcess, SpawnProcess subclasses) but the typeshed
        # stub for ``BaseContext`` doesn't model it. Cast via getattr keeps
        # us correct at runtime; the alternative is sprinkling type: ignores.
        process_cls: Any = getattr(ctx, "Process")
        proc: Any = process_cls(target=target, args=args, daemon=True)
        proc.start()

        def _join(timeout: float | None) -> None:
            proc.join(timeout)

        def _terminate() -> None:
            if proc.is_alive():
                proc.terminate()

        def _is_alive() -> bool:
            return bool(proc.is_alive())

        def _exitcode() -> int | None:
            code = proc.exitcode
            return int(code) if code is not None else None

        return RunnerHandle(_join, _terminate, _is_alive, _exitcode)

    return _run


def thread_runner(
    *,
    target: Callable[..., None],
    args: tuple[Any, ...],
    event_queue: "MpQueue[Any] | queue.Queue[Any]",
) -> RunnerHandle:
    """In-process thread runner — used by tests to avoid spawn overhead.

    Same contract as the real subprocess runner: the target pushes events
    onto ``event_queue`` and then a ``_DONE`` sentinel; the handle exposes
    join/terminate/is_alive.
    """
    finished = threading.Event()
    exit_code_box: list[int | None] = [None]

    def _target_wrapped() -> None:
        try:
            target(*args)
        except BaseException:
            exit_code_box[0] = 1
            raise
        else:
            exit_code_box[0] = 0
        finally:
            finished.set()

    thread = threading.Thread(target=_target_wrapped, daemon=True)
    thread.start()

    def _join(timeout: float | None) -> None:
        thread.join(timeout)

    def _terminate() -> None:
        # Threads cannot be cleanly terminated from outside; mark done so
        # the consumer can drain.
        finished.set()

    def _is_alive() -> bool:
        return thread.is_alive()

    def _exitcode() -> int | None:
        return exit_code_box[0]

    return RunnerHandle(_join, _terminate, _is_alive, _exitcode)


def _make_chat(chat_cfg: ChatConfig) -> Any:
    """Reconstruct a LangChain chat model from the spawn-picklable config.

    The agent layer does the same thing via ``init_chat_model`` — but
    importing the agent module here would muddy the layering. Inline because
    this is the *one* place ``translation/`` is allowed to touch LangChain.
    """
    from langchain.chat_models import init_chat_model

    init_kwargs: dict[str, Any] = {}
    if chat_cfg.max_tokens is not None:
        init_kwargs["max_tokens"] = chat_cfg.max_tokens
    if chat_cfg.api_key:
        init_kwargs["api_key"] = chat_cfg.api_key
    if chat_cfg.base_url:
        init_kwargs["base_url"] = chat_cfg.base_url
    if chat_cfg.default_headers:
        init_kwargs["default_headers"] = dict(chat_cfg.default_headers)
    init_kwargs.update(chat_cfg.extra)
    try:
        return init_chat_model(chat_cfg.model, **init_kwargs)
    except TypeError:
        # Drop headers and retry — some providers don't accept them.
        retry = {k: v for k, v in init_kwargs.items() if k != "default_headers"}
        try:
            return init_chat_model(chat_cfg.model, **retry)
        except TypeError:
            return init_chat_model(chat_cfg.model)


def _worker_entry(
    config: WorkerJobConfig,
    event_queue: "MpQueue[Any] | queue.Queue[Any]",
) -> None:
    """Top-level entrypoint executed inside the subprocess.

    Must be a module-level function so the ``spawn`` start method can pickle
    it. Pushes ``dict`` versions of each ``TranslationEvent`` onto
    ``event_queue``, then a sentinel string ``_DONE`` to signal closure.

    Errors inside ``_make_chat`` or the adapter loop are caught and surfaced
    as an :class:`ErrorEvent` plus the closing sentinel — the parent always
    sees a clean stream termination.
    """
    from xreadagent.translation.babeldoc_adapter import (
        iter_translation_events,
        make_translator,
    )

    try:
        chat = _make_chat(config.chat)
        translator = make_translator(chat)
        for event in iter_translation_events(config.adapter, translator):
            event_queue.put(event.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001 — error boundary, see docstring
        import traceback as _tb

        error = ErrorEvent(
            stage=None,
            message=f"{type(exc).__name__}: {exc}",
            traceback_excerpt=_tb.format_exc()[:2000],
            ts=utc_now_iso(),
        )
        event_queue.put(error.model_dump(mode="json"))
    finally:
        event_queue.put(_DONE)


class AsyncTranslationWorker:
    """Async-iterator façade over per-job subprocess workers.

    Construct once per sidecar process. The ``runner`` constructor arg lets
    tests inject ``thread_runner`` to avoid the ``spawn`` cost; production
    leaves it default which uses ``multiprocessing.get_context("spawn").Process``.
    """

    def __init__(
        self,
        *,
        runner: WorkerRunner | None = None,
        ctx: BaseContext | None = None,
        queue_factory: Callable[[], "MpQueue[Any] | queue.Queue[Any]"] | None = None,
        poll_interval: float = 0.05,
    ) -> None:
        self._ctx = ctx or multiprocessing.get_context("spawn")
        if runner is None:
            self._runner: WorkerRunner = _default_runner_factory(self._ctx)
        else:
            self._runner = runner
        # When a non-default runner is supplied (tests use ``thread_runner``),
        # default to a plain ``queue.Queue`` because ``mp.Queue`` requires the
        # spawn context and is heavier than necessary in-process.
        if runner is None:

            def default_queue_factory() -> "MpQueue[Any] | queue.Queue[Any]":
                return self._ctx.Queue()

        else:

            def default_queue_factory() -> "MpQueue[Any] | queue.Queue[Any]":
                return queue.Queue()

        self._queue_factory = queue_factory or default_queue_factory
        self._poll_interval = poll_interval
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def start(self, config: WorkerJobConfig) -> str:
        """Kick off the worker subprocess for ``config`` and return job_id."""
        if not config.job_id:
            config = WorkerJobConfig(
                adapter=config.adapter,
                chat=config.chat,
                job_id=uuid.uuid4().hex,
                babeldoc_version=config.babeldoc_version,
            )
        event_queue = self._queue_factory()
        handle = self._runner(
            target=_worker_entry,
            args=(config, event_queue),
            event_queue=event_queue,
        )
        record = JobRecord(
            job_id=config.job_id,
            event_queue=event_queue,
            handle=handle,
        )
        with self._lock:
            self._jobs[config.job_id] = record
        return config.job_id

    async def events(self, job_id: str) -> AsyncIterator[TranslationEvent]:
        """Yield :class:`TranslationEvent` for ``job_id`` until completion.

        Late subscribers see the buffered events first, then the live tail.
        On subprocess crash (non-zero exit before any event lands), a
        synthetic :class:`ErrorEvent` is emitted so the consumer always sees
        a terminal event before the iterator closes.
        """
        record = self._jobs.get(job_id)
        if record is None:
            raise KeyError(f"unknown job_id: {job_id}")

        # Replay any events the worker already produced.
        for buffered in list(record.buffer):
            yield buffered

        loop = asyncio.get_event_loop()
        while True:
            if record.finished:
                # Drain anything that arrived after the buffer was last
                # captured but the stream is closed.
                break
            try:
                payload = await loop.run_in_executor(
                    None, _get_with_timeout, record.event_queue, self._poll_interval
                )
            except queue.Empty:
                # Detect subprocess death — surface a synthetic error.
                if not record.handle.is_alive():
                    code = record.handle.exitcode()
                    if code not in (None, 0) and record.error is None:
                        synthetic = ErrorEvent(
                            stage=None,
                            message=(
                                f"translation subprocess exited with code "
                                f"{code} before emitting events"
                            ),
                            traceback_excerpt=None,
                            ts=utc_now_iso(),
                        )
                        record.error = synthetic
                        record.buffer.append(synthetic)
                        record.finished = True
                        yield synthetic
                        break
                continue
            if payload == _DONE:
                record.finished = True
                break
            event = _materialise_event(payload)
            record.buffer.append(event)
            if isinstance(event, ErrorEvent):
                record.error = event
                record.final_event = event
                record.finished = True
                yield event
                break
            from xreadagent.translation.events import FinishEvent

            if isinstance(event, FinishEvent):
                record.final_event = event
                yield event
                # Let the queue drain to ``_DONE`` so we can mark finished.
                continue
            yield event

    def cancel(self, job_id: str) -> None:
        record = self._jobs.get(job_id)
        if record is None:
            return
        record.handle.terminate()
        record.finished = True

    def drop(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def get_record(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)


def _get_with_timeout(
    event_queue: "MpQueue[Any] | queue.Queue[Any]", timeout: float
) -> Any:
    """Block on ``event_queue.get`` with a small timeout.

    Wraps both ``multiprocessing.Queue.get`` and ``queue.Queue.get`` which
    share the ``get(timeout=...)`` signature.
    """
    return event_queue.get(timeout=timeout)


def _materialise_event(payload: Any) -> TranslationEvent:
    """Re-hydrate a dict ``payload`` into the corresponding event class.

    The subprocess emits ``model_dump`` dicts because Pydantic models don't
    pickle reliably across the spawn boundary on every platform; we re-build
    here so consumers downstream see typed objects.
    """
    from xreadagent.translation.events import (
        ErrorEvent as _Err,
    )
    from xreadagent.translation.events import (
        FinishEvent as _Fin,
    )
    from xreadagent.translation.events import (
        ModelDownloadEvent as _Mod,
    )
    from xreadagent.translation.events import (
        StageEvent as _Sta,
    )

    if not isinstance(payload, dict):
        raise TypeError(
            f"expected dict event payload, got {type(payload).__name__}"
        )
    type_value = payload.get("type")
    if type_value in {"stage_start", "stage_progress", "stage_end"}:
        return _Sta.model_validate(payload)
    if type_value in {
        "model_download_start",
        "model_download_progress",
        "model_download_done",
    }:
        return _Mod.model_validate(payload)
    if type_value == "finish":
        return _Fin.model_validate(payload)
    if type_value == "error":
        return _Err.model_validate(payload)
    raise ValueError(f"unknown event type: {type_value!r}")


def replay_events(records: Iterator[TranslationEvent]) -> Iterator[TranslationEvent]:
    """Iterate ``records`` with a small sleep — for cache-hit synthetic streams.

    Used by the service layer to surface a finish event immediately when a
    cache lookup hits, so consumers see the same shape as a real worker run.
    """
    for event in records:
        yield event
        time.sleep(0)


__all__ = [
    "AsyncTranslationWorker",
    "ChatConfig",
    "JobRecord",
    "RunnerHandle",
    "WorkerJobConfig",
    "WorkerRunner",
    "thread_runner",
]
