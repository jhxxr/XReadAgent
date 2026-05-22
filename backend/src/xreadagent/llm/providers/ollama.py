# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ollama provider stub. Real implementation lands in Phase 1."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from xreadagent.llm.config import ProviderConfig
    from xreadagent.llm.gateway import ChatChunk, ChatMessage, ChatResponse


class OllamaProvider:
    def __init__(self, config: "ProviderConfig") -> None:
        self._config = config

    async def chat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> "ChatResponse":
        raise NotImplementedError("planned for Phase 1")

    async def stream_chat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> AsyncIterator["ChatChunk"]:
        raise NotImplementedError("planned for Phase 1")
        if False:
            yield  # pragma: no cover
