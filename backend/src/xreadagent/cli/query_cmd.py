# SPDX-License-Identifier: AGPL-3.0-or-later
"""``xreadagent query`` subcommand: ask a question and archive the answer."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from xreadagent.agents._defaults import DEFAULT_AGENT_MAX_TOKENS
from xreadagent.agents.query import PlannerMethod, QueryAgent
from xreadagent.agents.query_orchestrator import answer_query
from xreadagent.cli.env import ensure_provider_credentials, load_env_files
from xreadagent.cli.llm_flags import (
    add_llm_runtime_flags,
    resolve_env_override,
    resolve_headers,
    resolve_max_tokens,
)
from xreadagent.cli.output import emit_list, emit_many, error, progress
from xreadagent.cli.stubs import stub_query_planner, use_stub_planner
from xreadagent.wiki.workspace import Workspace


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "query",
        help="Ask a natural-language question grounded in the wiki.",
        description=(
            "Runs the QueryAgent. The answer is archived under "
            "wiki/queries/{topic}/{date}-{slug}.md; the synthesis zone "
            "(papers/, concepts/, index.md, log.md) is never modified."
        ),
    )
    parser.add_argument("question", type=str)
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
        help="LangChain provider:model string.",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Topic folder under wiki/queries/ (default: derived from the question).",
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
) -> QueryAgent:
    if force_stub or use_stub_planner():
        return QueryAgent(
            workspace,
            planner=stub_query_planner,
            max_tokens=max_tokens,
        )
    return QueryAgent(
        workspace,
        model=model,
        headers=headers or None,
        planner_method=planner_method,
        max_tokens=max_tokens,
    )


def run(args: argparse.Namespace) -> int:
    workspace_path: Path = args.workspace_path
    question: str = args.question
    model: str = args.model
    topic: str | None = args.topic
    force_stub: bool = bool(args.stub_planner)
    planner_method: PlannerMethod = args.planner_method
    headers = resolve_headers(args)
    env_override = resolve_env_override(args)
    max_tokens = resolve_max_tokens(args)

    if not question.strip():
        error("question must be a non-empty string")
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

    progress(f"planner = {'stub' if using_stub else model}")
    progress("running QueryAgent (read-only)")
    if not using_stub and headers:
        progress(f"custom headers: {sorted(headers)}")
    if not using_stub and env_override:
        progress(".env.local override enabled (winning over shell env)")
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
        result = asyncio.run(answer_query(workspace, question, agent=agent, topic=topic))
    except ValueError as exc:
        error(str(exc))
        return 1
    except RuntimeError as exc:
        error(str(exc))
        return 2
    except Exception as exc:  # noqa: BLE001  — CLI boundary
        error(f"unexpected failure: {exc!r}")
        return 2

    try:
        rel = result.query_page_path.relative_to(workspace.root).as_posix()
    except ValueError:
        rel = result.query_page_path.as_posix()

    emit_many(
        {
            "workspace": str(workspace.root),
            "question": result.answer.question,
            "topic": topic or "(derived)",
            "confidence": result.answer.confidence,
            "duration_s": f"{result.duration_s:.3f}",
            "archive_path": rel,
            "answer_chars": len(result.answer.answer_markdown),
            "evidence_count": len(result.answer.evidence),
        }
    )
    emit_list("source_cited", result.answer.sources_cited)
    emit_list("layer_used", result.answer.layers_used)
    emit_list("open_question_raised", result.answer.open_questions_raised)
    emit_list("file_touched", result.files_touched)

    return 0


__all__ = ["add_parser", "run"]
