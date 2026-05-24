# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tiny structured stdout helpers for CLI output.

We deliberately avoid ``rich`` / ``textual`` / ``tabulate`` — the output is
``key: value`` lines on stdout (one piece of data per line) so future tooling
can grep without parsing a TTY-rendered table. Progress goes to stderr.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from typing import Any, TextIO


def emit(key: str, value: Any, *, stream: TextIO | None = None) -> None:
    """Print one ``key: value`` line. The default stream is stdout."""
    target = stream if stream is not None else sys.stdout
    target.write(f"{key}: {value}\n")
    target.flush()


def emit_many(rows: Mapping[str, Any], *, stream: TextIO | None = None) -> None:
    """Print several key/value rows in field-declaration order."""
    target = stream if stream is not None else sys.stdout
    for key, value in rows.items():
        target.write(f"{key}: {value}\n")
    target.flush()


def emit_list(key: str, values: Iterable[Any], *, stream: TextIO | None = None) -> None:
    """Print ``key.0: …`` / ``key.1: …`` style for a sequence.

    Empty sequences produce ``key: (none)`` so the consumer can still tell
    the field existed.
    """
    target = stream if stream is not None else sys.stdout
    materialized = list(values)
    if not materialized:
        target.write(f"{key}: (none)\n")
    else:
        for idx, value in enumerate(materialized):
            target.write(f"{key}.{idx}: {value}\n")
    target.flush()


def progress(message: str) -> None:
    """One-line progress emit to stderr — never mixed with stdout key/value data."""
    sys.stderr.write(f"[xreadagent] {message}\n")
    sys.stderr.flush()


def error(message: str) -> None:
    """Print a user-visible error to stderr (no stack trace)."""
    sys.stderr.write(f"error: {message}\n")
    sys.stderr.flush()


__all__ = ["emit", "emit_list", "emit_many", "error", "progress"]
