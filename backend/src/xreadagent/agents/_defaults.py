# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared default constants for the agent layer.

Kept in a tiny private module so ingest / query / crystallize can all import
the same value without circular imports. The number itself is the upshot of
real-LLM smoke testing: LangChain's ``init_chat_model`` propagates a small
provider default (Anthropic ≈ 4096 tokens) that gets eaten by extended-thinking
models before any structured-output JSON can be emitted. Raising to 16384 is
the lowest budget that lets GLM-5.1 / Claude-Sonnet variants reliably emit a
full ``IngestPlan`` after their thinking tokens.

If a caller needs more (e.g. a 30-page paper triggers a giant ``IngestPlan``),
they pass ``max_tokens=`` explicitly to the agent or set
``XREADAGENT_LLM_MAX_TOKENS`` on the CLI.
"""

from __future__ import annotations

DEFAULT_AGENT_MAX_TOKENS: int = 16384
"""Default ``max_tokens`` applied when constructing the default planner.

A single constant across ingest / query / crystallize because per-provider
tuning belongs in a real ``LLMGateway`` (Phase 2+), not in the agent
constructor. Override per-call via the agent's ``max_tokens=`` kwarg or via
``--max-tokens`` / ``XREADAGENT_LLM_MAX_TOKENS``.
"""

__all__ = ["DEFAULT_AGENT_MAX_TOKENS"]
