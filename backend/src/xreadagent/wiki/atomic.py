# SPDX-License-Identifier: AGPL-3.0-or-later
"""Atomic filesystem helpers shared by wiki modules.

A correct ingest is more important than a fast one — every state mutation goes
through ``atomic_write_text`` / ``atomic_write_bytes`` (write to a sibling
``.tmp`` file, fsync, then rename). This guarantees a torn-write or a
``Ctrl+C`` mid-write leaves the previous file intact instead of producing a
partial JSON file the next ingest would refuse to parse.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

_APPEND_LOCK = threading.Lock()


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically via a same-directory temp file."""
    atomic_write_bytes(path, content.encode(encoding))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    # Use os-level fd handling so we can fsync before rename.
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        with os.fdopen(fd, "wb") as fp:
            fp.write(data)
            fp.flush()
            os.fsync(fp.fileno())
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    os.replace(tmp_path, path)


def append_text_locked(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Append ``content`` to ``path`` under a process-wide lock.

    Used for the append-only logs where multiple ingests / queries could race.
    Inter-process safety is out of scope — Phase 1 assumes a single sidecar.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with _APPEND_LOCK:
        with path.open("a", encoding=encoding) as fp:
            fp.write(content)
            fp.flush()
            os.fsync(fp.fileno())
