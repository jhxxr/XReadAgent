# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI sidecar: ``/healthz`` + translation endpoints + ``/ws/events``.

Bound to ``127.0.0.1`` only. CORS is wide-open for local dev origins
(``http://localhost:*`` / ``http://127.0.0.1:*``); production builds will
tighten this when the Electron wrapper lands in Phase 3.

Translation surface (Phase 2A):

- ``POST /api/translate``      → returns ``{job_id}`` immediately; the
  TranslationService kicks off the BabelDOC worker.
- ``WS /ws/jobs/{job_id}``     → streams :class:`TranslationEvent` JSON
  objects; closes on ``finish`` / ``error``.

The :class:`TranslationService` instance lives on ``app.state.translation``
so tests can inject a stub via ``create_app(translation_service=...)``.
"""

from __future__ import annotations

import importlib.metadata
import re
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from starlette.websockets import WebSocketState

from xreadagent.translation.service import TranslationRequest, TranslationService
from xreadagent.wiki.workspace import Workspace

_LOCAL_ORIGIN_RE = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def _version() -> str:
    try:
        return importlib.metadata.version("xreadagent")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+unknown"


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class TranslateRequest(_Strict):
    """Body of ``POST /api/translate`` — camelCase per the wire convention."""

    workspacePath: str
    sourcePath: str
    model: str
    targetLang: str = "zh"
    sourceLang: str = "en"
    mono: bool = True
    dual: bool = True
    headers: dict[str, str] = Field(default_factory=dict)
    maxTokens: int | None = None
    apiKey: str | None = None
    baseUrl: str | None = None


class TranslateResponse(_Strict):
    jobId: str


def create_app(
    *,
    lifespan: Lifespan | None = None,
    translation_service: TranslationService | None = None,
    translation_service_factory: Callable[[Workspace], TranslationService] | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``translation_service`` pins one service instance for the lifetime of the
    app (used by tests). ``translation_service_factory`` lets the production
    flow lazily build per-workspace services on first ``POST /api/translate``
    — kept for symmetry; tests don't use it.
    """
    app = FastAPI(title="XReadAgent sidecar", version=_version(), lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_LOCAL_ORIGIN_RE.pattern,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Wire the translation service onto app.state so handlers can pull it
    # without import cycles.
    app.state.translation_service = translation_service
    app.state.translation_service_factory = translation_service_factory

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "version": _version()}

    @app.post("/api/translate", response_model=TranslateResponse)
    async def translate(req: TranslateRequest) -> TranslateResponse:
        service = _resolve_translation_service(app, Path(req.workspacePath))
        try:
            translation_req = TranslationRequest(
                source_path=Path(req.sourcePath),
                model=req.model,
                target_lang=req.targetLang,
                source_lang=req.sourceLang,
                mono=req.mono,
                dual=req.dual,
                api_key=req.apiKey,
                base_url=req.baseUrl,
                default_headers=dict(req.headers),
                max_tokens=req.maxTokens,
            )
            job_id = service.start_translation(translation_req)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return TranslateResponse(jobId=job_id)

    @app.websocket("/ws/jobs/{job_id}")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        service: TranslationService | None = app.state.translation_service
        if service is None:
            await websocket.close(code=1008, reason="translation service not configured")
            return
        await websocket.accept()
        try:
            async for event in service.event_stream(job_id):
                await websocket.send_json(event.model_dump(mode="json"))
        except KeyError:
            await websocket.send_json(
                {"type": "error", "message": f"unknown job_id: {job_id}"}
            )
        except WebSocketDisconnect:
            return
        finally:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                try:
                    await websocket.close()
                except RuntimeError:
                    pass

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
                try:
                    await websocket.close()
                except RuntimeError:
                    pass

    return app


def _resolve_translation_service(app: FastAPI, workspace_path: Path) -> TranslationService:
    """Resolve the active :class:`TranslationService` for ``workspace_path``.

    Tests pin a service at construction time; production code can pass a
    factory that constructs one per workspace. Either way we raise a 422 if
    no service is wired up — better than a confusing AttributeError.
    """
    pinned: TranslationService | None = app.state.translation_service
    if pinned is not None:
        return pinned
    factory: Callable[[Workspace], TranslationService] | None = (
        app.state.translation_service_factory
    )
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail="translation service not configured on this sidecar instance",
        )
    workspace = Workspace.at(workspace_path)
    service = factory(workspace)
    app.state.translation_service = service
    return service


app = create_app()
