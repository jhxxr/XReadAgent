# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared argparse helpers — flags wired identically across ``ingest`` and ``query``.

Three concerns are factored here:

- ``add_llm_runtime_flags`` adds ``--header`` / ``--user-agent`` /
  ``--planner-method`` / ``--env-override`` to a subparser so the flag UX
  stays consistent.
- ``resolve_headers`` merges three sources (env vars, ``XREADAGENT_LLM_HEADERS``,
  explicit ``--header NAME=VALUE`` flags) with documented precedence.
- ``resolve_env_override`` honors either the flag or
  ``XREADAGENT_ENV_OVERRIDE=1``.

Kept separate from each subcommand module so a third subcommand (e.g.
``crystallize``) can opt in without copy-pasting.
"""

from __future__ import annotations

import argparse
import os

from xreadagent.agents.ingest import PlannerMethod
from xreadagent.cli.env import parse_headers_spec

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
            "known nested-list-as-string proxy bug."
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


__all__ = [
    "add_llm_runtime_flags",
    "resolve_env_override",
    "resolve_headers",
]
