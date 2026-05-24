# SPDX-License-Identifier: AGPL-3.0-or-later
"""``xreadagent init`` subcommand: bootstrap a new workspace on disk."""

from __future__ import annotations

import argparse
from pathlib import Path

from xreadagent.cli.output import emit_many, error
from xreadagent.wiki.workspace import Workspace


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "init",
        help="Create a new XReadAgent workspace at the given path.",
        description=(
            "Initialize an empty LLM-Wiki workspace. Creates the on-disk "
            "directory layout (raw/, extracts/, state/, wiki/) plus the "
            "seed files (index.md, log.md, sources.json, …)."
        ),
    )
    parser.add_argument("workspace_path", type=Path)
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Human-readable title for the workspace (used in index.md / log.md headers).",
    )
    parser.set_defaults(handler=run)


def _prompt_title(workspace_path: Path) -> str:
    suggested = workspace_path.name or "Workspace"
    raw = input(f"workspace title [{suggested}]: ").strip()
    return raw or suggested


def _is_dir_nonempty(path: Path) -> bool:
    if not path.exists():
        return False
    if not path.is_dir():
        return True
    try:
        next(path.iterdir())
    except StopIteration:
        return False
    return True


def run(args: argparse.Namespace) -> int:
    workspace_path: Path = args.workspace_path
    title: str | None = args.title

    if workspace_path.exists() and not workspace_path.is_dir():
        error(f"path exists but is not a directory: {workspace_path}")
        return 1

    workspace = Workspace.at(workspace_path)
    if workspace.is_initialized():
        # Treat as idempotent: nothing to do, no destructive overwrite.
        emit_many(
            {
                "workspace": str(workspace.root),
                "status": "already-initialized",
                "index_path": str(workspace.index_md_path),
            }
        )
        return 0

    if _is_dir_nonempty(workspace_path):
        error(
            f"refusing to init: {workspace_path} is non-empty and lacks a wiki/index.md; "
            "pick a fresh directory"
        )
        return 1

    if title is None:
        title = _prompt_title(workspace_path)

    workspace.ensure_layout()
    workspace.init_empty(title)

    emit_many(
        {
            "workspace": str(workspace.root),
            "status": "initialized",
            "title": title,
            "index_path": str(workspace.index_md_path),
            "log_path": str(workspace.log_md_path),
            "raw_dir": str(workspace.raw_dir),
            "extracts_dir": str(workspace.extracts_dir),
            "state_dir": str(workspace.state_dir),
        }
    )
    return 0


__all__ = ["add_parser", "run"]
