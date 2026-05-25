# SPDX-License-Identifier: AGPL-3.0-or-later
"""``xreadagent`` console-script dispatcher.

Returns an int exit code:
- ``0`` on success.
- ``1`` for user errors (bad arguments, missing file, etc.).
- ``2`` for system errors (unexpected exceptions, network failure, …).
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from xreadagent.cli import ingest_cmd, init_cmd, query_cmd, show_cmd, translate_cmd
from xreadagent.cli.output import error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xreadagent",
        description=(
            "Scientific research agent with LLM-Wiki memory. "
            "Smoke-test harness for ingest / query against a real LLM."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=_version_string(),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    init_cmd.add_parser(subparsers)
    ingest_cmd.add_parser(subparsers)
    query_cmd.add_parser(subparsers)
    show_cmd.add_parser(subparsers)
    translate_cmd.add_parser(subparsers)
    return parser


def _version_string() -> str:
    try:
        import importlib.metadata

        return f"xreadagent {importlib.metadata.version('xreadagent')}"
    except Exception:  # noqa: BLE001  — version is best-effort
        return "xreadagent 0.0.0+unknown"


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(sys.stderr)
        return 1
    try:
        return int(handler(args))
    except KeyboardInterrupt:
        error("interrupted")
        return 1


__all__ = ["build_parser", "main"]
