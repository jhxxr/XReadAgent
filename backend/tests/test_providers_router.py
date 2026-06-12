# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the provider utility endpoints (fetch models / test model).

The endpoints make a single outbound ``httpx`` call; tests monkeypatch
``httpx.AsyncClient`` with a fake that returns a canned :class:`httpx.Response`
(or raises a request error) and records what was sent.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import xreadagent.api.providers_router as providers_mod
from xreadagent.api.main import create_app
from xreadagent.api.providers_router import _parse_models


def _install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response: httpx.Response | None = None,
    request_error: Exception | None = None,
) -> dict[str, Any]:
    """Patch ``httpx.AsyncClient`` and return a dict recording the sent request."""
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["client_kwargs"] = kwargs

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def get(
            self, url: str, headers: dict[str, str] | None = None
        ) -> httpx.Response:
            captured.update(method="GET", url=url, headers=headers)
            if request_error is not None:
                raise request_error
            assert response is not None
            return response

        async def post(
            self,
            url: str,
            headers: dict[str, str] | None = None,
            json: Any = None,
        ) -> httpx.Response:
            captured.update(method="POST", url=url, headers=headers, json=json)
            if request_error is not None:
                raise request_error
            assert response is not None
            return response

    monkeypatch.setattr(providers_mod.httpx, "AsyncClient", FakeClient)
    return captured


# ---------------------------------------------------------------------------
# _parse_models
# ---------------------------------------------------------------------------


def test_parse_models_openai_shape() -> None:
    payload = {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}
    models = _parse_models(payload)
    assert [m.id for m in models] == ["gpt-4o", "gpt-4o-mini"]
    assert all(m.name == "" for m in models)


def test_parse_models_anthropic_display_name() -> None:
    payload = {"data": [{"id": "claude-x", "display_name": "Claude X"}]}
    models = _parse_models(payload)
    assert models[0].id == "claude-x"
    assert models[0].name == "Claude X"


def test_parse_models_bare_list() -> None:
    payload = [{"id": "m1"}, {"id": "m2"}]
    assert [m.id for m in _parse_models(payload)] == ["m1", "m2"]


def test_parse_models_skips_malformed_items() -> None:
    payload = {"data": [{"no_id": True}, "junk", {"id": ""}, {"id": "good"}]}
    assert [m.id for m in _parse_models(payload)] == ["good"]


def test_parse_models_unexpected_payload() -> None:
    assert _parse_models({"unexpected": 1}) == []
    assert _parse_models(None) == []


# ---------------------------------------------------------------------------
# POST /api/providers/models
# ---------------------------------------------------------------------------


def test_fetch_models_openai_auth_and_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_client(
        monkeypatch,
        response=httpx.Response(200, json={"data": [{"id": "gpt-4o"}]}),
    )
    client = TestClient(create_app())
    resp = client.post(
        "/api/providers/models",
        json={"format": "openai", "baseUrl": "https://api.x.com/v1", "apiKey": "sk-1"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"models": [{"id": "gpt-4o", "name": ""}]}
    assert captured["url"] == "https://api.x.com/v1/models"
    assert captured["headers"]["Authorization"] == "Bearer sk-1"


def test_fetch_models_anthropic_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_client(
        monkeypatch,
        response=httpx.Response(200, json={"data": [{"id": "claude-x"}]}),
    )
    client = TestClient(create_app())
    resp = client.post(
        "/api/providers/models",
        json={"format": "anthropic", "baseUrl": "https://cch.x.de/v1", "apiKey": "k"},
    )
    assert resp.status_code == 200
    assert captured["headers"]["x-api-key"] == "k"
    assert captured["headers"]["anthropic-version"] == providers_mod._ANTHROPIC_VERSION
    assert "Authorization" not in captured["headers"]


def test_fetch_models_requires_base_url() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/api/providers/models", json={"format": "openai", "baseUrl": "  "}
    )
    assert resp.status_code == 422


def test_fetch_models_provider_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_client(
        monkeypatch, response=httpx.Response(401, text="invalid api key")
    )
    client = TestClient(create_app())
    resp = client.post(
        "/api/providers/models",
        json={"format": "openai", "baseUrl": "https://api.x.com/v1", "apiKey": "bad"},
    )
    assert resp.status_code == 502
    assert "401" in resp.json()["detail"]


def test_fetch_models_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_client(monkeypatch, request_error=httpx.ConnectError("boom"))
    client = TestClient(create_app())
    resp = client.post(
        "/api/providers/models",
        json={"format": "openai", "baseUrl": "https://nope.invalid/v1"},
    )
    assert resp.status_code == 502
    assert "could not reach provider" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/providers/test
# ---------------------------------------------------------------------------


def test_test_model_ok_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_client(
        monkeypatch, response=httpx.Response(200, json={"choices": []})
    )
    client = TestClient(create_app())
    resp = client.post(
        "/api/providers/test",
        json={
            "format": "openai",
            "baseUrl": "https://api.x.com/v1",
            "apiKey": "sk-1",
            "modelId": "gpt-4o",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["error"] is None
    assert isinstance(body["latencyMs"], int)
    assert captured["url"] == "https://api.x.com/v1/chat/completions"
    assert captured["json"]["model"] == "gpt-4o"


def test_test_model_anthropic_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_client(
        monkeypatch, response=httpx.Response(200, json={})
    )
    client = TestClient(create_app())
    resp = client.post(
        "/api/providers/test",
        json={
            "format": "anthropic",
            "baseUrl": "https://cch.x.de/v1",
            "apiKey": "k",
            "modelId": "claude-x",
        },
    )
    assert resp.status_code == 200
    assert captured["url"] == "https://cch.x.de/v1/messages"
    assert captured["headers"]["anthropic-version"] == providers_mod._ANTHROPIC_VERSION


def test_test_model_failure_status_returns_ok_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_client(
        monkeypatch, response=httpx.Response(404, text="model not found")
    )
    client = TestClient(create_app())
    resp = client.post(
        "/api/providers/test",
        json={
            "format": "openai",
            "baseUrl": "https://api.x.com/v1",
            "modelId": "ghost",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "404" in body["error"]


def test_test_model_network_error_returns_ok_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_client(monkeypatch, request_error=httpx.ConnectError("down"))
    client = TestClient(create_app())
    resp = client.post(
        "/api/providers/test",
        json={
            "format": "openai",
            "baseUrl": "https://nope.invalid/v1",
            "modelId": "m",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "could not reach provider" in body["error"]


def test_test_model_requires_model_id() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/api/providers/test",
        json={"format": "openai", "baseUrl": "https://api.x.com/v1", "modelId": " "},
    )
    assert resp.status_code == 422
