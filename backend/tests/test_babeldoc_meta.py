# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for translation.babeldoc_meta — single-source BabelDOC version.

Guards C2 of the optimize-project task: the BabelDOC version string must be
derived from the installed distribution metadata, never hardcoded, so the
``babeldoc==X.Y.Z`` pin in ``pyproject.toml`` stays the single source.
"""

from importlib import metadata
from pathlib import Path

import pytest

from xreadagent.translation import babeldoc_meta
from xreadagent.translation import service as service_mod
from xreadagent.translation.babeldoc_adapter import AdapterConfig
from xreadagent.translation.babeldoc_meta import installed_babeldoc_version
from xreadagent.translation.worker import ChatConfig, WorkerJobConfig


def test_version_matches_installed_distribution() -> None:
    assert installed_babeldoc_version() == metadata.version("babeldoc")


def test_fallback_when_babeldoc_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_not_found(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(babeldoc_meta.metadata, "version", raise_not_found)
    # Call through __wrapped__ to bypass the functools.cache wrapper — the
    # cached value was already populated by earlier imports in this process.
    assert babeldoc_meta.installed_babeldoc_version.__wrapped__() == "unknown"


def test_adapter_config_defaults_to_installed_version(tmp_path: Path) -> None:
    config = AdapterConfig(input_path=tmp_path / "in.pdf", output_dir=tmp_path)
    assert config.babeldoc_version == installed_babeldoc_version()


def test_worker_config_defaults_to_installed_version(tmp_path: Path) -> None:
    config = WorkerJobConfig(
        adapter=AdapterConfig(input_path=tmp_path / "in.pdf", output_dir=tmp_path),
        chat=ChatConfig(model="test-model"),
        job_id="job-1",
    )
    assert config.babeldoc_version == installed_babeldoc_version()


def test_service_default_matches_installed_version() -> None:
    assert service_mod._BABELDOC_VERSION_DEFAULT == installed_babeldoc_version()
