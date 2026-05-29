# SPDX-License-Identifier: AGPL-3.0-or-later
"""``xreadagent reindex`` subcommand: rebuild the vector search index.

Scans all wiki/papers/*.md and wiki/concepts/*.md files, re-embeds them
using the local ONNX model, and writes the results to vec.sqlite.
Query archive pages (wiki/queries/) are intentionally excluded per the
isolation rule.

When the embedding engine is unavailable (sqlite-vec or optimum not
installed), rebuilds only the FTS5 full-text index.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from xreadagent.cli.output import emit_many, error, progress
from xreadagent.wiki.workspace import Workspace


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "reindex",
        help="Rebuild the vector search index for a workspace.",
        description=(
            "Re-embed all wiki paper + concept pages into vec.sqlite. "
            "When the embedding engine is unavailable, rebuilds only the "
            "FTS5 full-text index."
        ),
    )
    parser.add_argument(
        "--workspace",
        dest="workspace_path",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--fts-only",
        action="store_true",
        help="Skip embedding and rebuild only the FTS5 full-text index.",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    workspace_path: Path = args.workspace_path
    fts_only: bool = bool(args.fts_only)

    workspace = Workspace.at(workspace_path)
    if not workspace.is_initialized():
        error(
            f"workspace at {workspace.root} is not initialized; run 'xreadagent init' first"
        )
        return 1

    progress(f"opening vec.sqlite at {workspace.vec_sqlite_path}")

    try:
        from xreadagent.wiki.vector import VectorStore

        store = VectorStore.open(workspace)
    except ImportError:
        if not fts_only:
            error(
                "sqlite-vec is not installed. Install it via: pip install sqlite-vec\n"
                "Use --fts-only to rebuild only the full-text index."
            )
            return 1
        # When sqlite-vec is not available but --fts-only was requested, we still
        # cannot proceed because the VectorStore itself depends on sqlite-vec.
        error("sqlite-vec is required even for FTS5-only rebuild")
        return 1
    except Exception as exc:
        error(f"failed to open vec.sqlite: {exc}")
        return 1

    embed_fn = None
    if not fts_only:
        try:
            from xreadagent.wiki.embedder import Embedder

            embedder = Embedder()
            progress(f"loading embedding model: {embedder.model_name}")
            embed_fn = embedder.embed
        except ImportError:
            error(
                "embedding dependencies not installed. "
                "Install via: pip install 'optimum[onnxruntime]' transformers\n"
                "Use --fts-only to rebuild only the full-text index."
            )
            store.close()
            return 1
        except Exception as exc:
            error(f"failed to initialize embedder: {exc}")
            store.close()
            return 1

    progress("rebuilding index...")
    try:
        stats = store.rebuild(embed_fn=embed_fn)
    except Exception as exc:
        error(f"rebuild failed: {exc}")
        store.close()
        return 2

    store.close()

    total = stats["papers"] + stats["concepts"]
    errors = stats["errors"]

    if errors > 0:
        print(
            f"[xreadagent] warning: {errors} page(s) failed to index",
            file=sys.stderr,
        )

    emit_many(
        {
            "workspace": str(workspace.root),
            "papers_indexed": stats["papers"],
            "concepts_indexed": stats["concepts"],
            "total_indexed": total,
            "errors": errors,
            "mode": "fts-only" if fts_only else "hybrid",
        }
    )
    return 0


__all__ = ["add_parser", "run"]
