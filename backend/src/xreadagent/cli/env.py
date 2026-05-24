# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tiny `.env.local` parser — no `python-dotenv` dependency.

Lookup order matches conventional behavior:

1. Variables already in ``os.environ`` win — the CLI never overwrites them.
2. If a ``.env.local`` file is present in the workspace root or current
   working directory (in that priority order), parse it and inject any
   missing keys.

The parser is deliberately minimal — it understands ``KEY=VALUE`` lines,
strips surrounding whitespace, ignores blank lines and comment lines that
start with ``#``, and supports single- or double-quoted values. It does
NOT do shell-style expansion (``$VAR`` interpolation) on purpose: this is
configuration, not a shell.
"""

from __future__ import annotations

import os
from pathlib import Path

_PROVIDER_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "google": "GOOGLE_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "ollama": "",  # Ollama needs no key for the local default.
}


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse one `.env`-style file. Missing file ⇒ empty dict."""
    if not path.exists() or not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[key] = value
    return result


def load_env_files(*candidates: Path) -> None:
    """Inject values from candidate ``.env.local`` files into ``os.environ``.

    Earlier candidates win over later ones. Already-set env vars are never
    overwritten — explicit shell exports always take priority.
    """
    seen: set[str] = set()
    for candidate in candidates:
        for key, value in parse_env_file(candidate).items():
            if key in seen:
                continue
            seen.add(key)
            os.environ.setdefault(key, value)


def required_env_var_for_model(model: str) -> str | None:
    """Return the env var that must be set for ``model`` (a ``provider:name`` string).

    Returns ``None`` for providers (e.g. Ollama) that don't need an API key.
    Raises ``ValueError`` if the provider prefix is unrecognized.
    """
    if ":" not in model:
        raise ValueError(
            f"model must be in the form 'provider:name' (got {model!r}); "
            "examples: 'openai:gpt-4o', 'anthropic:claude-sonnet-4-6', "
            "'google_genai:gemini-2.5-pro', 'ollama:llama3.1:70b'"
        )
    provider = model.split(":", 1)[0].strip().lower()
    if provider not in _PROVIDER_KEY_ENV:
        raise ValueError(
            f"unknown LLM provider {provider!r}; supported: "
            f"{sorted(_PROVIDER_KEY_ENV)}"
        )
    env_name = _PROVIDER_KEY_ENV[provider]
    return env_name or None


def ensure_provider_credentials(model: str) -> str | None:
    """Validate that the env var the model needs is present.

    Returns the env-var name that was checked (or ``None`` for providers
    that don't need one). Raises ``RuntimeError`` if the required var is
    missing — the error message names the env var so the user can fix it.
    """
    env_var = required_env_var_for_model(model)
    if env_var is None:
        return None
    if not os.environ.get(env_var, "").strip():
        raise RuntimeError(
            f"missing env var {env_var!r} required for model {model!r}; "
            f"set it in your shell or add it to .env.local"
        )
    return env_var


__all__ = [
    "ensure_provider_credentials",
    "load_env_files",
    "parse_env_file",
    "required_env_var_for_model",
]
