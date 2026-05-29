# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared helpers for the MCP module.

Internal utilities used by both tools and resources. Not part of the public
MCP surface.
"""

from __future__ import annotations

import os
from pathlib import Path

from xreadagent.wiki.workspace import Workspace


def resolve_workspace(workspace_path: str | None = None) -> Workspace:
    """Resolve workspace from argument, env var, or raise.

    Resolution order:
    1. Explicit ``workspace_path`` argument.
    2. ``XREAD_AGENT_WORKSPACE`` environment variable.
    3. Raise ``ValueError`` if neither is available.
    """
    path = (workspace_path or "").strip() or os.environ.get(
        "XREAD_AGENT_WORKSPACE", ""
    )
    if not path:
        raise ValueError(
            "workspace_path is required (or set XREAD_AGENT_WORKSPACE env var)"
        )
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_dir():
        raise ValueError(f"workspace path is not an existing directory: {path}")
    workspace = Workspace.at(candidate)
    if not workspace.is_initialized():
        raise ValueError(f"not an initialized XReadAgent workspace: {path}")
    return workspace


def resolve_model(model_override: str | None = None) -> str:
    """Return model from arg, env, settings, or raise.

    Resolution order:
    1. Explicit ``model_override`` argument.
    2. ``XREAD_AGENT_MODEL`` environment variable.
    3. Persisted settings (``~/.xreadagent/settings.json``).
    4. Raise ``ValueError`` if none is available.
    """
    if model_override and model_override.strip():
        return model_override.strip()
    env_model = os.environ.get("XREAD_AGENT_MODEL", "").strip()
    if env_model:
        return env_model
    # Check persisted settings — best-effort; missing/corrupt file is not fatal.
    try:
        from xreadagent.api.settings import load_settings

        settings_model = load_settings().model.strip()
        if settings_model:
            return settings_model
    except (OSError, ValueError):
        pass
    raise ValueError(
        "No model specified. Pass `model` argument, set XREAD_AGENT_MODEL "
        "environment variable, or configure it in settings."
    )


__all__ = ["resolve_workspace", "resolve_model"]
