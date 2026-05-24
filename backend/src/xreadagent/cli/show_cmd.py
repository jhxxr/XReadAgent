# SPDX-License-Identifier: AGPL-3.0-or-later
"""``xreadagent show`` subcommand: dump wiki / log content to stdout."""

from __future__ import annotations

import argparse
from pathlib import Path

from xreadagent.cli.output import error
from xreadagent.wiki.workspace import Workspace


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "show",
        help="Print wiki / log contents to stdout for inspection.",
        description=(
            "Pure-read inspection commands. Useful for verifying ingest / "
            "query output."
        ),
    )
    parser.add_argument(
        "--workspace",
        dest="workspace_path",
        type=Path,
        required=True,
    )
    show_subparsers = parser.add_subparsers(dest="show_kind", required=True)

    paper_p = show_subparsers.add_parser("paper")
    paper_p.add_argument("slug", type=str)

    concept_p = show_subparsers.add_parser("concept")
    concept_p.add_argument("slug", type=str)

    show_subparsers.add_parser("index")
    show_subparsers.add_parser("overview")
    show_subparsers.add_parser("open-questions")

    log_p = show_subparsers.add_parser("log")
    log_p.add_argument(
        "--tail",
        type=int,
        default=0,
        help="Show only the last N log entries (0 means all).",
    )

    parser.set_defaults(handler=run)


def _print_file(path: Path) -> int:
    if not path.exists():
        error(f"file not found: {path}")
        return 1
    print(path.read_text(encoding="utf-8"), end="")
    return 0


def _print_log_tail(path: Path, tail: int) -> int:
    if not path.exists():
        error(f"log not found: {path}")
        return 1
    text = path.read_text(encoding="utf-8")
    if tail <= 0:
        print(text, end="")
        return 0
    # Entries are demarcated by lines starting with "## [" (timestamp header).
    lines = text.splitlines(keepends=True)
    headers: list[int] = [i for i, line in enumerate(lines) if line.startswith("## [")]
    if not headers:
        print(text, end="")
        return 0
    if len(headers) <= tail:
        print(text, end="")
        return 0
    start = headers[-tail]
    print("".join(lines[start:]), end="")
    return 0


def run(args: argparse.Namespace) -> int:
    workspace = Workspace.at(args.workspace_path)
    if not workspace.is_initialized():
        error(
            f"workspace at {workspace.root} is not initialized; run 'xreadagent init' first"
        )
        return 1

    kind: str = args.show_kind
    if kind == "paper":
        path = workspace.papers_dir / f"{args.slug}.md"
        return _print_file(path)
    if kind == "concept":
        path = workspace.concepts_dir / f"{args.slug}.md"
        return _print_file(path)
    if kind == "index":
        return _print_file(workspace.index_md_path)
    if kind == "overview":
        return _print_file(workspace.overview_md_path)
    if kind == "open-questions":
        return _print_file(workspace.open_questions_md_path)
    if kind == "log":
        return _print_log_tail(workspace.log_md_path, int(args.tail))

    error(f"unknown 'show' target: {kind!r}")
    return 1


__all__ = ["add_parser", "run"]
