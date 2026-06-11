# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared argparse helpers — flags wired identically across ``ingest`` and ``query``.

Three concerns are factored here:

- ``add_llm_runtime_flags`` adds ``--header`` / ``--user-agent`` /
  ``--planner-method`` / ``--env-override`` / ``--max-tokens`` to a subparser
  so the flag UX stays consistent.
- ``resolve_headers`` merges three sources (env vars, ``XREADAGENT_LLM_HEADERS``,
  explicit ``--header NAME=VALUE`` flags) with documented precedence.
- ``resolve_env_override`` honors either the flag or
  ``XREADAGENT_ENV_OVERRIDE=1``.
- ``resolve_max_tokens`` merges the ``--max-tokens`` flag and
  ``XREADAGENT_LLM_MAX_TOKENS`` env var, falling back to ``None`` (the
  sentinel that means "use the agent default").

Kept separate from each subcommand module so a third subcommand (e.g.
``crystallize``) can opt in without copy-pasting.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TYPE_CHECKING

from xreadagent.cli.env import parse_headers_spec

if TYPE_CHECKING:
    from xreadagent.agents.ingest import PlannerMethod

_PLANNER_METHODS: tuple[PlannerMethod, ...] = ("auto", "tool", "json")


def add_llm_runtime_flags(parser: argparse.ArgumentParser) -> None:
    """Add the LLM-runtime flags every agent subcommand should expose."""
    parser.add_argument(
        "--header",
        dest="headers",
        action="append",
        default=None,
        metavar="NAME=VALUE",
        help=(
            "Add a custom header to LLM API calls (repeatable). Use to set a "
            "User-Agent the proxy accepts (e.g. 'user-agent=claude-cli/2.0') "
            "or to clear a proxy-stripped header (e.g. 'x-stainless-arch=')."
        ),
    )
    parser.add_argument(
        "--user-agent",
        dest="user_agent",
        type=str,
        default=None,
        help=(
            "Shorthand for --header user-agent=UA. Wins over --header when "
            "both target user-agent. Also reads XREADAGENT_LLM_USER_AGENT."
        ),
    )
    parser.add_argument(
        "--planner-method",
        dest="planner_method",
        choices=list(_PLANNER_METHODS),
        default="auto",
        help=(
            "How to coax structured output from the model. 'tool' uses "
            "with_structured_output(); 'json' uses raw JSON mode + repair; "
            "'auto' (default) tries tool first and falls back to json on the "
            "known nested-list-as-string proxy bug or when the tool path "
            "returns nothing (typically a max_tokens budget exhaustion)."
        ),
    )
    parser.add_argument(
        "--env-override",
        dest="env_override",
        action="store_true",
        help=(
            "Let .env.local override shell-exported env vars. Use when "
            "running inside Claude Code (or another agent) whose own "
            "ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN leaks into the "
            "child env and points at the wrong endpoint. Also reads "
            "XREADAGENT_ENV_OVERRIDE=1."
        ),
    )
    parser.add_argument(
        "--max-tokens",
        dest="max_tokens",
        type=int,
        default=None,
        help=(
            "Override the chat model's max_tokens reply budget. Default: the "
            "agent's DEFAULT_AGENT_MAX_TOKENS constant (16384). Raise this "
            "when extended-thinking models (GLM-5.1, Claude Opus thinking, "
            "etc.) eat the budget on internal reasoning and the structured "
            "output comes back empty. Also reads XREADAGENT_LLM_MAX_TOKENS "
            "as a fallback."
        ),
    )


def resolve_headers(args: argparse.Namespace) -> dict[str, str]:
    """Merge env vars + ``--header`` + ``--user-agent`` flags into one mapping.

    Precedence (later wins):
    1. ``XREADAGENT_LLM_HEADERS`` env var (parsed as ``name=val,name=val``).
    2. ``XREADAGENT_LLM_USER_AGENT`` env var.
    3. ``--header NAME=VALUE`` CLI flags (in order).
    4. ``--user-agent UA`` CLI flag.

    Header names are case-insensitively deduped — we lower-case on store so
    the dict has one canonical entry per header (LangChain proxies treat
    headers case-insensitively per HTTP).
    """
    merged: dict[str, str] = {}
    spec = os.environ.get("XREADAGENT_LLM_HEADERS", "").strip()
    if spec:
        for name, value in parse_headers_spec(spec).items():
            merged[name.lower()] = value
    env_ua = os.environ.get("XREADAGENT_LLM_USER_AGENT", "").strip()
    if env_ua:
        merged["user-agent"] = env_ua
    cli_headers: list[str] | None = getattr(args, "headers", None)
    if cli_headers:
        for raw in cli_headers:
            if "=" not in raw:
                continue
            name, value = raw.split("=", 1)
            name = name.strip()
            if not name:
                continue
            merged[name.lower()] = value.strip()
    cli_ua: str | None = getattr(args, "user_agent", None)
    if cli_ua:
        merged["user-agent"] = cli_ua.strip()
    return merged


def resolve_env_override(args: argparse.Namespace) -> bool:
    """Return True iff the user opted into ``.env.local`` overriding shell env."""
    if bool(getattr(args, "env_override", False)):
        return True
    return os.environ.get("XREADAGENT_ENV_OVERRIDE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def resolve_max_tokens(args: argparse.Namespace) -> int | None:
    """Resolve the effective ``max_tokens`` from CLI flag + env var.

    Precedence (later wins):
    1. ``XREADAGENT_LLM_MAX_TOKENS`` env var (parsed as int; non-int values
       trigger a one-line stderr warning and are ignored).
    2. ``--max-tokens N`` CLI flag.

    Returns ``None`` when neither is set — the agent's
    ``DEFAULT_AGENT_MAX_TOKENS`` constant will then apply at construction
    time. Returns the resolved positive integer otherwise. We intentionally
    do NOT cap the upper bound here; the model provider will reject anything
    out of range on its own with a clearer error than we could synthesize.
    """
    resolved: int | None = None
    raw_env = os.environ.get("XREADAGENT_LLM_MAX_TOKENS", "").strip()
    if raw_env:
        try:
            resolved = int(raw_env)
        except ValueError:
            print(
                f"[xreadagent] ignoring XREADAGENT_LLM_MAX_TOKENS={raw_env!r}; "
                "must be an integer",
                file=sys.stderr,
                flush=True,
            )
    cli_value = getattr(args, "max_tokens", None)
    if isinstance(cli_value, int):
        resolved = cli_value
    if resolved is not None and resolved <= 0:
        # Non-positive values would silently disable the budget on some
        # providers; treat as a mis-configuration and fall back to default.
        print(
            f"[xreadagent] ignoring non-positive max_tokens={resolved!r}; "
            "using agent default",
            file=sys.stderr,
            flush=True,
        )
        return None
    return resolved


__all__ = [
    "add_llm_runtime_flags",
    "resolve_env_override",
    "resolve_headers",
    "resolve_max_tokens",
]
