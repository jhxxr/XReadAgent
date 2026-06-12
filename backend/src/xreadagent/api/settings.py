# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistent application settings stored at ``~/.xreadagent/settings.json``.

Settings are loaded/saved atomically so a crash mid-write never corrupts the
file.

Provider-centric model config lives here too: a list of :class:`Provider`
entries (each with a format mode, base URL, API key, and a list of models) plus
per-feature :class:`ModelRef` assignments. API keys are persisted in this file
alongside the rest of the config — acceptable for a single-user desktop app and
the only place the app/API path reads them from (no env-var fallback).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from xreadagent.wiki.atomic import atomic_write_bytes

_SETTINGS_DIR = Path.home() / ".xreadagent"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

AppLanguage = Literal["en", "zh"]

#: The two API wire formats a provider can speak. ``openai`` covers every
#: OpenAI-compatible endpoint (OpenAI, DeepSeek, OpenRouter, local proxies, …);
#: ``anthropic`` covers the Anthropic Messages API.
ProviderFormat = Literal["openai", "anthropic"]

#: Features that can each be pointed at a different model.
FeatureName = Literal["ingest", "query", "translate"]


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class ModelEntry(_Strict):
    """One model offered by a provider (camelCase wire format).

    ``id`` is the identifier sent to the provider API (e.g. ``gpt-4o``);
    ``name`` is an optional human-facing label shown in the UI.
    """

    id: str
    name: str = ""


class Provider(_Strict):
    """A configured model provider (camelCase wire format).

    ``id`` is a stable, user-editable short slug used to reference the provider
    from a :class:`ModelRef`. ``format`` selects the API wire format; ``baseUrl``
    and ``apiKey`` are the connection credentials; ``models`` is the curated /
    fetched model list (list order is display order).
    """

    id: str
    name: str = ""
    format: ProviderFormat = "openai"
    baseUrl: str = ""
    apiKey: str = ""
    enabled: bool = True
    models: list[ModelEntry] = Field(default_factory=list)


class ModelRef(_Strict):
    """A pointer to one model of one provider, used for feature assignment."""

    providerId: str
    modelId: str


class FeatureModels(_Strict):
    """Per-feature model assignment. ``None`` means the feature is unassigned."""

    ingest: ModelRef | None = None
    query: ModelRef | None = None
    translate: ModelRef | None = None


class AppSettings(_Strict):
    """Persisted application settings (camelCase wire format).

    ``model`` is the legacy single ``provider:model`` string, kept so existing
    settings files keep validating; new config flows through ``providers`` +
    ``featureModels``.
    """

    model: str = ""
    workspacePath: str = ""
    language: AppLanguage = "zh"
    providers: list[Provider] = Field(default_factory=list)
    featureModels: FeatureModels = Field(default_factory=FeatureModels)


class UpdateSettingsRequest(_Strict):
    """Body of ``PUT /api/settings`` — partial update.

    ``providers`` and ``featureModels``, when present, replace the stored value
    wholesale (the renderer owns the full list and PUTs it back in one shot).
    """

    model: str | None = None
    workspacePath: str | None = None
    language: AppLanguage | None = None
    providers: list[Provider] | None = None
    featureModels: FeatureModels | None = None


def load_settings() -> AppSettings:
    """Read settings from disk, returning defaults if the file is missing."""
    if not _SETTINGS_FILE.exists():
        return AppSettings()
    try:
        raw = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        return AppSettings.model_validate(raw)
    except (json.JSONDecodeError, ValueError):
        # Corrupted file — return defaults rather than crashing.
        return AppSettings()


def save_settings(settings: AppSettings) -> None:
    """Persist settings to disk atomically."""
    data = settings.model_dump(mode="json")
    atomic_write_bytes(_SETTINGS_FILE, json.dumps(data, indent=2).encode("utf-8"))


def merge_settings(current: AppSettings, update: UpdateSettingsRequest) -> AppSettings:
    """Return a new ``AppSettings`` with non-None fields from *update* applied.

    ``providers`` and ``featureModels`` are replaced wholesale when present.
    """
    data = current.model_dump(mode="json")
    if update.model is not None:
        data["model"] = update.model
    if update.workspacePath is not None:
        data["workspacePath"] = update.workspacePath
    if update.language is not None:
        data["language"] = update.language
    if update.providers is not None:
        data["providers"] = [p.model_dump(mode="json") for p in update.providers]
    if update.featureModels is not None:
        data["featureModels"] = update.featureModels.model_dump(mode="json")
    return AppSettings.model_validate(data)


def resolve_feature_model(
    settings: AppSettings, feature: FeatureName
) -> tuple[Provider, ModelEntry] | None:
    """Resolve a feature's assigned ``(provider, model)`` from settings.

    Returns ``None`` when the feature is unassigned, the referenced provider is
    missing or disabled, or the referenced model is no longer on the provider.
    Callers map the result onto a ``provider:model`` string + connection
    credentials for ``init_chat_model``.
    """
    ref: ModelRef | None = getattr(settings.featureModels, feature)
    if ref is None:
        return None
    provider = next(
        (p for p in settings.providers if p.id == ref.providerId and p.enabled),
        None,
    )
    if provider is None:
        return None
    model = next((m for m in provider.models if m.id == ref.modelId), None)
    if model is None:
        return None
    return provider, model


#: Maps a provider's wire format onto the LangChain ``init_chat_model`` provider
#: prefix. OpenAI-compatible providers all speak the ``openai`` dialect.
_FORMAT_TO_LANGCHAIN_PROVIDER: dict[ProviderFormat, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
}


class ResolvedChatModel(_Strict):
    """A fully-resolved chat target: ``provider:model`` string + credentials.

    ``apiKey`` / ``baseUrl`` are empty strings when unknown (e.g. the legacy
    ``model`` string or an explicit override carries no provider credentials).
    """

    model: str
    apiKey: str = ""
    baseUrl: str = ""


def resolve_chat_model(
    settings: AppSettings, feature: FeatureName, *, override: str | None = None
) -> ResolvedChatModel | None:
    """Resolve the chat target for *feature*, with credentials when available.

    Precedence:

    1. An explicit ``override`` ``provider:model`` string (request-body model) —
       used verbatim, no credentials (advanced / test path).
    2. The feature's assigned provider+model — yields the model string built
       from the provider format plus the provider's base URL and API key.
    3. The legacy single ``model`` string — used verbatim, no credentials.

    Returns ``None`` when nothing is configured. There is intentionally **no
    environment-variable fallback** on the app/API path — credentials come from
    the UI provider config (the CLI keeps its own env-based resolution).
    """
    if override and override.strip():
        return ResolvedChatModel(model=override.strip())
    pair = resolve_feature_model(settings, feature)
    if pair is not None:
        provider, model = pair
        prefix = _FORMAT_TO_LANGCHAIN_PROVIDER[provider.format]
        return ResolvedChatModel(
            model=f"{prefix}:{model.id}",
            apiKey=provider.apiKey,
            baseUrl=provider.baseUrl,
        )
    legacy = settings.model.strip()
    if legacy:
        return ResolvedChatModel(model=legacy)
    return None
