# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ``xreadagent.cli.env`` and ``xreadagent.cli.llm_flags``.

Covers:

- ``load_env_files(..., override=True)`` actually wins over pre-set env vars
  (the Claude-Code-leaks-its-own-ANTHROPIC_vars escape hatch).
- ``parse_headers_spec`` matches the documented ``XREADAGENT_LLM_HEADERS``
  comma-separated grammar and tolerates whitespace.
- ``resolve_headers`` merges env + CLI flags with the right precedence.
- ``resolve_env_override`` honors both the flag and the env var.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from xreadagent.cli.env import load_env_files, parse_headers_spec
from xreadagent.cli.llm_flags import (
    add_llm_runtime_flags,
    resolve_env_override,
    resolve_headers,
)


def _write_env(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_load_env_files_does_not_override_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://shell-wins.example/")
    env_file = _write_env(
        tmp_path / ".env.local", 'ANTHROPIC_BASE_URL="https://file-loses.example/"\n'
    )
    load_env_files(env_file)
    import os

    assert os.environ["ANTHROPIC_BASE_URL"] == "https://shell-wins.example/"


def test_load_env_files_override_true_wins_over_shell_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://shell-loses.example/")
    env_file = _write_env(
        tmp_path / ".env.local", "ANTHROPIC_BASE_URL=https://file-wins.example/\n"
    )
    load_env_files(env_file, override=True)
    import os

    assert os.environ["ANTHROPIC_BASE_URL"] == "https://file-wins.example/"


def test_load_env_files_first_candidate_still_wins_under_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    workspace_env = _write_env(tmp_path / "ws.env", "ANTHROPIC_API_KEY=workspace-wins\n")
    cwd_env = _write_env(tmp_path / "cwd.env", "ANTHROPIC_API_KEY=cwd-loses\n")
    load_env_files(workspace_env, cwd_env, override=True)
    import os

    assert os.environ["ANTHROPIC_API_KEY"] == "workspace-wins"


def test_parse_headers_spec_handles_whitespace_and_quotes() -> None:
    parsed = parse_headers_spec(
        " user-agent = claude-cli/2.0 ,  x-trace-id=abc , x-stainless-arch="
    )
    assert parsed == {
        "user-agent": "claude-cli/2.0",
        "x-trace-id": "abc",
        "x-stainless-arch": "",
    }


def test_parse_headers_spec_skips_malformed_entries() -> None:
    parsed = parse_headers_spec("good=ok,no-equals-here,=missing-name,another=fine")
    assert parsed == {"good": "ok", "another": "fine"}


def test_parse_headers_spec_empty_returns_empty() -> None:
    assert parse_headers_spec("") == {}
    assert parse_headers_spec("   ") == {}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    add_llm_runtime_flags(parser)
    return parser


def test_resolve_headers_from_cli_flags_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XREADAGENT_LLM_HEADERS", raising=False)
    monkeypatch.delenv("XREADAGENT_LLM_USER_AGENT", raising=False)
    args = _build_parser().parse_args(
        [
            "--header",
            "user-agent=claude-cli/2.0",
            "--header",
            "x-trace-id=abc",
        ]
    )
    headers = resolve_headers(args)
    assert headers == {"user-agent": "claude-cli/2.0", "x-trace-id": "abc"}


def test_resolve_headers_user_agent_flag_wins_over_header_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XREADAGENT_LLM_HEADERS", raising=False)
    monkeypatch.delenv("XREADAGENT_LLM_USER_AGENT", raising=False)
    args = _build_parser().parse_args(
        [
            "--header",
            "user-agent=will-be-overridden",
            "--user-agent",
            "final-ua/1.0",
        ]
    )
    headers = resolve_headers(args)
    assert headers["user-agent"] == "final-ua/1.0"


def test_resolve_headers_env_var_then_cli_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XREADAGENT_LLM_HEADERS", "user-agent=env-ua,x-trace=env-trace")
    monkeypatch.setenv("XREADAGENT_LLM_USER_AGENT", "ua-from-dedicated-env")
    args = _build_parser().parse_args(["--header", "x-trace=cli-trace"])
    headers = resolve_headers(args)
    # XREADAGENT_LLM_USER_AGENT beats the value the LLM_HEADERS env had for user-agent.
    assert headers["user-agent"] == "ua-from-dedicated-env"
    # CLI --header beats the env-var entry.
    assert headers["x-trace"] == "cli-trace"


def test_resolve_headers_returns_empty_when_nothing_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XREADAGENT_LLM_HEADERS", raising=False)
    monkeypatch.delenv("XREADAGENT_LLM_USER_AGENT", raising=False)
    args = _build_parser().parse_args([])
    assert resolve_headers(args) == {}


def test_resolve_env_override_via_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XREADAGENT_ENV_OVERRIDE", raising=False)
    args = _build_parser().parse_args(["--env-override"])
    assert resolve_env_override(args) is True


def test_resolve_env_override_via_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XREADAGENT_ENV_OVERRIDE", "yes")
    args = _build_parser().parse_args([])
    assert resolve_env_override(args) is True


def test_resolve_env_override_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XREADAGENT_ENV_OVERRIDE", raising=False)
    args = _build_parser().parse_args([])
    assert resolve_env_override(args) is False
