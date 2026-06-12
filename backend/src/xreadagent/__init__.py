# SPDX-License-Identifier: AGPL-3.0-or-later
"""XReadAgent — scientific research agent with LLM-Wiki memory.

Agent classes are re-exported lazily (PEP 562). Eager top-level re-exports
pulled the whole LangChain / langgraph / langsmith import chain into every
``import xreadagent`` — ~0.4s of warm sidecar startup and the dominant cost
of a cold (first-run) start, which risked the Electron loader's 30s startup
timeout. ``from xreadagent import IngestAgent`` still works; the agents
package is only imported on first attribute access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from xreadagent.agents import (
        CrystallizeAgent,
        CrystallizePlan,
        CrystallizeResult,
        IngestAgent,
        IngestPlan,
        IngestResult,
        QueryAgent,
        QueryAnswer,
        QueryResult,
        answer_query,
        apply_crystallize,
        ingest_source,
    )

_AGENT_EXPORTS = frozenset(
    {
        "CrystallizeAgent",
        "CrystallizePlan",
        "CrystallizeResult",
        "IngestAgent",
        "IngestPlan",
        "IngestResult",
        "QueryAgent",
        "QueryAnswer",
        "QueryResult",
        "answer_query",
        "apply_crystallize",
        "ingest_source",
    }
)

__all__ = [
    "CrystallizeAgent",
    "CrystallizePlan",
    "CrystallizeResult",
    "IngestAgent",
    "IngestPlan",
    "IngestResult",
    "QueryAgent",
    "QueryAnswer",
    "QueryResult",
    "__version__",
    "answer_query",
    "apply_crystallize",
    "ingest_source",
]

__version__ = "0.0.9"


def __getattr__(name: str) -> Any:
    if name in _AGENT_EXPORTS:
        import importlib

        return getattr(importlib.import_module("xreadagent.agents"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
