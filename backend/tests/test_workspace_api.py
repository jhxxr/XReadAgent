# SPDX-License-Identifier: AGPL-3.0-or-later
"""``GET /api/translations/manifest`` + ``GET /api/workspaces/file`` tests.

These two endpoints are the read-only HTTP surface the Phase 2B PDF reader
hits from the renderer (see ``frontend/src/lib/api.ts:79-119``). They have
no dependency on the translation worker, so the tests build a real
:class:`Workspace` on disk and exercise the FastAPI app with no stub
service. The deny-list / path-traversal assertions are the security
contract — keep them sharp.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from xreadagent.api.main import create_app
from xreadagent.translation.manifest import TranslationEntry, TranslationsIndex
from xreadagent.wiki.workspace import Workspace


def _seeded_workspace(tmp_path: Path) -> Workspace:
    workspace = Workspace.at(tmp_path / "ws")
    workspace.init_empty("Workspace API Test")
    return workspace


def _write_manifest_entry(workspace: Workspace) -> TranslationEntry:
    index = TranslationsIndex.load(workspace)
    entry = TranslationEntry(
        sourceSlug="attention-aaa",
        sourceHash="aaa",
        targetLang="zh",
        model="anthropic:claude-sonnet-4-6",
        monoPath="translations/attention-aaa.mono.pdf",
        dualPath="translations/attention-aaa.dual.pdf",
        translatedAt="2026-05-25T10:00:00Z",
        durationS=12.5,
        babeldocVersion="0.6.2",
    )
    index.add(entry)
    index.save()
    return entry


# ---------------------------------------------------------------------------
# /api/translations/manifest
# ---------------------------------------------------------------------------


def test_manifest_returns_camel_case_payload_when_present(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    entry = _write_manifest_entry(workspace)
    client = TestClient(create_app())
    response = client.get(
        "/api/translations/manifest", params={"workspacePath": str(workspace.root)}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == 1
    assert len(body["entries"]) == 1
    row = body["entries"][0]
    # camelCase enforced by the Pydantic wire schema.
    assert row["sourceSlug"] == entry.sourceSlug
    assert row["sourceHash"] == entry.sourceHash
    assert row["targetLang"] == entry.targetLang
    assert row["model"] == entry.model
    assert row["monoPath"] == entry.monoPath
    assert row["dualPath"] == entry.dualPath


def test_manifest_returns_404_when_file_missing(tmp_path: Path) -> None:
    """A workspace whose translations/manifest.json was never created → 404."""
    workspace = Workspace.at(tmp_path / "ws")
    workspace.ensure_layout()
    # Intentionally do NOT call init_empty — the manifest file is absent.
    assert not workspace.translations_manifest_path.exists()
    client = TestClient(create_app())
    response = client.get(
        "/api/translations/manifest", params={"workspacePath": str(workspace.root)}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "manifest not found"


def test_manifest_rejects_missing_workspace_dir(tmp_path: Path) -> None:
    bogus = tmp_path / "does-not-exist"
    client = TestClient(create_app())
    response = client.get(
        "/api/translations/manifest", params={"workspacePath": str(bogus)}
    )
    assert response.status_code == 400
    assert "not an existing directory" in response.json()["detail"]


def test_manifest_rejects_missing_query_param(tmp_path: Path) -> None:
    """FastAPI auto-validates required Query params → 422."""
    client = TestClient(create_app())
    response = client.get("/api/translations/manifest")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /api/workspaces/file
# ---------------------------------------------------------------------------


def test_file_endpoint_streams_pdf_bytes_from_translations(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    pdf_path = workspace.translations_dir / "sample.dual.pdf"
    pdf_bytes = b"%PDF-1.4\n%hello from translation\n%%EOF\n"
    pdf_path.write_bytes(pdf_bytes)

    client = TestClient(create_app())
    response = client.get(
        "/api/workspaces/file",
        params={"workspacePath": str(workspace.root), "path": "translations/sample.dual.pdf"},
    )
    assert response.status_code == 200, response.text
    assert response.content == pdf_bytes
    assert response.headers["content-type"].startswith("application/pdf")


def test_file_endpoint_streams_from_raw_dir(tmp_path: Path) -> None:
    """``raw/`` is in the allowlist — source PDFs render in the Original tab."""
    workspace = _seeded_workspace(tmp_path)
    pdf_path = workspace.raw_dir / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 raw")
    client = TestClient(create_app())
    response = client.get(
        "/api/workspaces/file",
        params={"workspacePath": str(workspace.root), "path": "raw/source.pdf"},
    )
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 raw"


def test_file_endpoint_returns_octet_stream_for_non_pdf(tmp_path: Path) -> None:
    """Non-PDF files in the allowlist fall back to octet-stream."""
    workspace = _seeded_workspace(tmp_path)
    md_path = workspace.extracts_dir / "paper.md"
    md_path.write_text("# Extract\n", encoding="utf-8")
    client = TestClient(create_app())
    response = client.get(
        "/api/workspaces/file",
        params={"workspacePath": str(workspace.root), "path": "extracts/paper.md"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/octet-stream")


def test_file_endpoint_returns_404_for_missing_file(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/workspaces/file",
        params={"workspacePath": str(workspace.root), "path": "translations/missing.pdf"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "file not found"


def test_file_endpoint_rejects_parent_traversal(tmp_path: Path) -> None:
    """``../../escape`` resolves outside the workspace and must be blocked."""
    workspace = _seeded_workspace(tmp_path)
    # A neighbouring file the attacker is hoping to read.
    sibling = tmp_path / "secret.txt"
    sibling.write_text("top secret\n", encoding="utf-8")
    client = TestClient(create_app())
    response = client.get(
        "/api/workspaces/file",
        params={"workspacePath": str(workspace.root), "path": "../secret.txt"},
    )
    assert response.status_code == 400
    assert "escapes workspace" in response.json()["detail"]


def test_file_endpoint_rejects_absolute_path(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/workspaces/file",
        params={
            "workspacePath": str(workspace.root),
            # Absolute path — must be rejected regardless of whether the file exists.
            "path": str((tmp_path / "anything.pdf").as_posix()),
        },
    )
    assert response.status_code == 400
    assert "workspace-relative" in response.json()["detail"]


def test_file_endpoint_rejects_state_dir(tmp_path: Path) -> None:
    """``state/`` is deny-listed even if the requested file exists."""
    workspace = _seeded_workspace(tmp_path)
    # The conversation log path lives under state/ — confirm we never expose it.
    workspace.conversation_log_path.write_text("{\"event\":\"x\"}\n", encoding="utf-8")
    client = TestClient(create_app())
    response = client.get(
        "/api/workspaces/file",
        params={
            "workspacePath": str(workspace.root),
            "path": "state/conversation-log.jsonl",
        },
    )
    assert response.status_code == 403
    assert "state" in response.json()["detail"]


def test_file_endpoint_rejects_wiki_dir(tmp_path: Path) -> None:
    """``wiki/`` (the synthesis zone) is deny-listed."""
    workspace = _seeded_workspace(tmp_path)
    # init_empty already wrote wiki/index.md, so the file exists — the 403 has
    # to come from the allowlist check, not the file-exists check.
    assert workspace.index_md_path.exists()
    client = TestClient(create_app())
    response = client.get(
        "/api/workspaces/file",
        params={"workspacePath": str(workspace.root), "path": "wiki/index.md"},
    )
    assert response.status_code == 403


def test_file_endpoint_rejects_missing_path_param(tmp_path: Path) -> None:
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.get(
        "/api/workspaces/file", params={"workspacePath": str(workspace.root)}
    )
    assert response.status_code == 422
