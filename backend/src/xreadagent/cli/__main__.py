# SPDX-License-Identifier: AGPL-3.0-or-later
"""``python -m xreadagent.cli`` entry point.

Re-exports ``main`` from the package so ``python -m xreadagent.cli`` and the
console-script entry point in ``pyproject.toml`` share one implementation.
"""

from __future__ import annotations

from xreadagent.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
