# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAI-compatible HTTP provider.

Targets any server that speaks the ``/v1/chat/completions`` shape — OpenAI,
DeepSeek, OpenRouter, vLLM, LM Studio, etc. Keeps the implementation
dependency-light (``httpx`` only). Retry / budget / cache wiring is deferred.

TODO(phase-1): add retry-with-backoff, per-call budget enforcement, response
cache, and provider-aware error normalization.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from xreadagent.llm.config import ProviderConfig
    from xreadagent.llm.gateway import ChatChunk, ChatMessage, ChatResponse


class OpenAICompatProvider:
    def __init__(self, config: "ProviderConfig") -> None:
        self._config = config
        self._base_url = (config.base_url or "https://api.openai.com").rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        headers.update(self._config.default_headers)
        return headers

    def _payload(
        self,
        messages: list["ChatMessage"],
        *,
        model: str,
        temperature: float,
        stream: bool,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": stream,
        }
        payload.update(extra)
        return payload

    async def chat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> "ChatResponse":
        from xreadagent.llm.gateway import ChatResponse

        payload = self._payload(
            messages,
            model=model,
            temperature=temperature,
            stream=False,
            extra=dict(kwargs),
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            data = response.json()
        choices = data.get("choices") or []
        content = ""
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
        return ChatResponse(content=content, model=model, raw=data)

    async def stream_chat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> AsyncIterator["ChatChunk"]:
        from xreadagent.llm.gateway import ChatChunk

        payload = self._payload(
            messages,
            model=model,
            temperature=temperature,
            stream=True,
            extra=dict(kwargs),
        )
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers(),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:") :].strip()
                    if data_str == "[DONE]":
                        yield ChatChunk(delta="", done=True)
                        return
                    try:
                        chunk_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk_data.get("choices") or []
                    if not choices:
                        continue
                    delta_obj = choices[0].get("delta") or {}
                    delta = delta_obj.get("content") or ""
                    if delta:
                        yield ChatChunk(delta=delta, done=False)
