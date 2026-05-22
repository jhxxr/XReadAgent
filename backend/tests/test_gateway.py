# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMGateway routing + provider stub tests."""

from __future__ import annotations

import pytest

from xreadagent.llm import (
    ChatMessage,
    LLMGateway,
    LLMGatewayConfig,
    ProviderConfig,
)
from xreadagent.llm.providers.openai_compat import OpenAICompatProvider


def test_gateway_unknown_prefix_raises() -> None:
    gw = LLMGateway()
    with pytest.raises(ValueError):
        # Bypass the async call entry — provider lookup itself fails first.
        gw._get_provider("totally-unknown")


def test_gateway_split_model_requires_colon() -> None:
    from xreadagent.llm.gateway import _split_model

    with pytest.raises(ValueError):
        _split_model("no-colon-here")
    with pytest.raises(ValueError):
        _split_model("openai:")
    with pytest.raises(ValueError):
        _split_model(":gpt-4")
    assert _split_model("openai:gpt-4o") == ("openai", "gpt-4o")
    assert _split_model("Anthropic:claude-sonnet-4-6") == ("anthropic", "claude-sonnet-4-6")


async def test_stub_provider_chat_raises() -> None:
    gw = LLMGateway()
    for prefix in ("anthropic", "gemini", "ollama"):
        with pytest.raises(NotImplementedError):
            await gw.chat(
                [ChatMessage(role="user", content="hi")],
                model=f"{prefix}:any-model",
            )


async def test_stub_provider_stream_raises() -> None:
    gw = LLMGateway()
    for prefix in ("anthropic", "gemini", "ollama"):
        with pytest.raises(NotImplementedError):
            async for _ in gw.stream_chat(
                [ChatMessage(role="user", content="hi")],
                model=f"{prefix}:any-model",
            ):
                pass


async def test_openai_compat_chat_against_mock_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json as _json

    import httpx

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["json"] = _json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "pong"},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def make_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", make_client)

    provider = OpenAICompatProvider(
        ProviderConfig(base_url="https://example.invalid", api_key="sk-test")
    )
    from xreadagent.llm.gateway import ChatMessage as Msg

    response = await provider.chat(
        [Msg(role="user", content="ping")],
        model="gpt-4o-mini",
        temperature=0.0,
    )

    assert response.content == "pong"
    assert response.model == "gpt-4o-mini"
    assert captured["url"] == "https://example.invalid/v1/chat/completions"
    assert captured["auth"] == "Bearer sk-test"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "gpt-4o-mini"
    assert payload["messages"] == [{"role": "user", "content": "ping"}]
    assert payload["stream"] is False


async def test_gateway_routes_openai_to_openai_provider() -> None:
    gw = LLMGateway(
        LLMGatewayConfig(
            providers={
                "openai": ProviderConfig(
                    base_url="https://example.invalid",
                    api_key="sk-x",
                )
            }
        )
    )
    provider = gw._get_provider("openai")
    assert isinstance(provider, OpenAICompatProvider)
    # Cached on second lookup.
    assert gw._get_provider("openai") is provider
