# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append-only log writers.

Two flavors:

- ``WikiLog`` — ``wiki/log.md``, human-readable Karpathy-style chronological log.
- ``WikiConversationLog`` — ``state/conversation-log.jsonl``, machine-grep-able
  JSONL event log for queries / crystallize / lint / ingest.

Both serialize through ``append_text_locked`` to defend against concurrent
appends from background tasks. Inter-process safety is out of scope — Phase 1
assumes a single sidecar process.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from xreadagent.wiki.atomic import append_text_locked
from xreadagent.wiki.workspace import Workspace


def _utc_now_iso() -> str:
    # Karpathy log convention: ISO 8601 UTC with `Z` suffix, no microseconds.
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class WikiLog:
    """Markdown append-only ledger at ``wiki/log.md``."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def append(
        self,
        op: str,
        subject: str,
        *,
        files_touched: Iterable[str] | None = None,
        timestamp: str | None = None,
    ) -> str:
        """Append one entry and return the timestamp that was recorded.

        Format::

            ## [2026-05-22T14:23:00Z] ingest | Attention Is All You Need
            - files: papers/attention-....md, concepts/transformer.md
        """
        ts = timestamp or _utc_now_iso()
        op_clean = op.strip() or "op"
        subject_clean = subject.strip() or "(no subject)"

        lines = [f"\n## [{ts}] {op_clean} | {subject_clean}\n"]
        if files_touched is not None:
            files = [f.strip() for f in files_touched if f and f.strip()]
            if files:
                lines.append(f"- files: {', '.join(files)}\n")

        append_text_locked(self._workspace.log_md_path, "".join(lines))
        return ts


class WikiConversationLog:
    """JSONL append-only event log at ``state/conversation-log.jsonl``."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def append(self, record: dict[str, Any], *, timestamp: str | None = None) -> str:
        """Append one JSON line. Adds ``ts`` if the caller didn't provide it."""
        ts = timestamp or record.get("ts") or _utc_now_iso()
        payload = {"ts": ts, **{k: v for k, v in record.items() if k != "ts"}}
        # ``ensure_ascii=False`` so CJK paper titles aren't escaped to ``\\uXXXX``.
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
        append_text_locked(self._workspace.conversation_log_path, line)
        return ts
