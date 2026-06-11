# SPDX-License-Identifier: AGPL-3.0-or-later
"""``xreadagent ingest`` subcommand: run the full ingest pipeline with a real LLM.

Calls ``agents.orchestrator.ingest_source`` which already handles the
content-hash short-circuit + cache-hit short-circuit. The CLI only adds:

- ``--model`` provider string resolution → ``IngestAgent``.
- ``--header`` / ``--user-agent`` / ``--planner-method`` / ``--env-override``
  to make calls through Claude-Code-compat proxies actually work
  (see ``llm_flags.py``).
- Optional ``--stub-planner`` (or ``XREADAGENT_STUB_PLANNER=1``) for tests.
- One-line progress on stderr, structured key/value summary on stdout.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from xreadagent.agents._defaults import DEFAULT_AGENT_MAX_TOKENS
from xreadagent.cli.env import ensure_provider_credentials, load_env_files
from xreadagent.cli.llm_flags import (
    add_llm_runtime_flags,
    resolve_env_override,
    resolve_headers,
    resolve_max_tokens,
)
from xreadagent.cli.output import emit_list, emit_many, error, progress
from xreadagent.cli.stubs import stub_ingest_planner, use_stub_planner
from xreadagent.wiki.workspace import Workspace

if TYPE_CHECKING:
    from xreadagent.agents.ingest import IngestAgent, PlannerMethod


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "ingest",
        help="Ingest a source file into a workspace with a real LLM.",
        description=(
            "Convert the file to markdown (markitdown / MinerU), then run the "
            "single-pass IngestAgent. Emits structured key/value output on "
            "success."
        ),
    )
    parser.add_argument("source_path", type=Path)
    parser.add_argument(
        "--workspace",
        dest="workspace_path",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--model",
        type=str,
        default="anthropic:claude-sonnet-4-6",
        help="LangChain provider:model string (e.g. 'openai:gpt-4o').",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Override the paper title (else: derived from the filename).",
    )
    parser.add_argument(
        "--stub-planner",
        action="store_true",
        help=(
            "Use a deterministic in-process stub planner instead of a real LLM "
            "(also enabled by XREADAGENT_STUB_PLANNER=1; used by tests)."
        ),
    )
    add_llm_runtime_flags(parser)
    parser.set_defaults(handler=run)


def _build_agent(
    workspace: Workspace,
    model: str,
    *,
    force_stub: bool,
    headers: dict[str, str],
    planner_method: PlannerMethod,
    max_tokens: int | None,
) -> IngestAgent:
    # Imported lazily: pulling in IngestAgent loads the LangChain chain, which
    # must not happen at CLI-dispatch time (keeps `xreadagent --version` fast).
    from xreadagent.agents.ingest import IngestAgent

    if force_stub or use_stub_planner():
        return IngestAgent(
            workspace,
            planner=stub_ingest_planner,
            max_tokens=max_tokens,
        )
    return IngestAgent(
        workspace,
        model=model,
        headers=headers or None,
        planner_method=planner_method,
        max_tokens=max_tokens,
    )


def run(args: argparse.Namespace) -> int:
    from xreadagent.agents.orchestrator import ingest_source

    source_path: Path = args.source_path
    workspace_path: Path = args.workspace_path
    model: str = args.model
    title: str | None = args.title
    force_stub: bool = bool(args.stub_planner)
    planner_method: PlannerMethod = args.planner_method
    headers = resolve_headers(args)
    env_override = resolve_env_override(args)
    max_tokens = resolve_max_tokens(args)

    if not source_path.exists():
        error(f"source file does not exist: {source_path}")
        return 1
    if not source_path.is_file():
        error(f"source path is not a regular file: {source_path}")
        return 1

    workspace = Workspace.at(workspace_path)
    if not workspace.is_initialized():
        error(
            f"workspace at {workspace.root} is not initialized; run 'xreadagent init' first"
        )
        return 1

    load_env_files(
        workspace.root / ".env.local",
        Path.cwd() / ".env.local",
        override=env_override,
    )

    using_stub = force_stub or use_stub_planner()
    if not using_stub:
        try:
            ensure_provider_credentials(model)
        except (RuntimeError, ValueError) as exc:
            error(str(exc))
            return 1

    progress(f"converting {source_path.name} via pipeline router")
    progress(f"planner = {'stub' if using_stub else model}")
    if not using_stub and headers:
        progress(f"custom headers: {sorted(headers)}")
    if not using_stub and env_override:
        progress(".env.local override enabled (winning over shell env)")
    # Always surface the effective budget — the default is silent otherwise
    # and the recent smoke tests showed that "max_tokens too small" is the
    # single most common open-the-box failure on extended-thinking models.
    effective_max_tokens = (
        max_tokens if max_tokens is not None else DEFAULT_AGENT_MAX_TOKENS
    )
    progress(f"max_tokens = {effective_max_tokens}")

    try:
        agent = _build_agent(
            workspace,
            model,
            force_stub=force_stub,
            headers=headers,
            planner_method=planner_method,
            max_tokens=max_tokens,
        )
    except (ValueError, RuntimeError) as exc:
        error(str(exc))
        return 1

    try:
        result = asyncio.run(
            ingest_source(workspace, source_path, agent=agent, title=title)
        )
    except FileNotFoundError as exc:
        error(str(exc))
        return 1
    except ValueError as exc:
        error(str(exc))
        return 1
    except RuntimeError as exc:
        error(str(exc))
        return 2
    except Exception as exc:  # noqa: BLE001  — CLI boundary surfaces errors as exit codes
        error(f"unexpected failure: {exc!r}")
        return 2

    created_concepts = [c.slug for c in result.plan.concepts if c.op == "create"]
    merged_concepts = [c.slug for c in result.plan.concepts if c.op == "merge"]

    emit_many(
        {
            "workspace": str(workspace.root),
            "source_id": result.source.id,
            "source_slug": result.source.slug,
            "source_path": result.source.sourcePath,
            "content_hash": result.source.contentHash,
            "page_count": result.source.pageCount,
            "cache_hit": "true" if result.cache_hit else "false",
            "duration_s": f"{result.duration_s:.3f}",
            "paper_page": f"wiki/papers/{result.plan.paper.slug}.md",
            "concepts_created_count": len(created_concepts),
            "concepts_merged_count": len(merged_concepts),
            "files_touched_count": len(result.files_touched),
        }
    )
    emit_list("concept_created", created_concepts)
    emit_list("concept_merged", merged_concepts)
    emit_list("file_touched", result.files_touched)
    emit_list(
        "token_usage",
        [f"{k}={v}" for k, v in sorted(result.tokens_used.items())],
    )

    return 0


__all__ = ["add_parser", "run"]
