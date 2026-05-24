# SPDX-License-Identifier: AGPL-3.0-or-later
"""LangChain / deepagents-backed agent layer.

The rest of the codebase deliberately stays framework-agnostic; everything that
talks to LangChain types lives under this package. Import surfaces are kept
narrow so a future swap of harness only touches files in here.
"""

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

__all__ = [
    "CitedEvidence",
    "CrystallizeAgent",
    "CrystallizeConceptPatch",
    "CrystallizePaperPatch",
    "CrystallizePlan",
    "CrystallizePlanner",
    "CrystallizeProposal",
    "CrystallizeResult",
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
