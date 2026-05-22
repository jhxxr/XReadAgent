# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI sidecar: ``/healthz`` + ``/ws/events``.

Bound to ``127.0.0.1`` only. CORS is wide-open for local dev origins
(``http://localhost:*`` / ``http://127.0.0.1:*``); production builds will
tighten this when the Electron wrapper lands in Phase 3.
"""

from __future__ import annotations

import importlib.metadata
import re
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

_LOCAL_ORIGIN_RE = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def _version() -> str:
    try:
        return importlib.metadata.version("xreadagent")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+unknown"


def create_app(*, lifespan: Lifespan | None = None) -> FastAPI:
    app = FastAPI(title="XReadAgent sidecar", version=_version(), lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_LOCAL_ORIGIN_RE.pattern,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "version": _version()}

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"type": "hello"})
        try:
            while True:
                message = await websocket.receive_text()
                await websocket.send_text(message)
        except WebSocketDisconnect:
            return
        finally:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                # Best-effort close — ignore if already torn down.
                try:
                    await websocket.close()
                except RuntimeError:
                    pass

    return app


app = create_app()
