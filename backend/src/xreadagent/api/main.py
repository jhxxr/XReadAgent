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

``POST /api/ingest`` (wiki_router) follows the same job contract: it returns
``{jobId}`` immediately and streams :mod:`xreadagent.api.ingest_jobs` events
over the same ``/ws/jobs/{job_id}`` channel.

The :class:`TranslationService` instance lives on ``app.state.translation``
so tests can inject a stub via ``create_app(translation_service=...)``.
"""

from __future__ import annotations

import importlib.metadata
import os
import re
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.websockets import WebSocketState

from xreadagent.api.ingest_jobs import IngestJobService
from xreadagent.api.settings import (
    AppSettings,
    UpdateSettingsRequest,
    load_settings,
    merge_settings,
    save_settings,
)
from xreadagent.api.wiki_router import wiki_router
from xreadagent.translation.manifest import TranslationsIndex, TranslationsManifest
from xreadagent.translation.service import TranslationRequest, TranslationService
from xreadagent.wiki.workspace import Workspace

# Subdirectories under a workspace that are safe to serve over HTTP. We keep
# this strict so we never expose ``state/`` (conversation log, sources.json),
# ``wiki/`` (markdown the LLM owns), or any hidden top-level file.
_FILE_ALLOWLIST: frozenset[str] = frozenset({"translations", "raw", "extracts"})
_PDF_SUFFIX = ".pdf"

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
    ingest_service: IngestJobService | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``translation_service`` pins one service instance for the lifetime of the
    app (used by tests). ``translation_service_factory`` lets the production
    flow lazily build per-workspace services on first ``POST /api/translate``
    — kept for symmetry; tests don't use it. ``ingest_service`` pins the
    ingest job service (tests inject a stub); production uses the default
    :class:`IngestJobService`, which is workspace-agnostic.
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
    app.state.translation_services_by_workspace = {}
    app.state.translation_services_by_job = {}

    # Ingest jobs share the same /ws/jobs/{job_id} channel as translations;
    # the by-job map lets the WS handler resolve which service owns a job.
    app.state.ingest_service = (
        ingest_service if ingest_service is not None else IngestJobService()
    )
    app.state.ingest_services_by_job = {}

    # Include the wiki + ingest/query router.
    app.include_router(wiki_router, prefix="/api")

    @app.get("/api/settings", response_model=AppSettings)
    async def get_settings() -> AppSettings:
        return load_settings()

    @app.put("/api/settings", response_model=AppSettings)
    async def put_settings(req: UpdateSettingsRequest) -> AppSettings:
        current = load_settings()
        updated = merge_settings(current, req)
        save_settings(updated)
        return updated

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
            app.state.translation_services_by_job[job_id] = service
        except FileNotFoundError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return TranslateResponse(jobId=job_id)

    @app.get("/api/translations/manifest", response_model=TranslationsManifest)
    async def translations_manifest(
        workspacePath: str = Query(..., description="Absolute path to a workspace directory."),
    ) -> TranslationsManifest:
        """Return the parsed ``translations/manifest.json`` for ``workspacePath``.

        404 (not 200 with empty entries) when the manifest file is missing —
        the frontend interprets 404 as "no translations yet" (see
        ``frontend/src/lib/api.ts:94-101``). Workspace-path errors (not a
        directory, etc.) surface as 400.
        """
        workspace = _open_workspace(workspacePath)
        manifest_path = workspace.translations_manifest_path
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail="manifest not found")
        index = TranslationsIndex.load(workspace)
        return index.manifest

    @app.get("/api/workspaces/file")
    async def workspaces_file(
        workspacePath: str = Query(..., description="Absolute path to a workspace directory."),
        path: str = Query(..., description="Workspace-relative POSIX path of the file."),
    ) -> FileResponse:
        """Stream a file from inside a workspace.

        Only files under ``translations/``, ``raw/``, ``extracts/`` are served
        — ``state/`` and ``wiki/`` are off-limits so the agent's audit log
        and synthesized markdown never leak over HTTP. Path traversal
        (``../foo``, absolute paths) is rejected with 400.
        """
        workspace = _open_workspace(workspacePath)
        target = _resolve_workspace_file(workspace, path)
        media_type = "application/pdf" if target.suffix.lower() == _PDF_SUFFIX else (
            "application/octet-stream"
        )
        return FileResponse(target, media_type=media_type, filename=target.name)

    @app.websocket("/ws/jobs/{job_id}")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        service = _resolve_job_event_source(app, job_id)
        if service is None:
            await websocket.close(code=1008, reason="no event source for this job")
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

    # Mount the MCP (Model Context Protocol) server under /mcp.
    # The MCP server exposes XReadAgent capabilities as tools and resources
    # for external AI tools (Claude Desktop, Cursor, etc.) via Streamable HTTP.
    try:
        from xreadagent.mcp import create_mcp_app

        mcp_app = create_mcp_app()
        app.mount("/mcp", mcp_app.streamable_http_app())
    except ImportError:
        # mcp SDK not installed — MCP endpoints are not available.
        pass

    _mount_frontend(app)

    return app


def _frontend_dir() -> Path | None:
    """Locate the built frontend SPA directory, or ``None`` if not configured.

    Production: the Electron wrapper sets ``XREAD_FRONTEND_DIR`` to the bundled
    ``resources/frontend`` directory. When the variable is unset (e.g. pytest,
    or ``python -m xreadagent.api`` standalone in dev where Vite serves the UI),
    we return ``None`` and the sidecar runs API-only — preserving prior behavior.
    """
    env_dir = os.environ.get("XREAD_FRONTEND_DIR", "").strip()
    if not env_dir:
        return None
    candidate = Path(env_dir)
    if (candidate / "index.html").is_file():
        return candidate
    return None


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built frontend SPA when ``XREAD_FRONTEND_DIR`` points at one.

    Mounts hashed static assets under ``/assets`` and adds a catch-all that
    returns ``index.html`` for any non-API route so client-side (browser-history)
    routing works on first load and on reload of deep links. Control-plane
    prefixes (``/api``, ``/ws``, ``/mcp``, ``/healthz``) keep their JSON 404s.
    """
    dist = _frontend_dir()
    if dist is None:
        return
    index_html = dist / "index.html"

    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    _RESERVED_PREFIXES = ("api/", "ws/", "mcp/", "healthz")

    @app.get("/", include_in_schema=False)
    async def _spa_root() -> FileResponse:
        return FileResponse(index_html)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str) -> FileResponse:
        # API / websocket / MCP / health paths must surface their own JSON
        # 404 rather than being swallowed into the SPA HTML.
        if full_path == "mcp" or full_path.startswith(_RESERVED_PREFIXES):
            raise HTTPException(status_code=404, detail="Not Found")
        # Serve a real static file from dist when it exists (e.g. favicon),
        # with strict containment so "../" can't escape the dist root.
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Not Found") from exc
        if candidate.is_file():
            return FileResponse(candidate)
        # Otherwise it's a client-side route → serve the SPA shell.
        return FileResponse(index_html)


def _open_workspace(workspace_path: str) -> Workspace:
    """Resolve ``workspace_path`` into a :class:`Workspace` or raise HTTP 400.

    The directory must already exist — we do not auto-create workspaces from
    HTTP requests, because the file endpoints are read-only and the
    translations endpoint should fail loudly when pointed at a non-workspace
    rather than silently materialize an empty manifest.
    """
    cleaned = (workspace_path or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="workspacePath is required")
    try:
        candidate = Path(cleaned)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid workspacePath: {exc}") from exc
    if not candidate.exists() or not candidate.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"workspacePath is not an existing directory: {cleaned}",
        )
    return Workspace.at(candidate)


def _resolve_workspace_file(workspace: Workspace, relative: str) -> Path:
    """Resolve ``relative`` against ``workspace`` with strict containment + allowlist.

    Errors:
      - 400 if ``relative`` is empty / absolute / escapes the workspace.
      - 403 if the first path segment is not in ``_FILE_ALLOWLIST``.
      - 404 if the file does not exist (or is not a regular file).
    """
    raw = (relative or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="path is required")
    candidate = Path(raw)
    if candidate.is_absolute() or raw.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="path must be workspace-relative")

    root = workspace.root.resolve()
    resolved = (root / candidate).resolve()
    try:
        rel = resolved.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes workspace") from exc

    parts = rel.parts
    if not parts:
        raise HTTPException(status_code=400, detail="path resolves to workspace root")
    if parts[0] not in _FILE_ALLOWLIST:
        raise HTTPException(
            status_code=403,
            detail=(
                f"reading from {parts[0]!r} is not permitted; "
                f"allowed roots: {sorted(_FILE_ALLOWLIST)}"
            ),
        )

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return resolved


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
    cache: dict[str, TranslationService] = app.state.translation_services_by_workspace
    cache_key = str(workspace.root.resolve())
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    service = factory(workspace)
    cache[cache_key] = service
    return service


def _resolve_translation_service_for_job(app: FastAPI, job_id: str) -> TranslationService | None:
    pinned: TranslationService | None = app.state.translation_service
    if pinned is not None:
        return pinned
    by_job: dict[str, TranslationService] = app.state.translation_services_by_job
    return by_job.get(job_id)


class _JobEventSource(Protocol):
    """Anything ``/ws/jobs/{job_id}`` can stream from.

    Both :class:`TranslationService` and :class:`IngestJobService` satisfy
    this: an async generator of Pydantic events that ends after the terminal
    ``finish`` / ``error`` event and raises ``KeyError`` for unknown jobs.
    """

    def event_stream(self, job_id: str) -> AsyncIterator[Any]: ...


def _resolve_job_event_source(app: FastAPI, job_id: str) -> _JobEventSource | None:
    """Resolve which service owns ``job_id`` for the shared WS jobs channel.

    Ingest jobs are matched exactly via the by-job map populated by
    ``POST /api/ingest``; everything else falls back to the translation
    resolution (pinned service first, then the translate by-job map) so the
    pre-existing translate contract is unchanged.
    """
    ingest_by_job: dict[str, IngestJobService] = app.state.ingest_services_by_job
    ingest_service = ingest_by_job.get(job_id)
    if ingest_service is not None:
        return ingest_service
    return _resolve_translation_service_for_job(app, job_id)


app = create_app()
