# SPDX-License-Identifier: AGPL-3.0-or-later
"""LangChain / deepagents-backed agent layer.

The rest of the codebase deliberately stays framework-agnostic; everything that
talks to LangChain types lives under this package. Import surfaces are kept
narrow so a future swap of harness only touches files in here.

Re-exports are lazy (PEP 562): importing this package — or a schema-only
submodule like ``xreadagent.agents.ingest_schema`` — must not load
langchain/langsmith. The heavy modules (``ingest``, ``query``, ``crystallize``,
``tools``) are imported on first attribute access, keeping sidecar and CLI
startup fast (agents load at request / subcommand time instead).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from xreadagent.agents._defaults import DEFAULT_AGENT_MAX_TOKENS
    from xreadagent.agents.crystallize import (
        CrystallizeAgent,
        CrystallizePlanner,
        CrystallizeProposal,
        CrystallizeResult,
        apply_crystallize,
    )
    from xreadagent.agents.crystallize_schema import (
        CrystallizeConceptPatch,
        CrystallizePaperPatch,
        CrystallizePlan,
    )
    from xreadagent.agents.ingest import (
        IngestAgent,
        IngestResult,
        apply_plan,
    )
    from xreadagent.agents.ingest_schema import (
        IngestConceptTouch,
        IngestPaperPage,
        IngestPlan,
    )
    from xreadagent.agents.orchestrator import ingest_source
    from xreadagent.agents.query import (
        QueryAgent,
        QueryAgentOutcome,
        QueryPlanner,
        QueryResult,
    )
    from xreadagent.agents.query_orchestrator import answer_query
    from xreadagent.agents.query_schema import (
        CitedEvidence,
        QueryAnswer,
    )
    from xreadagent.agents.query_tools import build_query_tools
    from xreadagent.agents.tools import build_ingest_tools

# Maps each public name to the submodule that defines it. `__getattr__`
# imports the submodule on first access — never at package-import time.
_EXPORTS: dict[str, str] = {
    "DEFAULT_AGENT_MAX_TOKENS": "xreadagent.agents._defaults",
    "CrystallizeAgent": "xreadagent.agents.crystallize",
    "CrystallizePlanner": "xreadagent.agents.crystallize",
    "CrystallizeProposal": "xreadagent.agents.crystallize",
    "CrystallizeResult": "xreadagent.agents.crystallize",
    "apply_crystallize": "xreadagent.agents.crystallize",
    "CrystallizeConceptPatch": "xreadagent.agents.crystallize_schema",
    "CrystallizePaperPatch": "xreadagent.agents.crystallize_schema",
    "CrystallizePlan": "xreadagent.agents.crystallize_schema",
    "IngestAgent": "xreadagent.agents.ingest",
    "IngestResult": "xreadagent.agents.ingest",
    "apply_plan": "xreadagent.agents.ingest",
    "IngestConceptTouch": "xreadagent.agents.ingest_schema",
    "IngestPaperPage": "xreadagent.agents.ingest_schema",
    "IngestPlan": "xreadagent.agents.ingest_schema",
    "ingest_source": "xreadagent.agents.orchestrator",
    "QueryAgent": "xreadagent.agents.query",
    "QueryAgentOutcome": "xreadagent.agents.query",
    "QueryPlanner": "xreadagent.agents.query",
    "QueryResult": "xreadagent.agents.query",
    "answer_query": "xreadagent.agents.query_orchestrator",
    "CitedEvidence": "xreadagent.agents.query_schema",
    "QueryAnswer": "xreadagent.agents.query_schema",
    "build_query_tools": "xreadagent.agents.query_tools",
    "build_ingest_tools": "xreadagent.agents.tools",
}

__all__ = [
    "CitedEvidence",
    "CrystallizeAgent",
    "CrystallizeConceptPatch",
    "CrystallizePaperPatch",
    "CrystallizePlan",
    "CrystallizePlanner",
    "CrystallizeProposal",
    "CrystallizeResult",
    "DEFAULT_AGENT_MAX_TOKENS",
    "IngestAgent",
    "IngestConceptTouch",
    "IngestPaperPage",
    "IngestPlan",
    "IngestResult",
    "QueryAgent",
    "QueryAgentOutcome",
    "QueryAnswer",
    "QueryPlanner",
    "QueryResult",
    "answer_query",
    "apply_crystallize",
    "apply_plan",
    "build_ingest_tools",
    "build_query_tools",
    "ingest_source",
]


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is not None:
        import importlib

        return getattr(importlib.import_module(module_name), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
