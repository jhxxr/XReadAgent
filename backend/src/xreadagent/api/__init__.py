# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI sidecar entry points.

``create_app`` is re-exported lazily (PEP 562). ``python -m xreadagent.api``
imports this package *before* ``__main__`` runs; an eager re-export would pull
the whole FastAPI/pydantic import chain in before the entry point can print
its ``SIDECAR_BOOT`` liveness marker — on a cold cache (first run after
install, AV scanning) that chain can take minutes, and the marker exists
precisely to make that window observable to the Electron loader.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from xreadagent.api.main import create_app

__all__ = ["create_app"]


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from xreadagent.api.main import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
