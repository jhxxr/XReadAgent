# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gateway configuration model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProviderConfig(BaseModel):
    """Per-provider settings. ``base_url`` and ``api_key`` cover the common case;
    ``default_headers`` lets users add e.g. ``HTTP-Referer`` for OpenRouter.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    base_url: str = ""
    api_key: str = ""
    default_headers: dict[str, str] = Field(default_factory=dict)


class LLMGatewayConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
