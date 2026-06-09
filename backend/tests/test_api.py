# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI sidecar endpoint + SIDECAR_READY contract tests."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from xreadagent.api.main import create_app
from xreadagent.wiki.workspace import Workspace


def test_healthz_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["version"], str)
    assert body["version"]


def test_websocket_hello_and_echo() -> None:
    client = TestClient(create_app())
    with client.websocket_connect("/ws/events") as ws:
        hello = ws.receive_json()
        assert hello == {"type": "hello"}
        ws.send_text("ping")
        echoed = ws.receive_text()
        assert echoed == "ping"


def test_cors_allows_localhost() -> None:
    client = TestClient(create_app())
    response = client.get(
        "/healthz",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


_SPA_SENTINEL = '<!doctype html><div id="root">SPA</div>'
_ASSET_CONTENT = "console.log('x')"


def _write_fake_frontend(root: Path) -> None:
    (root / "index.html").write_text(_SPA_SENTINEL, encoding="utf-8")
    assets = root / "assets"
    assets.mkdir()
    (assets / "app.js").write_text(_ASSET_CONTENT, encoding="utf-8")


def test_spa_root_serves_index_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_fake_frontend(tmp_path)
    monkeypatch.setenv("XREAD_FRONTEND_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/")
    assert response.status_code == 200
    assert _SPA_SENTINEL in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_spa_fallback_serves_index_for_client_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_fake_frontend(tmp_path)
    monkeypatch.setenv("XREAD_FRONTEND_DIR", str(tmp_path))
    client = TestClient(create_app())

    # /workspace is a client-side route with no matching file on disk.
    response = client.get("/workspace")
    assert response.status_code == 200
    assert _SPA_SENTINEL in response.text


def test_spa_serves_static_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_fake_frontend(tmp_path)
    monkeypatch.setenv("XREAD_FRONTEND_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert response.text == _ASSET_CONTENT


def test_api_404_not_swallowed_by_spa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_fake_frontend(tmp_path)
    monkeypatch.setenv("XREAD_FRONTEND_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    # Must NOT be the SPA HTML — it should surface a JSON 404.
    assert _SPA_SENTINEL not in response.text
    assert response.headers["content-type"].startswith("application/json")


def test_healthz_ok_with_frontend_mounted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_fake_frontend(tmp_path)
    monkeypatch.setenv("XREAD_FRONTEND_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_404_when_frontend_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    # No XREAD_FRONTEND_DIR set → API-only default (current behavior preserved).
    monkeypatch.delenv("XREAD_FRONTEND_DIR", raising=False)
    client = TestClient(create_app())

    response = client.get("/")
    assert response.status_code == 404


def test_translation_service_factory_is_cached_per_workspace(tmp_path: Path) -> None:
    workspace_a = Workspace.at(tmp_path / "a")
    workspace_a.init_empty("A")
    workspace_b = Workspace.at(tmp_path / "b")
    workspace_b.init_empty("B")
    source_a = workspace_a.raw_dir / "paper.pdf"
    source_a.write_bytes(b"%PDF-1.4\nfake\n")
    source_b = workspace_b.raw_dir / "paper.pdf"
    source_b.write_bytes(b"%PDF-1.4\nfake\n")

    created: list[Path] = []

    class _StubTranslationService:
        def start_translation(self, request: object) -> str:
            _ = request
            return "job-123"

    def factory(workspace: Workspace) -> _StubTranslationService:
        created.append(workspace.root)
        return _StubTranslationService()

    client = TestClient(create_app(translation_service_factory=factory))  # type: ignore[arg-type]

    for workspace, source in (
        (workspace_a, source_a),
        (workspace_a, source_a),
        (workspace_b, source_b),
    ):
        response = client.post(
            "/api/translate",
            json={
                "workspacePath": str(workspace.root),
                "sourcePath": str(source),
                "model": "anthropic:claude-fake",
            },
        )
        assert response.status_code == 200, response.text

    assert created == [workspace_a.root, workspace_b.root]


def test_sidecar_entrypoint_wires_translation_service_factory() -> None:
    from xreadagent.api.__main__ import _build_server

    server = _build_server(8765)
    app = server.config.app
    assert hasattr(app.state, "translation_service_factory")
    assert app.state.translation_service_factory is not None


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_sidecar_ready(proc: subprocess.Popen[str], timeout: float = 30.0) -> int:
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"sidecar exited early: rc={proc.returncode} stderr={stderr!r}")
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        line = line.strip()
        if line.startswith("SIDECAR_READY port="):
            return int(line.removeprefix("SIDECAR_READY port="))
    raise TimeoutError("SIDECAR_READY line not seen within timeout")


def test_sidecar_subprocess_emits_ready_line() -> None:
    port = _pick_free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "xreadagent.api", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        actual_port = _wait_for_sidecar_ready(proc)
        assert actual_port == port

        # Confirm /healthz actually answers on the reported port.
        response = httpx.get(f"http://127.0.0.1:{actual_port}/healthz", timeout=5.0)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
