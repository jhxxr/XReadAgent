# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command-line entry point for XReadAgent.

Thin orchestration layer over the existing agent / pipeline / wiki modules.
The CLI is intended for smoke-testing the end-to-end ingest and query loops
with a real LLM (``--model anthropic:claude-sonnet-4-6`` etc.) without
spinning up the FastAPI sidecar or the React UI.

Subcommands are split across small modules under ``xreadagent.cli`` to keep
each one auditable and unit-testable in isolation.
"""

from xreadagent.cli.main import main

__all__ = ["main"]
