# SPDX-License-Identifier: AGPL-3.0-or-later
"""Query agent: navigates the wiki read-only and emits a ``QueryAnswer``.

Mirrors the ``IngestAgent`` shape (pluggable planner protocol so tests don't
need an LLM) but produces a different structured output and never writes to
the synthesis zone. ``answer_query`` in ``query_orchestrator.py`` is what
takes the answer and persists it to ``wiki/queries/...``.

The default planner builds a LangChain structured-output chain just like the
ingest agent's. A future iteration can swap it for a multi-turn deepagents
loop that calls the tools in ``query_tools.py``; the contract (planner
returns ``QueryAnswer``) doesn't change.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import ValidationError

from xreadagent.agents.json_planner import (
    is_nested_list_string_error,
    make_json_planner,
)
from xreadagent.agents.query_schema import QueryAnswer
from xreadagent.agents.query_tools import build_query_tools
from xreadagent.wiki.pages import read_page_frontmatter
from xreadagent.wiki.workspace import Workspace

PlannerMethod = Literal["auto", "tool", "json"]


def _load_system_prompt() -> str:
    resource = resources.files("xreadagent.agents.prompts").joinpath("query_system.md")
    return resource.read_text(encoding="utf-8")


QUERY_SYSTEM_PROMPT = _load_system_prompt()


class QueryPlanner(Protocol):
    """Anything that can turn a question + workspace context into a ``QueryAnswer``.

    The default planner uses LangChain's structured-output API; tests inject
    a stub that returns a pre-built answer so the LLM is never called.
    """

    def __call__(self, prompt: str, *, schema: type[QueryAnswer]) -> QueryAnswer: ...


@dataclass(frozen=True)
class QueryAgentOutcome:
    """Outcome of a single ``QueryAgent.answer`` call.

    Distinct from ``QueryResult`` (which the orchestrator returns) — that
    type carries the archive path the orchestrator wrote. The agent itself
    does not know where the answer was filed.
    """

    answer: QueryAnswer
    tokens_used: dict[str, int] = field(default_factory=dict)
    duration_s: float = 0.0


class QueryAgent:
    """Read-only agent that produces a ``QueryAnswer`` for a researcher's question."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        max_tool_iterations: int = 6,
        planner: QueryPlanner | None = None,
        headers: dict[str, str] | None = None,
        planner_method: PlannerMethod = "auto",
    ) -> None:
        self._workspace = workspace
        self._system_prompt = system_prompt or QUERY_SYSTEM_PROMPT
        self._max_tool_iterations = max_tool_iterations
        self._headers: dict[str, str] = dict(headers or {})
        self._planner_method: PlannerMethod = planner_method
        if planner is not None:
            self._planner: QueryPlanner = planner
        elif model is not None:
            self._planner = _make_default_planner(
                model, headers=self._headers, planner_method=planner_method
            )
        else:
            raise ValueError(
                "QueryAgent requires either an explicit planner or a model string"
            )
        # Tools are built eagerly so callers wiring MCP / a deepagents loop in a
        # future iteration have a handle. The default planner does not invoke them.
        self._tools = build_query_tools(workspace)

    @property
    def tools(self) -> list[Any]:
        return list(self._tools)

    @property
    def headers(self) -> dict[str, str]:
        """Read-only view of the custom headers threaded into the default planner."""
        return dict(self._headers)

    @property
    def planner_method(self) -> PlannerMethod:
        return self._planner_method

    async def answer(self, question: str, *, topic: str | None = None) -> QueryAgentOutcome:
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("question must be non-empty")
        start = time.monotonic()
        prompt = self._build_prompt(clean_question, topic=topic)
        answer = self._planner(prompt, schema=QueryAnswer)
        return QueryAgentOutcome(
            answer=answer,
            tokens_used={},
            duration_s=time.monotonic() - start,
        )

    def _build_prompt(self, question: str, *, topic: str | None) -> str:
        paper_summary = _summarize_papers(self._workspace)
        concept_summary = _summarize_concepts(self._workspace)
        topic_hint = topic.strip() if topic else ""
        topic_block = f"- topic_hint: {topic_hint}\n" if topic_hint else ""
        return (
            f"{self._system_prompt}\n\n"
            f"## Workspace state\n\n"
            f"Existing papers ({len(paper_summary)}):\n"
            + ("\n".join(f"- {row}" for row in paper_summary) or "_(none)_")
            + "\n\n"
            f"Existing concepts ({len(concept_summary)}):\n"
            + ("\n".join(f"- {row}" for row in concept_summary) or "_(none)_")
            + "\n\n"
            "## Question\n\n"
            f"{topic_block}"
            f"- question: {question}\n"
        )


def _summarize_papers(workspace: Workspace) -> list[str]:
    rows: list[str] = []
    if not workspace.papers_dir.exists():
        return rows
    for path in sorted(workspace.papers_dir.iterdir()):
        if not path.is_file() or path.suffix != ".md":
            continue
        try:
            fm = read_page_frontmatter(path)
        except (OSError, UnicodeDecodeError):
            fm = {}
        title = fm.get("title", "") if isinstance(fm, dict) else ""
        rows.append(f"{path.stem} — {title}")
    return rows


def _summarize_concepts(workspace: Workspace) -> list[str]:
    rows: list[str] = []
    if not workspace.concepts_dir.exists():
        return rows
    for path in sorted(workspace.concepts_dir.iterdir()):
        if not path.is_file() or path.suffix != ".md":
            continue
        try:
            fm = read_page_frontmatter(path)
        except (OSError, UnicodeDecodeError):
            fm = {}
        title = fm.get("title", "") if isinstance(fm, dict) else ""
        aliases_raw = fm.get("aliases", []) if isinstance(fm, dict) else []
        aliases = [str(a) for a in aliases_raw] if isinstance(aliases_raw, list) else []
        alias_part = f" (aliases: {', '.join(aliases)})" if aliases else ""
        rows.append(f"{path.stem} — {title}{alias_part}")
    return rows


def _make_default_planner(
    model: str,
    *,
    headers: dict[str, str] | None = None,
    planner_method: PlannerMethod = "auto",
) -> QueryPlanner:
    """Build a planner that uses LangChain's structured-output API.

    Imported lazily so the rest of the package stays importable when the
    LangChain extras are not installed. See ``ingest._make_default_planner``
    for the headers / planner_method rationale — same proxy-compat story.
    """
    from langchain.chat_models import init_chat_model

    init_kwargs: dict[str, Any] = {}
    if headers:
        init_kwargs["default_headers"] = dict(headers)

    try:
        chat = init_chat_model(model, **init_kwargs)
    except TypeError:
        chat = init_chat_model(model)

    tool_structured = chat.with_structured_output(QueryAnswer)
    json_plan = make_json_planner(chat)

    def _invoke_tool(prompt: str) -> QueryAnswer:
        result = tool_structured.invoke(prompt)
        if isinstance(result, QueryAnswer):
            return result
        return QueryAnswer.model_validate(result)

    def _plan(prompt: str, *, schema: type[QueryAnswer]) -> QueryAnswer:
        if planner_method == "json":
            result: QueryAnswer = json_plan(prompt, schema=schema)
            return result
        if planner_method == "tool":
            return _invoke_tool(prompt)
        try:
            return _invoke_tool(prompt)
        except ValidationError as exc:
            if not is_nested_list_string_error(exc):
                raise
            print(
                "[xreadagent] structured-output (tool) returned a nested list "
                "as a string; retrying with JSON-mode planner",
                file=sys.stderr,
                flush=True,
            )
            fallback: QueryAnswer = json_plan(prompt, schema=schema)
            return fallback

    return _plan


@dataclass(frozen=True)
class QueryResult:
    """What the orchestrator returns from ``answer_query``."""

    answer: QueryAnswer
    query_page_path: Path
    files_touched: list[str]
    tokens_used: dict[str, int] = field(default_factory=dict)
    duration_s: float = 0.0


__all__ = [
    "QUERY_SYSTEM_PROMPT",
    "QueryAgent",
    "QueryAgentOutcome",
    "QueryPlanner",
    "QueryResult",
]
