# SPDX-License-Identifier: AGPL-3.0-or-later
"""Provider utility endpoints: fetch a provider's model list and test a model.

Both endpoints are **stateless** — they take an unsaved provider draft in the
request body so the renderer can fetch / test before persisting the provider to
settings. Credentials never touch disk here; they are used only for the single
outbound call.

- ``POST /api/providers/models`` → lists the models a provider exposes
  (``GET {baseUrl}/models`` with format-appropriate auth).
- ``POST /api/providers/test``   → a minimal chat round-trip that verifies the
  base URL + API key + model id actually work.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from xreadagent.api.settings import ProviderFormat

#: Anthropic requires this header on every request; pin a stable version.
_ANTHROPIC_VERSION = "2023-06-01"
_TIMEOUT_S = 30.0
#: Cap provider error bodies echoed back to the UI so a stray HTML page can't
#: flood the toast.
_MAX_ERROR_CHARS = 300


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class FetchModelsRequest(_Strict):
    """Unsaved provider draft used to list available models."""

    format: ProviderFormat
    baseUrl: str
    apiKey: str = ""
    headers: dict[str, str] = Field(default_factory=dict)


class FetchedModel(_Strict):
    id: str
    name: str = ""


class FetchModelsResponse(_Strict):
    models: list[FetchedModel]


class TestModelRequest(_Strict):
    """Unsaved provider draft + a model id to verify connectivity against."""

    format: ProviderFormat
    baseUrl: str
    modelId: str
    apiKey: str = ""
    headers: dict[str, str] = Field(default_factory=dict)


class TestModelResponse(_Strict):
    ok: bool
    latencyMs: int | None = None
    error: str | None = None


def _truncate(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _MAX_ERROR_CHARS else text[:_MAX_ERROR_CHARS] + "…"


def _auth_headers(
    fmt: ProviderFormat, api_key: str, extra: dict[str, str]
) -> dict[str, str]:
    """Build auth headers for *fmt*; caller-supplied *extra* wins on conflict."""
    headers: dict[str, str] = {}
    if fmt == "anthropic":
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = _ANTHROPIC_VERSION
    else:  # openai-compatible
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
    headers.update(extra)
    return headers


def _join(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _parse_models(payload: Any) -> list[FetchedModel]:
    """Normalize OpenAI / Anthropic model-list payloads to ``[{id, name}]``.

    Both formats return ``{"data": [...]}``; some OpenAI-compatible proxies
    return a bare list. Anthropic items carry a ``display_name`` we use as the
    label. Items without a string ``id`` are skipped.
    """
    if isinstance(payload, dict):
        data = payload.get("data")
    else:
        data = payload
    if not isinstance(data, list):
        return []
    models: list[FetchedModel] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        display = item.get("display_name")
        name = display if isinstance(display, str) else ""
        models.append(FetchedModel(id=model_id, name=name))
    return models


providers_router = APIRouter()


@providers_router.post("/providers/models", response_model=FetchModelsResponse)
async def fetch_models(req: FetchModelsRequest) -> FetchModelsResponse:
    if not req.baseUrl.strip():
        raise HTTPException(status_code=422, detail="baseUrl is required")
    url = _join(req.baseUrl, "models")
    headers = _auth_headers(req.format, req.apiKey, req.headers)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail=f"could not reach provider: {exc}"
        ) from exc
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"provider returned {resp.status_code}: {_truncate(resp.text)}",
        )
    try:
        payload = resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail="provider returned a non-JSON model list"
        ) from exc
    return FetchModelsResponse(models=_parse_models(payload))


@providers_router.post("/providers/test", response_model=TestModelResponse)
async def test_model(req: TestModelRequest) -> TestModelResponse:
    if not req.baseUrl.strip():
        raise HTTPException(status_code=422, detail="baseUrl is required")
    if not req.modelId.strip():
        raise HTTPException(status_code=422, detail="modelId is required")
    headers = _auth_headers(req.format, req.apiKey, req.headers)
    headers["content-type"] = "application/json"
    if req.format == "anthropic":
        url = _join(req.baseUrl, "messages")
    else:
        url = _join(req.baseUrl, "chat/completions")
    body = {
        "model": req.modelId,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "ping"}],
    }
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(url, headers=headers, json=body)
    except httpx.RequestError as exc:
        return TestModelResponse(ok=False, error=f"could not reach provider: {exc}")
    latency_ms = int((time.monotonic() - start) * 1000)
    if resp.status_code >= 400:
        return TestModelResponse(
            ok=False,
            latencyMs=latency_ms,
            error=f"{resp.status_code}: {_truncate(resp.text)}",
        )
    return TestModelResponse(ok=True, latencyMs=latency_ms)
