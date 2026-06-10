# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistent application settings stored at ``~/.xreadagent/settings.json``.

Settings are loaded/saved atomically so a crash mid-write never corrupts the
file.  API keys are intentionally excluded — they stay in env vars for
security.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from xreadagent.wiki.atomic import atomic_write_bytes

_SETTINGS_DIR = Path.home() / ".xreadagent"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

AppLanguage = Literal["en", "zh"]


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class AppSettings(_Strict):
    """Persisted application settings (camelCase wire format)."""

    model: str = ""
    workspacePath: str = ""
    language: AppLanguage = "zh"


class UpdateSettingsRequest(_Strict):
    """Body of ``PUT /api/settings`` — partial update."""

    model: str | None = None
    workspacePath: str | None = None
    language: AppLanguage | None = None


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
    """Return a new ``AppSettings`` with non-None fields from *update* applied."""
    data = current.model_dump(mode="json")
    if update.model is not None:
        data["model"] = update.model
    if update.workspacePath is not None:
        data["workspacePath"] = update.workspacePath
    if update.language is not None:
        data["language"] = update.language
    return AppSettings.model_validate(data)
