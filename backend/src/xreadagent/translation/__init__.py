# SPDX-License-Identifier: AGPL-3.0-or-later
"""BabelDOC-driven layout-preserving translation subsystem (Phase 2).

This package wraps the AGPL-3.0 ``babeldoc==0.6.2`` engine in a subprocess
worker, exposes a streaming event protocol over WebSocket, and persists
results into ``workspaces/{ws}/translations/``. The wiki / state directories
are NEVER touched by translation (D4-style isolation extension).

The actual ``babeldoc`` import is lazy and happens inside the worker
subprocess — that keeps the rest of the codebase importable on machines that
don't have the heavy ML deps installed.
"""

from xreadagent.translation.events import (
    ErrorEvent,
    FinishEvent,
    ModelDownloadEvent,
    StageEvent,
    TranslationEvent,
    utc_now_iso,
)
from xreadagent.translation.manifest import (
    TranslationEntry,
    TranslationsIndex,
    TranslationsManifest,
)
from xreadagent.translation.service import TranslationRequest, TranslationService
from xreadagent.translation.worker import (
    AsyncTranslationWorker,
    ChatConfig,
    WorkerJobConfig,
    thread_runner,
)

__all__ = [
    "AsyncTranslationWorker",
    "ChatConfig",
    "ErrorEvent",
    "FinishEvent",
    "ModelDownloadEvent",
    "StageEvent",
    "TranslationEntry",
    "TranslationEvent",
    "TranslationRequest",
    "TranslationService",
    "TranslationsIndex",
    "TranslationsManifest",
    "WorkerJobConfig",
    "thread_runner",
    "utc_now_iso",
]
