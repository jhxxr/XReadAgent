# SPDX-License-Identifier: AGPL-3.0-or-later
"""LangChain / deepagents-backed agent layer.

The rest of the codebase deliberately stays framework-agnostic; everything that
talks to LangChain types lives under this package. Import surfaces are kept
narrow so a future swap of harness only touches files in here.
"""

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
from xreadagent.agents.tools import build_ingest_tools

__all__ = [
    "IngestAgent",
    "IngestConceptTouch",
    "IngestPaperPage",
    "IngestPlan",
    "IngestResult",
    "apply_plan",
    "build_ingest_tools",
    "ingest_source",
]
