# SPDX-License-Identifier: AGPL-3.0-or-later
"""``WikiLog`` + ``WikiConversationLog`` append + concurrency tests."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from xreadagent.wiki.log import WikiConversationLog, WikiLog
from xreadagent.wiki.workspace import Workspace

_TIMESTAMP_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\]$")


def test_wiki_log_append_formats_entry(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    log = WikiLog(workspace)

    ts = log.append("ingest", "Attention Is All You Need", files_touched=["a.md", "b.md"])
    assert _TIMESTAMP_RE.match(f"[{ts}]"), f"bad timestamp {ts!r}"

    body = workspace.log_md_path.read_text(encoding="utf-8")
    assert f"## [{ts}] ingest | Attention Is All You Need" in body
    assert "- files: a.md, b.md" in body


def test_wiki_log_append_handles_missing_files(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    log = WikiLog(workspace)

    log.append("query", "test", files_touched=None)
    body = workspace.log_md_path.read_text(encoding="utf-8")
    assert "- files:" not in body


def test_wiki_log_concurrent_appends_do_not_corrupt(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    log = WikiLog(workspace)

    def worker(label: str) -> None:
        for index in range(10):
            log.append("ingest", f"{label}-{index}")

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("A", "B", "C")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    body = workspace.log_md_path.read_text(encoding="utf-8")
    header_lines = [line for line in body.splitlines() if line.startswith("## [")]
    assert len(header_lines) == 30
    # Every header must conform to the timestamp + op + subject structure.
    pattern = re.compile(r"^## \[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\] ingest \| [ABC]-\d+$")
    for line in header_lines:
        assert pattern.match(line), f"corrupt header: {line!r}"


def test_conversation_log_appends_jsonl(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    log = WikiConversationLog(workspace)

    log.append({"event": "ingest_started", "slug": "paper-a"})
    log.append({"event": "ingest_complete", "slug": "paper-a"})

    lines = workspace.conversation_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    decoded = [json.loads(line) for line in lines]
    assert decoded[0]["event"] == "ingest_started"
    assert decoded[1]["event"] == "ingest_complete"
    for row in decoded:
        assert "ts" in row
