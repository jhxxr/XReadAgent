# SPDX-License-Identifier: AGPL-3.0-or-later
"""Base provider protocol — every provider implementation must satisfy this shape."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from xreadagent.llm.config import ProviderConfig
    from xreadagent.llm.gateway import ChatChunk, ChatMessage, ChatResponse


@runtime_checkable
class BaseProvider(Protocol):
    """All providers accept the same constructor + call shape."""

    def __init__(self, config: "ProviderConfig") -> None: ...

    async def chat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> "ChatResponse": ...

    def stream_chat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> AsyncIterator["ChatChunk"]: ...
