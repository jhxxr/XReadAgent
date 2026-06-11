# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single source of truth for the installed BabelDOC engine version.

The version pin lives in ``pyproject.toml`` (``babeldoc==X.Y.Z``). Everything
else — adapter configs, worker configs, manifest entries — derives the version
from the installed package metadata so a pin bump never requires touching
translation code. Reads only dist-info metadata; it does NOT import the heavy
``babeldoc`` package (which stays a subprocess-only lazy import).
"""

from __future__ import annotations

from functools import cache
from importlib import metadata

_FALLBACK_VERSION = "unknown"


@cache
def installed_babeldoc_version() -> str:
    """Return the installed ``babeldoc`` distribution version.

    ``babeldoc`` is a hard dependency, so the fallback only triggers in
    exotic environments (e.g. a vendored source tree without dist-info).
    """
    try:
        return metadata.version("babeldoc")
    except metadata.PackageNotFoundError:
        return _FALLBACK_VERSION
