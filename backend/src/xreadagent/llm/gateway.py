# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMGateway — single entry point that routes ``provider:model`` strings to
provider-specific implementations.

Phase 0: OpenAI-compatible provider is wired; Anthropic / Gemini / Ollama are
stubs that raise ``NotImplementedError``. Phase 1 will fill in the stubs and
layer budget / rate-limit / cache / retry on top (see TODO markers).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from xreadagent.llm.config import LLMGatewayConfig, ProviderConfig
from xreadagent.llm.providers.anthropic import AnthropicProvider
from xreadagent.llm.providers.base import BaseProvider
from xreadagent.llm.providers.gemini import GeminiProvider
from xreadagent.llm.providers.ollama import OllamaProvider
from xreadagent.llm.providers.openai_compat import OpenAICompatProvider

Role = Literal["system", "user", "assistant", "tool"]


class ChatMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    role: Role
    content: str


class ChatResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    content: str
    model: str
    raw: dict[str, Any] = Field(default_factory=dict)


class ChatChunk(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    delta: str
    done: bool = False


_PROVIDER_FACTORIES: dict[str, type[BaseProvider]] = {
    "openai": OpenAICompatProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}


def _split_model(provider_and_model: str) -> tuple[str, str]:
    if ":" not in provider_and_model:
        raise ValueError(
            "model must be of the form '<provider>:<model>' "
            f"(e.g. 'openai:gpt-4o'); got {provider_and_model!r}"
        )
    provider, model = provider_and_model.split(":", 1)
    provider = provider.strip().lower()
    model = model.strip()
    if not provider or not model:
        raise ValueError(f"invalid provider:model string: {provider_and_model!r}")
    return provider, model


class LLMGateway:
    """Routes chat calls to the configured provider based on a ``provider:model`` key."""

    def __init__(self, config: LLMGatewayConfig | None = None) -> None:
        self._config = config or LLMGatewayConfig()
        self._provider_cache: dict[str, BaseProvider] = {}

    def _get_provider(self, provider_name: str) -> BaseProvider:
        if provider_name in self._provider_cache:
            return self._provider_cache[provider_name]
        factory = _PROVIDER_FACTORIES.get(provider_name)
        if factory is None:
            raise ValueError(
                f"unknown LLM provider {provider_name!r}; "
                f"expected one of {sorted(_PROVIDER_FACTORIES)}"
            )
        provider_config = self._config.providers.get(provider_name, ProviderConfig())
        instance = factory(provider_config)
        self._provider_cache[provider_name] = instance
        return instance

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> ChatResponse:
        provider_name, model_name = _split_model(model)
        provider = self._get_provider(provider_name)
        return await provider.chat(
            list(messages),
            model=model_name,
            temperature=temperature,
            **kwargs,
        )

    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> AsyncIterator[ChatChunk]:
        provider_name, model_name = _split_model(model)
        provider = self._get_provider(provider_name)
        async for chunk in provider.stream_chat(
            list(messages),
            model=model_name,
            temperature=temperature,
            **kwargs,
        ):
            yield chunk
