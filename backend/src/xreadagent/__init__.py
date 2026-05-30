# SPDX-License-Identifier: AGPL-3.0-or-later
"""XReadAgent — scientific research agent with LLM-Wiki memory."""

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

__version__ = "0.0.2"
