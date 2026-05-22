# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI sidecar endpoint + SIDECAR_READY contract tests."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from typing import Any

import httpx
from fastapi.testclient import TestClient

from xreadagent.api.main import create_app


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
