# SPDX-License-Identifier: AGPL-3.0-or-later
"""CLI smoke tests.

NO real LLM calls are made: ingest / query use the stub planner exposed via
``--stub-planner`` / ``XREADAGENT_STUB_PLANNER=1``. The tests cover:

- ``xreadagent init`` end-to-end (create + idempotent re-run + non-empty guard).
- ``xreadagent show`` against a hand-seeded workspace.
- ``xreadagent ingest --stub-planner`` end-to-end through the orchestrator.
- ``xreadagent query --stub-planner`` end-to-end.
- ``provider:model`` string validation and the api-key-missing message.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from xreadagent.cli.env import ensure_provider_credentials, required_env_var_for_model
from xreadagent.cli.main import main
from xreadagent.schemas.wiki_pages import ConceptFrontmatter, PaperFrontmatter
from xreadagent.wiki.pages import write_concept_page, write_paper_page
from xreadagent.wiki.workspace import Workspace


def _run(
    argv: list[str],
    *,
    capsys: pytest.CaptureFixture[str] | None = None,
) -> tuple[int, str, str]:
    """Run the CLI and capture stdout + stderr in one call."""
    if capsys is not None:
        rc = main(argv)
        captured = capsys.readouterr()
        return rc, captured.out, captured.err
    # Manual capture fallback (kept for clarity even though unused).
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        rc = main(argv)
        return rc, sys.stdout.getvalue(), sys.stderr.getvalue()
    finally:
        sys.stdout, sys.stderr = old_out, old_err


def _drop_raw(workspace: Workspace, name: str, content: str) -> Path:
    path = workspace.raw_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_creates_workspace_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "fresh"
    rc, out, _err = _run(
        ["init", str(target), "--title", "Test Workspace"], capsys=capsys
    )
    assert rc == 0
    assert "status: initialized" in out
    assert "title: Test Workspace" in out

    workspace = Workspace.at(target)
    assert workspace.is_initialized()
    assert workspace.index_md_path.exists()
    assert workspace.log_md_path.exists()
    assert workspace.raw_dir.exists()
    assert workspace.extracts_dir.exists()
    assert workspace.state_dir.exists()
    assert workspace.sources_json_path.exists()


def test_init_is_idempotent_on_second_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "twice"
    first_rc, _, _ = _run(["init", str(target), "--title", "X"], capsys=capsys)
    assert first_rc == 0

    second_rc, out, _ = _run(["init", str(target), "--title", "X"], capsys=capsys)
    assert second_rc == 0
    assert "status: already-initialized" in out


def test_init_refuses_nonempty_unrelated_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "dirty"
    target.mkdir()
    (target / "leftover.txt").write_text("hi", encoding="utf-8")

    rc, _, err = _run(["init", str(target), "--title", "X"], capsys=capsys)
    assert rc == 1
    assert "non-empty" in err


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def _seed_workspace(tmp_path: Path) -> Workspace:
    workspace = Workspace.at(tmp_path / "ws")
    workspace.init_empty("Seeded")
    write_paper_page(
        workspace,
        "seed-paper-aaaaaaaa",
        PaperFrontmatter(
            title="Seed Paper", source="raw/_processed/seed.md", source_hash="aaaaaaaa"
        ),
        {"Background": "seed bg body"},
    )
    write_concept_page(
        workspace,
        "seed-concept",
        ConceptFrontmatter(title="Seed Concept", aliases=["sc"]),
        {"Summary": "seed concept summary body"},
    )
    return workspace


def test_show_paper_prints_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = _seed_workspace(tmp_path)
    rc, out, _ = _run(
        [
            "show",
            "--workspace",
            str(workspace.root),
            "paper",
            "seed-paper-aaaaaaaa",
        ],
        capsys=capsys,
    )
    assert rc == 0
    assert "seed bg body" in out
    assert "page_type: paper" in out


def test_show_concept_prints_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = _seed_workspace(tmp_path)
    rc, out, _ = _run(
        [
            "show",
            "--workspace",
            str(workspace.root),
            "concept",
            "seed-concept",
        ],
        capsys=capsys,
    )
    assert rc == 0
    assert "seed concept summary body" in out
    assert "aliases" in out


def test_show_index_and_log_succeed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = _seed_workspace(tmp_path)

    rc, out, _ = _run(
        ["show", "--workspace", str(workspace.root), "index"], capsys=capsys
    )
    assert rc == 0
    assert "Seeded" in out

    rc2, out2, _ = _run(
        ["show", "--workspace", str(workspace.root), "log"], capsys=capsys
    )
    assert rc2 == 0
    assert "Seeded" in out2


def test_show_missing_paper_returns_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = _seed_workspace(tmp_path)
    rc, _, err = _run(
        [
            "show",
            "--workspace",
            str(workspace.root),
            "paper",
            "nonexistent-slug",
        ],
        capsys=capsys,
    )
    assert rc == 1
    assert "file not found" in err


# ---------------------------------------------------------------------------
# ingest --stub-planner
# ---------------------------------------------------------------------------


def test_ingest_with_stub_planner_writes_wiki(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace_path = tmp_path / "ws"
    rc_init, _, _ = _run(
        ["init", str(workspace_path), "--title", "Ingest Test"], capsys=capsys
    )
    assert rc_init == 0
    workspace = Workspace.at(workspace_path)

    raw = _drop_raw(workspace, "sample.md", "# Sample\n\nA body.")

    rc, out, _ = _run(
        [
            "ingest",
            str(raw),
            "--workspace",
            str(workspace_path),
            "--stub-planner",
            "--model",
            "anthropic:claude-fake",
            "--title",
            "Sample Paper",
        ],
        capsys=capsys,
    )

    assert rc == 0, out
    assert "cache_hit: false" in out
    assert "paper_page: wiki/papers/" in out

    # Paper page exists.
    paper_files = list(workspace.papers_dir.iterdir())
    assert len(paper_files) == 1
    paper_text = paper_files[0].read_text(encoding="utf-8")
    assert "(stub) background section" in paper_text

    # The concept page from the stub also landed.
    concept_path = workspace.concepts_dir / "stub-concept.md"
    assert concept_path.exists()


def test_ingest_rejects_missing_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "x.md"
    raw.write_text("hi", encoding="utf-8")
    rc, _, err = _run(
        [
            "ingest",
            str(raw),
            "--workspace",
            str(tmp_path / "missing"),
            "--stub-planner",
        ],
        capsys=capsys,
    )
    assert rc == 1
    assert "not initialized" in err


def test_ingest_missing_api_key_names_env_var(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_path = tmp_path / "ws"
    _run(["init", str(workspace_path), "--title", "X"], capsys=capsys)
    raw = _drop_raw(Workspace.at(workspace_path), "x.md", "hi")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # No .env.local will be found.

    rc, _, err = _run(
        [
            "ingest",
            str(raw),
            "--workspace",
            str(workspace_path),
            "--model",
            "anthropic:claude-sonnet-4-6",
        ],
        capsys=capsys,
    )
    assert rc == 1
    assert "ANTHROPIC_API_KEY" in err


# ---------------------------------------------------------------------------
# query --stub-planner
# ---------------------------------------------------------------------------


def test_query_with_stub_planner_archives_under_queries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace_path = tmp_path / "ws"
    _run(["init", str(workspace_path), "--title", "Q Test"], capsys=capsys)

    rc, out, _ = _run(
        [
            "query",
            "what is the role of attention?",
            "--workspace",
            str(workspace_path),
            "--stub-planner",
            "--model",
            "openai:gpt-fake",
            "--topic",
            "smoke",
        ],
        capsys=capsys,
    )
    assert rc == 0
    assert "archive_path: wiki/queries/smoke/" in out

    queries_dir = Workspace.at(workspace_path).queries_dir / "smoke"
    assert queries_dir.exists()
    files = list(queries_dir.iterdir())
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "stub answer" in body


def test_query_with_stub_planner_keeps_synthesis_zone_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = _seed_workspace(tmp_path)

    def _digest(path: Path) -> bytes:
        import hashlib

        h = hashlib.sha256()
        for f in sorted(path.rglob("*")):
            if f.is_file():
                h.update(f.read_bytes())
                h.update(b"|")
        return h.digest()

    pre_papers = _digest(workspace.papers_dir)
    pre_concepts = _digest(workspace.concepts_dir)
    pre_index = workspace.index_md_path.read_bytes()
    pre_log = workspace.log_md_path.read_bytes()

    rc, _out, _ = _run(
        [
            "query",
            "anything?",
            "--workspace",
            str(workspace.root),
            "--stub-planner",
        ],
        capsys=capsys,
    )
    assert rc == 0

    assert _digest(workspace.papers_dir) == pre_papers
    assert _digest(workspace.concepts_dir) == pre_concepts
    assert workspace.index_md_path.read_bytes() == pre_index
    assert workspace.log_md_path.read_bytes() == pre_log


# ---------------------------------------------------------------------------
# Provider / env-var validation
# ---------------------------------------------------------------------------


def test_required_env_var_for_known_providers() -> None:
    assert required_env_var_for_model("openai:gpt-4o") == "OPENAI_API_KEY"
    assert required_env_var_for_model("anthropic:claude-sonnet-4-6") == "ANTHROPIC_API_KEY"
    assert required_env_var_for_model("google_genai:gemini-2.5-pro") == "GOOGLE_API_KEY"
    assert required_env_var_for_model("ollama:llama3.1:70b") is None


def test_required_env_var_rejects_bad_string() -> None:
    with pytest.raises(ValueError, match="provider:name"):
        required_env_var_for_model("no-colon-here")
    with pytest.raises(ValueError, match="unknown LLM provider"):
        required_env_var_for_model("nonexistent:foo")


def test_ensure_provider_credentials_passes_when_var_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    assert ensure_provider_credentials("anthropic:claude") == "ANTHROPIC_API_KEY"


def test_ensure_provider_credentials_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        ensure_provider_credentials("openai:gpt-4o")


def test_cli_version_flag_does_not_crash(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    out = capsys.readouterr().out
    assert "xreadagent" in out


def test_unknown_command_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["bogus-command"])
    assert isinstance(info.value.code, int)
    assert info.value.code != 0


# ---------------------------------------------------------------------------
# New: --header / --user-agent / --planner-method / --env-override flags
# ---------------------------------------------------------------------------


def test_ingest_help_documents_new_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["ingest", "--help"])
    out = capsys.readouterr().out
    for fragment in ("--header", "--user-agent", "--planner-method", "--env-override"):
        assert fragment in out, fragment


def test_query_help_documents_new_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["query", "--help"])
    out = capsys.readouterr().out
    for fragment in ("--header", "--user-agent", "--planner-method", "--env-override"):
        assert fragment in out, fragment


def test_ingest_threads_custom_headers_into_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Use --stub-planner but spy on the IngestAgent constructor to capture headers.

    The stub-planner path skips the model wiring, so we patch ``_build_agent``
    in the subcommand module to assert what was passed in instead. Indirect
    but keeps the test deterministic with no LLM call.
    """
    monkeypatch.delenv("XREADAGENT_LLM_HEADERS", raising=False)
    monkeypatch.delenv("XREADAGENT_LLM_USER_AGENT", raising=False)
    workspace_path = tmp_path / "ws"
    _run(["init", str(workspace_path), "--title", "X"], capsys=capsys)
    workspace = Workspace.at(workspace_path)
    raw = _drop_raw(workspace, "x.md", "# X\nbody")

    captured: dict[str, object] = {}

    import xreadagent.cli.ingest_cmd as ingest_cmd
    from xreadagent.agents.ingest import IngestAgent
    from xreadagent.cli.stubs import stub_ingest_planner

    def fake_build_agent(
        ws: Workspace,
        model: str,
        *,
        force_stub: bool,
        headers: dict[str, str],
        planner_method: str,
    ) -> IngestAgent:
        captured["headers"] = headers
        captured["planner_method"] = planner_method
        return IngestAgent(ws, planner=stub_ingest_planner)

    monkeypatch.setattr(ingest_cmd, "_build_agent", fake_build_agent)

    rc, _out, _err = _run(
        [
            "ingest",
            str(raw),
            "--workspace",
            str(workspace_path),
            "--model",
            "anthropic:claude-fake",
            "--stub-planner",
            "--header",
            "user-agent=will-be-overridden",
            "--user-agent",
            "claude-cli/2.0",
            "--header",
            "x-stainless-arch=",
            "--planner-method",
            "json",
        ],
        capsys=capsys,
    )

    assert rc == 0
    assert captured["headers"] == {
        "user-agent": "claude-cli/2.0",
        "x-stainless-arch": "",
    }
    assert captured["planner_method"] == "json"


def test_query_threads_custom_headers_into_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("XREADAGENT_LLM_HEADERS", raising=False)
    monkeypatch.delenv("XREADAGENT_LLM_USER_AGENT", raising=False)
    workspace_path = tmp_path / "ws"
    _run(["init", str(workspace_path), "--title", "X"], capsys=capsys)

    captured: dict[str, object] = {}

    import xreadagent.cli.query_cmd as query_cmd
    from xreadagent.agents.query import QueryAgent
    from xreadagent.cli.stubs import stub_query_planner

    def fake_build_agent(
        ws: Workspace,
        model: str,
        *,
        force_stub: bool,
        headers: dict[str, str],
        planner_method: str,
    ) -> QueryAgent:
        captured["headers"] = headers
        captured["planner_method"] = planner_method
        return QueryAgent(ws, planner=stub_query_planner)

    monkeypatch.setattr(query_cmd, "_build_agent", fake_build_agent)

    rc, _out, _err = _run(
        [
            "query",
            "what?",
            "--workspace",
            str(workspace_path),
            "--model",
            "openai:gpt-fake",
            "--stub-planner",
            "--header",
            "x-trace=42",
            "--planner-method",
            "tool",
        ],
        capsys=capsys,
    )
    assert rc == 0
    assert captured["headers"] == {"x-trace": "42"}
    assert captured["planner_method"] == "tool"


def test_ingest_agent_headers_property_round_trips(tmp_path: Path) -> None:
    from xreadagent.agents.ingest import IngestAgent
    from xreadagent.cli.stubs import stub_ingest_planner

    workspace = Workspace.at(tmp_path / "ws")
    workspace.init_empty("X")
    agent = IngestAgent(
        workspace,
        planner=stub_ingest_planner,
        headers={"user-agent": "ua/1.0"},
        planner_method="json",
    )
    assert agent.headers == {"user-agent": "ua/1.0"}
    assert agent.planner_method == "json"


def test_ingest_env_override_flag_makes_envfile_win(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--env-override` actually swaps the precedence inside the ingest command."""
    workspace_path = tmp_path / "ws"
    _run(["init", str(workspace_path), "--title", "X"], capsys=capsys)
    workspace = Workspace.at(workspace_path)
    raw = _drop_raw(workspace, "x.md", "# X\nbody")

    # Pre-set the env so .env.local would normally lose.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "shell-key")
    (workspace.root / ".env.local").write_text(
        "ANTHROPIC_API_KEY=envfile-key\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    rc, _out, _err = _run(
        [
            "ingest",
            str(raw),
            "--workspace",
            str(workspace_path),
            "--stub-planner",
            "--env-override",
        ],
        capsys=capsys,
    )
    assert rc == 0
    import os

    assert os.environ["ANTHROPIC_API_KEY"] == "envfile-key"
