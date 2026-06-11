# SPDX-License-Identifier: AGPL-3.0-or-later
"""``python -m xreadagent.api`` entry point.

Honors the Electron-sidecar contract:

1. Prints ``SIDECAR_BOOT`` (flushed) to stdout immediately — with only stdlib
   modules loaded — so the Electron loader can tell "Python is alive, the
   import chain is crawling" (cold cache / antivirus scanning on first run)
   apart from a genuinely hung process.
2. Prints ``SIDECAR_READY port=<N>`` (flushed) as soon as uvicorn finishes
   startup, then runs the app loop until terminated.

``--port 0`` lets the OS pick a free port; the actual bound port is reported
in the ready line. The heavy imports (uvicorn/FastAPI/xreadagent) live inside
``_build_server`` so the boot marker is never delayed by them.
"""

from __future__ import annotations

import argparse
import socket
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uvicorn

#: Liveness marker printed before the heavy import chain (see module docstring).
BOOT_MARKER = "SIDECAR_BOOT"


def _pick_port(requested: int) -> int:
    if requested != 0:
        return requested
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_server(port: int) -> uvicorn.Server:
    # Heavy imports are deferred to here: on a cold first launch they can take
    # minutes (AV scanning), and the BOOT_MARKER must already be on stdout.
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    import uvicorn
    from fastapi import FastAPI

    from xreadagent.api.main import create_app
    from xreadagent.translation.service import TranslationService

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        sys.stdout.write(f"SIDECAR_READY port={port}\n")
        sys.stdout.flush()
        yield

    app = create_app(
        lifespan=lifespan,
        translation_service_factory=lambda workspace: TranslationService(workspace),
    )
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    return uvicorn.Server(config)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.write(f"{BOOT_MARKER}\n")
    sys.stdout.flush()

    parser = argparse.ArgumentParser(prog="xreadagent.api")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="TCP port to bind on 127.0.0.1; 0 means auto-pick.",
    )
    args = parser.parse_args(argv)

    port = _pick_port(args.port)
    server = _build_server(port)
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
