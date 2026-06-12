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
    FeatureModels,
    ModelEntry,
    ModelRef,
    Provider,
    UpdateSettingsRequest,
    load_settings,
    merge_settings,
    resolve_chat_model,
    resolve_feature_model,
    save_settings,
)

# ---------------------------------------------------------------------------
# AppSettings model
# ---------------------------------------------------------------------------


def test_app_settings_round_trips() -> None:
    s = AppSettings(model="openai:gpt-4o", workspacePath="/tmp/ws", language="zh")
    assert s.model == "openai:gpt-4o"
    assert s.workspacePath == "/tmp/ws"
    assert s.language == "zh"
    dumped = s.model_dump(mode="json")
    assert dumped == {
        "model": "openai:gpt-4o",
        "workspacePath": "/tmp/ws",
        "language": "zh",
        "providers": [],
        "featureModels": {"ingest": None, "query": None, "translate": None},
    }
    assert AppSettings.model_validate(dumped) == s


def test_app_settings_defaults_are_empty_strings() -> None:
    s = AppSettings()
    assert s.model == ""
    assert s.workspacePath == ""
    assert s.language == "zh"


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
    with pytest.raises(ValidationError):
        AppSettings(language="fr")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# UpdateSettingsRequest model
# ---------------------------------------------------------------------------


def test_update_settings_request_all_none() -> None:
    req = UpdateSettingsRequest()
    assert req.model is None
    assert req.workspacePath is None
    assert req.language is None


def test_update_settings_request_partial() -> None:
    req = UpdateSettingsRequest(model="anthropic:claude-sonnet-4-6", language="zh")
    assert req.model == "anthropic:claude-sonnet-4-6"
    assert req.workspacePath is None
    assert req.language == "zh"


def test_update_settings_request_full() -> None:
    req = UpdateSettingsRequest(model="m", workspacePath="/data", language="en")
    assert req.model == "m"
    assert req.workspacePath == "/data"
    assert req.language == "en"


def test_update_settings_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        UpdateSettingsRequest(model="m", bogus=True)  # type: ignore[call-arg]


def test_update_settings_request_rejects_invalid_language() -> None:
    with pytest.raises(ValidationError):
        UpdateSettingsRequest(language="fr")  # type: ignore[arg-type]


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

    data = {"model": "openai:gpt-4o", "workspacePath": "/home/user/ws", "language": "zh"}
    settings_file.write_text(json.dumps(data), encoding="utf-8")

    result = load_settings()
    assert result.model == "openai:gpt-4o"
    assert result.workspacePath == "/home/user/ws"
    assert result.language == "zh"


def test_load_settings_defaults_language_for_legacy_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    settings_file.write_text(
        json.dumps({"model": "openai:gpt-4o", "workspacePath": "/home/user/ws"}),
        encoding="utf-8",
    )

    result = load_settings()
    assert result.model == "openai:gpt-4o"
    assert result.workspacePath == "/home/user/ws"
    assert result.language == "zh"


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

    s = AppSettings(model="test-model", workspacePath="/test", language="zh")
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
        language="zh",
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

    save_settings(AppSettings(model="m", workspacePath="/p", language="zh"))

    raw = settings_file.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["model"] == "m"
    assert parsed["workspacePath"] == "/p"
    assert parsed["language"] == "zh"


# ---------------------------------------------------------------------------
# merge_settings
# ---------------------------------------------------------------------------


def test_merge_settings_partial_model_update() -> None:
    current = AppSettings(model="old-model", workspacePath="/old-path", language="zh")
    update = UpdateSettingsRequest(model="new-model")
    merged = merge_settings(current, update)
    assert merged.model == "new-model"
    assert merged.workspacePath == "/old-path"
    assert merged.language == "zh"


def test_merge_settings_partial_workspace_path_update() -> None:
    current = AppSettings(model="old-model", workspacePath="/old-path", language="zh")
    update = UpdateSettingsRequest(workspacePath="/new-path")
    merged = merge_settings(current, update)
    assert merged.model == "old-model"
    assert merged.workspacePath == "/new-path"
    assert merged.language == "zh"


def test_merge_settings_partial_language_update() -> None:
    current = AppSettings(model="old-model", workspacePath="/old-path", language="en")
    update = UpdateSettingsRequest(language="zh")
    merged = merge_settings(current, update)
    assert merged.model == "old-model"
    assert merged.workspacePath == "/old-path"
    assert merged.language == "zh"


def test_merge_settings_full_update() -> None:
    current = AppSettings(model="old-model", workspacePath="/old-path", language="en")
    update = UpdateSettingsRequest(model="new-model", workspacePath="/new-path", language="zh")
    merged = merge_settings(current, update)
    assert merged.model == "new-model"
    assert merged.workspacePath == "/new-path"
    assert merged.language == "zh"


def test_merge_settings_none_fields_preserve_current() -> None:
    current = AppSettings(model="preserved", workspacePath="/preserved", language="zh")
    update = UpdateSettingsRequest()
    merged = merge_settings(current, update)
    assert merged.model == "preserved"
    assert merged.workspacePath == "/preserved"
    assert merged.language == "zh"


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
    assert body["language"] == "zh"


def test_get_settings_returns_saved_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    save_settings(AppSettings(model="openai:gpt-4o", workspacePath="/data", language="zh"))

    client = TestClient(create_app())
    response = client.get("/api/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "openai:gpt-4o"
    assert body["workspacePath"] == "/data"
    assert body["language"] == "zh"


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
        json={
            "model": "anthropic:claude-sonnet-4-6",
            "workspacePath": "/home/ws",
            "language": "zh",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "anthropic:claude-sonnet-4-6"
    assert body["workspacePath"] == "/home/ws"
    assert body["language"] == "zh"

    # Verify persisted to disk.
    loaded = load_settings()
    assert loaded.model == "anthropic:claude-sonnet-4-6"
    assert loaded.workspacePath == "/home/ws"
    assert loaded.language == "zh"


def test_put_settings_partial_update_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    # Pre-save settings with a model value.
    save_settings(AppSettings(model="openai:gpt-4o", workspacePath="/old-path", language="zh"))

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
    assert body["language"] == "zh"


def test_put_settings_partial_language_update_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    save_settings(AppSettings(model="openai:gpt-4o", workspacePath="/old-path", language="en"))

    client = TestClient(create_app())
    response = client.put(
        "/api/settings",
        json={"language": "zh"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "openai:gpt-4o"
    assert body["workspacePath"] == "/old-path"
    assert body["language"] == "zh"


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


def test_put_settings_rejects_invalid_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    client = TestClient(create_app())
    response = client.put(
        "/api/settings",
        json={"language": "fr"},
    )
    assert response.status_code == 422


def test_put_settings_empty_body_returns_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty JSON body has both fields as None — merge preserves current values."""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    save_settings(AppSettings(model="saved-model", workspacePath="/saved", language="zh"))

    client = TestClient(create_app())
    response = client.put("/api/settings", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "saved-model"
    assert body["workspacePath"] == "/saved"
    assert body["language"] == "zh"


# ---------------------------------------------------------------------------
# Provider / model schema
# ---------------------------------------------------------------------------


def _sample_provider() -> Provider:
    return Provider(
        id="deepseek",
        name="DeepSeek",
        format="openai",
        baseUrl="https://api.deepseek.com/v1",
        apiKey="sk-test",
        enabled=True,
        models=[
            ModelEntry(id="deepseek-chat", name="DeepSeek Chat"),
            ModelEntry(id="deepseek-reasoner"),
        ],
    )


def test_provider_defaults() -> None:
    p = Provider(id="p1")
    assert p.name == ""
    assert p.format == "openai"
    assert p.baseUrl == ""
    assert p.apiKey == ""
    assert p.enabled is True
    assert p.models == []


def test_provider_rejects_invalid_format() -> None:
    with pytest.raises(ValidationError):
        Provider(id="p1", format="gemini")  # type: ignore[arg-type]


def test_provider_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Provider(id="p1", bogus=True)  # type: ignore[call-arg]


def test_app_settings_with_providers_round_trips() -> None:
    s = AppSettings(
        model="",
        workspacePath="/ws",
        language="en",
        providers=[_sample_provider()],
        featureModels=FeatureModels(
            ingest=ModelRef(providerId="deepseek", modelId="deepseek-chat"),
            query=ModelRef(providerId="deepseek", modelId="deepseek-reasoner"),
        ),
    )
    dumped = s.model_dump(mode="json")
    assert AppSettings.model_validate(dumped) == s
    assert dumped["providers"][0]["apiKey"] == "sk-test"
    assert dumped["featureModels"]["ingest"] == {
        "providerId": "deepseek",
        "modelId": "deepseek-chat",
    }
    assert dumped["featureModels"]["translate"] is None


def test_load_legacy_two_field_file_gets_empty_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-provider settings.json must still load with provider defaults."""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    settings_file.write_text(
        json.dumps({"model": "openai:gpt-4o", "workspacePath": "/ws"}),
        encoding="utf-8",
    )

    result = load_settings()
    assert result.model == "openai:gpt-4o"
    assert result.language == "zh"
    assert result.providers == []
    assert result.featureModels == FeatureModels()


def test_save_load_round_trips_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    original = AppSettings(
        providers=[_sample_provider()],
        featureModels=FeatureModels(
            translate=ModelRef(providerId="deepseek", modelId="deepseek-chat")
        ),
    )
    save_settings(original)
    assert load_settings() == original


# ---------------------------------------------------------------------------
# merge_settings — providers / featureModels
# ---------------------------------------------------------------------------


def test_merge_replaces_providers_wholesale() -> None:
    current = AppSettings(providers=[_sample_provider()])
    update = UpdateSettingsRequest(providers=[Provider(id="other", format="anthropic")])
    merged = merge_settings(current, update)
    assert [p.id for p in merged.providers] == ["other"]
    assert merged.providers[0].format == "anthropic"


def test_merge_none_providers_preserves_current() -> None:
    current = AppSettings(providers=[_sample_provider()])
    merged = merge_settings(current, UpdateSettingsRequest(language="en"))
    assert [p.id for p in merged.providers] == ["deepseek"]
    assert merged.language == "en"


def test_merge_replaces_feature_models() -> None:
    current = AppSettings(
        featureModels=FeatureModels(ingest=ModelRef(providerId="a", modelId="m"))
    )
    update = UpdateSettingsRequest(
        featureModels=FeatureModels(query=ModelRef(providerId="b", modelId="n"))
    )
    merged = merge_settings(current, update)
    assert merged.featureModels.ingest is None
    assert merged.featureModels.query == ModelRef(providerId="b", modelId="n")


# ---------------------------------------------------------------------------
# resolve_feature_model
# ---------------------------------------------------------------------------


def test_resolve_feature_model_happy_path() -> None:
    settings = AppSettings(
        providers=[_sample_provider()],
        featureModels=FeatureModels(
            ingest=ModelRef(providerId="deepseek", modelId="deepseek-chat")
        ),
    )
    resolved = resolve_feature_model(settings, "ingest")
    assert resolved is not None
    provider, model = resolved
    assert provider.id == "deepseek"
    assert model.id == "deepseek-chat"


def test_resolve_feature_model_unassigned_returns_none() -> None:
    settings = AppSettings(providers=[_sample_provider()])
    assert resolve_feature_model(settings, "query") is None


def test_resolve_feature_model_missing_provider_returns_none() -> None:
    settings = AppSettings(
        providers=[_sample_provider()],
        featureModels=FeatureModels(
            ingest=ModelRef(providerId="ghost", modelId="deepseek-chat")
        ),
    )
    assert resolve_feature_model(settings, "ingest") is None


def test_resolve_feature_model_disabled_provider_returns_none() -> None:
    provider = _sample_provider()
    provider.enabled = False
    settings = AppSettings(
        providers=[provider],
        featureModels=FeatureModels(
            ingest=ModelRef(providerId="deepseek", modelId="deepseek-chat")
        ),
    )
    assert resolve_feature_model(settings, "ingest") is None


def test_resolve_feature_model_missing_model_returns_none() -> None:
    settings = AppSettings(
        providers=[_sample_provider()],
        featureModels=FeatureModels(
            ingest=ModelRef(providerId="deepseek", modelId="vanished")
        ),
    )
    assert resolve_feature_model(settings, "ingest") is None


# ---------------------------------------------------------------------------
# resolve_chat_model (model string + credentials)
# ---------------------------------------------------------------------------


def test_resolve_chat_model_override_wins_without_credentials() -> None:
    settings = AppSettings(
        providers=[_sample_provider()],
        featureModels=FeatureModels(
            ingest=ModelRef(providerId="deepseek", modelId="deepseek-chat")
        ),
    )
    resolved = resolve_chat_model(settings, "ingest", override="openai:gpt-4o")
    assert resolved is not None
    assert resolved.model == "openai:gpt-4o"
    assert resolved.apiKey == ""
    assert resolved.baseUrl == ""


def test_resolve_chat_model_from_openai_provider() -> None:
    settings = AppSettings(
        providers=[_sample_provider()],
        featureModels=FeatureModels(
            ingest=ModelRef(providerId="deepseek", modelId="deepseek-chat")
        ),
    )
    resolved = resolve_chat_model(settings, "ingest")
    assert resolved is not None
    assert resolved.model == "openai:deepseek-chat"
    assert resolved.apiKey == "sk-test"
    assert resolved.baseUrl == "https://api.deepseek.com/v1"


def test_resolve_chat_model_anthropic_prefix() -> None:
    provider = Provider(
        id="cch",
        format="anthropic",
        baseUrl="https://cch.x.de/v1",
        apiKey="k",
        models=[ModelEntry(id="claude-x")],
    )
    settings = AppSettings(
        providers=[provider],
        featureModels=FeatureModels(
            query=ModelRef(providerId="cch", modelId="claude-x")
        ),
    )
    resolved = resolve_chat_model(settings, "query")
    assert resolved is not None
    assert resolved.model == "anthropic:claude-x"
    assert resolved.baseUrl == "https://cch.x.de/v1"


def test_resolve_chat_model_legacy_model_string() -> None:
    settings = AppSettings(model="openai:gpt-4o")
    resolved = resolve_chat_model(settings, "ingest")
    assert resolved is not None
    assert resolved.model == "openai:gpt-4o"
    assert resolved.apiKey == ""


def test_resolve_chat_model_nothing_configured_returns_none() -> None:
    assert resolve_chat_model(AppSettings(), "translate") is None


# ---------------------------------------------------------------------------
# HTTP round-trip for providers + featureModels
# ---------------------------------------------------------------------------


def test_put_get_settings_round_trips_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    client = TestClient(create_app())
    payload = {
        "providers": [
            {
                "id": "deepseek",
                "name": "DeepSeek",
                "format": "openai",
                "baseUrl": "https://api.deepseek.com/v1",
                "apiKey": "sk-test",
                "enabled": True,
                "models": [{"id": "deepseek-chat", "name": "DeepSeek Chat"}],
            }
        ],
        "featureModels": {
            "ingest": {"providerId": "deepseek", "modelId": "deepseek-chat"},
            "query": None,
            "translate": None,
        },
    }
    put = client.put("/api/settings", json=payload)
    assert put.status_code == 200

    body = client.get("/api/settings").json()
    assert body["providers"][0]["id"] == "deepseek"
    assert body["providers"][0]["apiKey"] == "sk-test"
    assert body["featureModels"]["ingest"]["modelId"] == "deepseek-chat"


def test_put_settings_rejects_invalid_provider_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", tmp_path)

    client = TestClient(create_app())
    response = client.put(
        "/api/settings",
        json={"providers": [{"id": "p1", "format": "gemini"}]},
    )
    assert response.status_code == 422
