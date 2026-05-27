# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ``POST /api/ingest`` and ``POST /api/query`` endpoints.

These endpoints delegate to the agent orchestrators.  The tests inject
stub planners so no LLM is ever called.  We verify:

- Successful ingest returns the expected response shape.
- Successful query returns the expected response shape.
- Missing ``model`` (no env var, no request body) returns 422.
- Extra fields in the request body are rejected (strict Pydantic).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from xreadagent.api.main import create_app
from xreadagent.wiki.workspace import Workspace


def _seeded_workspace(tmp_path: Path) -> Workspace:
    """Create a minimal workspace with a source PDF stub."""
    workspace = Workspace.at(tmp_path / "ws")
    workspace.init_empty("Ingest/Query API Test")
    workspace.ensure_layout()
    # Write a minimal source PDF stub.
    pdf_path = workspace.raw_dir / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nfake pdf content\n%%EOF\n")
    return workspace


# ---------------------------------------------------------------------------
# POST /api/ingest
# ---------------------------------------------------------------------------


def test_ingest_rejects_missing_model(tmp_path: Path) -> None:
    """No model in body and no env var -> 422."""
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    # Ensure the env var is not set.
    import os

    os.environ.pop("XREAD_AGENT_MODEL", None)
    response = client.post(
        "/api/ingest",
        json={
            "workspacePath": str(workspace.root),
            "filePath": str(workspace.raw_dir / "paper.pdf"),
        },
    )
    assert response.status_code == 422
    assert "model" in response.json()["detail"].lower()


def test_ingest_rejects_missing_file(tmp_path: Path) -> None:
    """File not found -> 422."""
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.post(
        "/api/ingest",
        json={
            "workspacePath": str(workspace.root),
            "filePath": str(workspace.raw_dir / "nonexistent.pdf"),
            "model": "anthropic:claude-fake",
        },
    )
    assert response.status_code == 422
    assert "not found" in response.json()["detail"]


def test_ingest_rejects_extra_fields(tmp_path: Path) -> None:
    """Strict Pydantic rejects unknown body keys."""
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.post(
        "/api/ingest",
        json={
            "workspacePath": str(workspace.root),
            "filePath": str(workspace.raw_dir / "paper.pdf"),
            "model": "m",
            "mystery": "forbidden",
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/query
# ---------------------------------------------------------------------------


def test_query_rejects_missing_model(tmp_path: Path) -> None:
    """No model in body and no env var -> 422."""
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    import os

    os.environ.pop("XREAD_AGENT_MODEL", None)
    response = client.post(
        "/api/query",
        json={
            "workspacePath": str(workspace.root),
            "question": "What is attention?",
        },
    )
    assert response.status_code == 422
    assert "model" in response.json()["detail"].lower()


def test_query_rejects_empty_question(tmp_path: Path) -> None:
    """Empty question -> 422 from the agent's ValueError."""
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.post(
        "/api/query",
        json={
            "workspacePath": str(workspace.root),
            "question": "",
            "model": "anthropic:claude-fake",
        },
    )
    # The agent raises ValueError for empty questions.
    assert response.status_code == 422


def test_query_rejects_extra_fields(tmp_path: Path) -> None:
    """Strict Pydantic rejects unknown body keys."""
    workspace = _seeded_workspace(tmp_path)
    client = TestClient(create_app())
    response = client.post(
        "/api/query",
        json={
            "workspacePath": str(workspace.root),
            "question": "What?",
            "model": "m",
            "extra_field": "nope",
        },
    )
    assert response.status_code == 422


def test_query_rejects_missing_workspace(tmp_path: Path) -> None:
    """Missing workspace directory -> 400."""
    client = TestClient(create_app())
    response = client.post(
        "/api/query",
        json={
            "workspacePath": str(tmp_path / "nonexistent"),
            "question": "What?",
            "model": "m",
        },
    )
    assert response.status_code == 400


# Suppress accidental unused-import flake.
_ = (Any, pytest)
