# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests gated behind explicit pytest markers.

Tests in this package exercise real heavy dependencies (BabelDOC engine,
MinerU CLI, real LLM providers) and are **skipped by default**. Opt in
per-marker, e.g.::

    pytest -m babeldoc backend/tests/integration/

Each marker is registered in :file:`pyproject.toml` under
``[tool.pytest.ini_options].markers``.
"""
