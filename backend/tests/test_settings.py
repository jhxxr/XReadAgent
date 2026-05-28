# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ``xreadagent.api.settings`` and the ``GET/PUT /api/settings`` endpoints.

Unit tests cover AppSettings / UpdateSettingsRequest model validation,
load / save / merge functions. Integration tests cover the HTTP surface
through FastAPI's TestClient.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import xreadagent.api.settings as settings_mod
from xreadagent.api.main import create_app
from xreadagent.api.settings import (
    AppSettings,
    UpdateSettingsRequest,
    load_settings,
    merge_settings,
    save_settings,
)

# ---------------------------------------------------------------------------
# AppSettings model
# ---------------------------------------------------------------------------


def test_app_settings_round_trips() -> None:
    s = AppSettings(model="openai:gpt-4o", workspacePath="/tmp/ws")
    assert s.model == "openai:gpt-4o"
    assert s.workspacePath == "/tmp/ws"
    dumped = s.model_dump(mode="json")
    assert dumped == {"model": "openai:gpt-4o", "workspacePath": "/tmp/ws"}
    assert AppSettings.model_validate(dumped) == s


def test_app_settings_defaults_are_empty_strings() -> None:
    s = AppSettings()
    assert s.model == ""
    assert s.workspacePath == ""


def test_app_settings_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AppSettings(model="m", surprise="nope")  # type: ignore[call-arg]


def test_app_settings_required_fields_enforced() -> None:
    """Strict mode: missing required fields should fail, but both have defaults."""
    # AppSettings has defaults for everything, so constructing with no args is fine.
    s = AppSettings()
    assert s.model == ""
    # Explicitly passing None for a str field should fail under strict mode.
    with pytest.raises(ValidationError):
        AppSettings(model=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# UpdateSettingsRequest model
# ---------------------------------------------------------------------------


def test_update_settings_request_all_none() -> None:
    req = UpdateSettingsRequest()
    assert req.model is None
    assert req.workspacePath is None


def test_update_settings_request_partial() -> None:
    req = UpdateSettingsRequest(model="anthropic:claude-sonnet-4-6")
    assert req.model == "anthropic:claude-sonnet-4-6"
    assert req.workspacePath is None


def test_update_settings_request_full() -> None:
    req = UpdateSettingsRequest(model="m", workspacePath="/data")
    assert req.model == "m"
    assert req.workspacePath == "/data"


def test_update_settings_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        UpdateSettingsRequest(model="m", bogus=True)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# load_settings
# ---------------------------------------------------------------------------


def test_load_settings_returns_defaults_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    result = load_settings()
    assert result == AppSettings()


def test_load_settings_reads_valid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    data = {"model": "openai:gpt-4o", "workspacePath": "/home/user/ws"}
    settings_file.write_text(json.dumps(data), encoding="utf-8")

    result = load_settings()
    assert result.model == "openai:gpt-4o"
    assert result.workspacePath == "/home/user/ws"


def test_load_settings_returns_defaults_on_corrupted_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    settings_file.write_text("{invalid json", encoding="utf-8")

    result = load_settings()
    assert result == AppSettings()


def test_load_settings_returns_defaults_on_invalid_field_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    # Strict mode rejects extra fields, which triggers ValueError in model_validate.
    settings_file.write_text(json.dumps({"model": "m", "bogus": True}), encoding="utf-8")

    result = load_settings()
    assert result == AppSettings()


# ---------------------------------------------------------------------------
# save_settings
# ---------------------------------------------------------------------------


def test_save_settings_creates_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_dir = tmp_path / "subdir"
    settings_file = settings_dir / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", settings_dir)

    s = AppSettings(model="test-model", workspacePath="/test")
    save_settings(s)

    assert settings_dir.is_dir()
    assert settings_file.exists()


def test_save_settings_round_trips_with_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    original = AppSettings(
        model="anthropic:claude-3-7-sonnet-latest",
        workspacePath="/data/ws",
    )
    save_settings(original)

    loaded = load_settings()
    assert loaded == original


def test_save_settings_produces_valid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    save_settings(AppSettings(model="m", workspacePath="/p"))

    raw = settings_file.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["model"] == "m"
    assert parsed["workspacePath"] == "/p"


# ---------------------------------------------------------------------------
# merge_settings
# ---------------------------------------------------------------------------


def test_merge_settings_partial_model_update() -> None:
    current = AppSettings(model="old-model", workspacePath="/old-path")
    update = UpdateSettingsRequest(model="new-model")
    merged = merge_settings(current, update)
    assert merged.model == "new-model"
    assert merged.workspacePath == "/old-path"


def test_merge_settings_partial_workspace_path_update() -> None:
    current = AppSettings(model="old-model", workspacePath="/old-path")
    update = UpdateSettingsRequest(workspacePath="/new-path")
    merged = merge_settings(current, update)
    assert merged.model == "old-model"
    assert merged.workspacePath == "/new-path"


def test_merge_settings_full_update() -> None:
    current = AppSettings(model="old-model", workspacePath="/old-path")
    update = UpdateSettingsRequest(model="new-model", workspacePath="/new-path")
    merged = merge_settings(current, update)
    assert merged.model == "new-model"
    assert merged.workspacePath == "/new-path"


def test_merge_settings_none_fields_preserve_current() -> None:
    current = AppSettings(model="preserved", workspacePath="/preserved")
    update = UpdateSettingsRequest()
    merged = merge_settings(current, update)
    assert merged.model == "preserved"
    assert merged.workspacePath == "/preserved"


# ---------------------------------------------------------------------------
# HTTP endpoints: GET /api/settings
# ---------------------------------------------------------------------------


def test_get_settings_returns_defaults_when_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    client = TestClient(create_app())
    response = client.get("/api/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == ""
    assert body["workspacePath"] == ""


def test_get_settings_returns_saved_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    save_settings(AppSettings(model="openai:gpt-4o", workspacePath="/data"))

    client = TestClient(create_app())
    response = client.get("/api/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "openai:gpt-4o"
    assert body["workspacePath"] == "/data"


# ---------------------------------------------------------------------------
# HTTP endpoints: PUT /api/settings
# ---------------------------------------------------------------------------


def test_put_settings_creates_and_returns_updated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    client = TestClient(create_app())
    response = client.put(
        "/api/settings",
        json={"model": "anthropic:claude-sonnet-4-6", "workspacePath": "/home/ws"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "anthropic:claude-sonnet-4-6"
    assert body["workspacePath"] == "/home/ws"

    # Verify persisted to disk.
    loaded = load_settings()
    assert loaded.model == "anthropic:claude-sonnet-4-6"
    assert loaded.workspacePath == "/home/ws"


def test_put_settings_partial_update_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    # Pre-save settings with a model value.
    save_settings(AppSettings(model="openai:gpt-4o", workspacePath="/old-path"))

    client = TestClient(create_app())
    response = client.put(
        "/api/settings",
        json={"workspacePath": "/new-path"},
    )
    assert response.status_code == 200
    body = response.json()
    # model is preserved; workspacePath is updated.
    assert body["model"] == "openai:gpt-4o"
    assert body["workspacePath"] == "/new-path"


def test_put_settings_rejects_extra_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    client = TestClient(create_app())
    response = client.put(
        "/api/settings",
        json={"model": "m", "surprise": "forbidden"},
    )
    assert response.status_code == 422


def test_put_settings_empty_body_returns_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty JSON body has both fields as None — merge preserves current values."""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    save_settings(AppSettings(model="saved-model", workspacePath="/saved"))

    client = TestClient(create_app())
    response = client.put("/api/settings", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "saved-model"
    assert body["workspacePath"] == "/saved"
