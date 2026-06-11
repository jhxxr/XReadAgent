# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import-graph guards: startup paths must not load the agent-framework chain.

The Electron loader gives the sidecar 30s to print ``SIDECAR_READY``; on a
cold cache (first run after install, AV scanning) the langchain/langsmith
import chain alone can eat most of that budget. These tests pin the fix from
the lazy-import refactor (PEP 562 ``__getattr__`` re-exports): importing the
package root, the FastAPI app module, or the CLI dispatcher must never pull
langchain / langgraph / deepagents / langsmith into ``sys.modules``.

Each check runs in a subprocess because the pytest process itself imports
agent modules elsewhere — ``sys.modules`` in-process is already polluted.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_FORBIDDEN_PREFIXES = ("langchain", "langgraph", "deepagents", "langsmith")

_BACKEND_SRC = Path(__file__).resolve().parents[1] / "src"

_GUARD_SNIPPET = """
import sys
{imports}
bad = sorted({{m.split(".")[0] for m in sys.modules if m.startswith({prefixes!r})}})
assert not bad, f"agent-framework modules loaded at import time: {{bad}}"
"""


def _run_import_guard(*imports: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_BACKEND_SRC) + os.pathsep + env.get("PYTHONPATH", "")
    snippet = _GUARD_SNIPPET.format(
        imports="\n".join(f"import {module}" for module in imports),
        prefixes=_FORBIDDEN_PREFIXES,
    )
    return subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_import_package_root_does_not_load_agent_frameworks() -> None:
    result = _run_import_guard("xreadagent")
    assert result.returncode == 0, result.stderr


def test_import_api_main_does_not_load_agent_frameworks() -> None:
    result = _run_import_guard("xreadagent", "xreadagent.api.main")
    assert result.returncode == 0, result.stderr


def test_import_cli_dispatcher_does_not_load_agent_frameworks() -> None:
    result = _run_import_guard("xreadagent.cli.main")
    assert result.returncode == 0, result.stderr


def test_lazy_reexports_still_resolve() -> None:
    """``from xreadagent import IngestAgent`` keeps working via PEP 562."""
    import xreadagent

    assert xreadagent.__version__
    assert xreadagent.IngestAgent.__name__ == "IngestAgent"
    assert callable(xreadagent.ingest_source)
    from xreadagent.agents import DEFAULT_AGENT_MAX_TOKENS

    assert DEFAULT_AGENT_MAX_TOKENS > 0


def test_unknown_attribute_raises_attribute_error() -> None:
    import xreadagent
    import xreadagent.agents as agents_pkg

    try:
        xreadagent.NoSuchThing
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected AttributeError for unknown attribute")

    try:
        agents_pkg.NoSuchThing
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected AttributeError for unknown attribute")
