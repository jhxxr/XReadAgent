# SPDX-License-Identifier: AGPL-3.0-or-later
"""XReadAgent — scientific research agent with LLM-Wiki memory."""

from xreadagent.agents import (
    IngestAgent,
    IngestPlan,
    IngestResult,
    ingest_source,
)

__all__ = [
    "IngestAgent",
    "IngestPlan",
    "IngestResult",
    "__version__",
    "ingest_source",
]

__version__ = "0.0.1"
