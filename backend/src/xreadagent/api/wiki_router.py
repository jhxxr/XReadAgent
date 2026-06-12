# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wiki read API + ingest/query HTTP endpoints.

Included in the main FastAPI app via ``app.include_router(wiki_router)``.
All routes are prefixed with ``/api/wiki`` (papers, concepts, queries,
index, overview) or ``/api`` (ingest, query).

Read-only wiki endpoints parse frontmatter + content from the markdown
pages on disk. Ingest starts a background job (progress over
``/ws/jobs/{job_id}``, see ``api/ingest_jobs.py``); query delegates to the
query orchestrator synchronously.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from xreadagent.api.ingest_jobs import IngestJobRequest, IngestJobService
from xreadagent.api.settings import (
    FeatureName,
    ResolvedChatModel,
    load_settings,
    resolve_chat_model,
)
from xreadagent.wiki.frontmatter_utils import (
    list_concepts,
    list_papers,
    list_queries,
    read_page_content,
    read_page_frontmatter,
)
from xreadagent.wiki.sources import SourcesIndex
from xreadagent.wiki.workspace import Workspace

# ---------------------------------------------------------------------------
# Pydantic wire models (camelCase)
# ---------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class PaperSummaryResponse(_Strict):
    slug: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    ingestedAt: str = ""
    sourcePath: str | None = None
    sourceKind: str = ""


class ConceptSummaryResponse(_Strict):
    slug: str
    title: str
    aliases: list[str] = Field(default_factory=list)
    paperCount: int = 0


class QuerySummaryResponse(_Strict):
    id: str
    question: str
    topic: str
    archivedAt: str = ""


class WikiPageResponse(_Strict):
    slug: str
    content: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    sourcePath: str | None = None
    sourceKind: str = ""


class IngestRequest(_Strict):
    workspacePath: str
    filePath: str
    title: str | None = None
    model: str | None = None


class IngestJobResponse(_Strict):
    """Body of the ``POST /api/ingest`` reply — camelCase per wire convention."""

    jobId: str


class QueryRequest(_Strict):
    workspacePath: str
    question: str
    topic: str | None = None
    model: str | None = None


class QueryResultResponse(_Strict):
    question: str
    answer: str
    confidence: str = ""
    sourcesCited: list[str] = Field(default_factory=list)
    queryPagePath: str = ""
    filesTouched: list[str] = Field(default_factory=list)
    durationS: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_workspace(workspace_path: str) -> Workspace:
    """Resolve *workspace_path* into a :class:`Workspace` or raise HTTP 400."""
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


def _resolve_chat(
    feature: FeatureName, model_override: str | None
) -> ResolvedChatModel:
    """Resolve a feature's chat target (model + credentials) from settings.

    Precedence is request-body override → feature-assigned provider → legacy
    ``model`` string (see :func:`resolve_chat_model`). There is no env-var
    fallback on the API path — credentials come from the UI provider config.
    """
    settings = load_settings()
    resolved = resolve_chat_model(settings, feature, override=model_override)
    if resolved is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No model configured for {feature}. Pass `model` in the request "
                "body or configure a provider for it in Settings."
            ),
        )
    return resolved


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

wiki_router = APIRouter()


# -- Papers ----------------------------------------------------------------


@wiki_router.get("/wiki/papers", response_model=list[PaperSummaryResponse])
async def get_papers(
    workspacePath: str = Query(..., description="Absolute path to a workspace directory."),
) -> list[PaperSummaryResponse]:
    workspace = _open_workspace(workspacePath)
    raw = list_papers(workspace)
    return [PaperSummaryResponse(**row) for row in raw]


@wiki_router.get("/wiki/papers/{slug}", response_model=WikiPageResponse)
async def get_paper(
    slug: str,
    workspacePath: str = Query(..., description="Absolute path to a workspace directory."),
) -> WikiPageResponse:
    workspace = _open_workspace(workspacePath)
    path = workspace.papers_dir / f"{slug}.md"
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"paper not found: {slug}")
    source = SourcesIndex.load(workspace).find_by_id(slug)
    return WikiPageResponse(
        slug=slug,
        content=read_page_content(path),
        frontmatter=read_page_frontmatter(path),
        sourcePath=source.sourcePath if source and source.sourcePath else None,
        sourceKind=source.kind if source else "",
    )


# -- Concepts --------------------------------------------------------------


@wiki_router.get("/wiki/concepts", response_model=list[ConceptSummaryResponse])
async def get_concepts(
    workspacePath: str = Query(..., description="Absolute path to a workspace directory."),
) -> list[ConceptSummaryResponse]:
    workspace = _open_workspace(workspacePath)
    raw = list_concepts(workspace)
    return [ConceptSummaryResponse(**row) for row in raw]


@wiki_router.get("/wiki/concepts/{slug}", response_model=WikiPageResponse)
async def get_concept(
    slug: str,
    workspacePath: str = Query(..., description="Absolute path to a workspace directory."),
) -> WikiPageResponse:
    workspace = _open_workspace(workspacePath)
    path = workspace.concepts_dir / f"{slug}.md"
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"concept not found: {slug}")
    return WikiPageResponse(
        slug=slug,
        content=read_page_content(path),
        frontmatter=read_page_frontmatter(path),
    )


# -- Queries ---------------------------------------------------------------


@wiki_router.get("/wiki/queries", response_model=list[QuerySummaryResponse])
async def get_queries(
    workspacePath: str = Query(..., description="Absolute path to a workspace directory."),
) -> list[QuerySummaryResponse]:
    workspace = _open_workspace(workspacePath)
    raw = list_queries(workspace)
    return [QuerySummaryResponse(**row) for row in raw]


@wiki_router.get(
    "/wiki/queries/{topic}/{slug}", response_model=WikiPageResponse
)
async def get_query(
    topic: str,
    slug: str,
    workspacePath: str = Query(..., description="Absolute path to a workspace directory."),
) -> WikiPageResponse:
    workspace = _open_workspace(workspacePath)
    path = workspace.queries_dir / topic / f"{slug}.md"
    if not path.exists() or not path.is_file():
        raise HTTPException(
            status_code=404, detail=f"query not found: {topic}/{slug}"
        )
    return WikiPageResponse(
        slug=f"{topic}/{slug}",
        content=read_page_content(path),
        frontmatter=read_page_frontmatter(path),
    )


# -- Index / Overview ------------------------------------------------------


@wiki_router.get("/wiki/index")
async def get_index(
    workspacePath: str = Query(..., description="Absolute path to a workspace directory."),
) -> dict[str, str]:
    workspace = _open_workspace(workspacePath)
    path = workspace.index_md_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="index.md not found")
    return {"content": read_page_content(path)}


@wiki_router.get("/wiki/overview")
async def get_overview(
    workspacePath: str = Query(..., description="Absolute path to a workspace directory."),
) -> dict[str, str]:
    workspace = _open_workspace(workspacePath)
    path = workspace.overview_md_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="overview.md not found")
    return {"content": read_page_content(path)}


# -- Ingest ---------------------------------------------------------------


@wiki_router.post("/ingest", response_model=IngestJobResponse)
async def post_ingest(req: IngestRequest, request: Request) -> IngestJobResponse:
    """Start an ingest job and return its ``jobId`` immediately.

    The ingest itself (conversion + LLM agent + wiki write-out) runs in the
    background; progress streams over ``/ws/jobs/{job_id}`` as
    ``stage_start`` / ``stage_end`` / ``finish`` / ``error`` events — same
    job contract as ``POST /api/translate``.
    """
    workspace = _open_workspace(req.workspacePath)
    raw_path = Path(req.filePath)
    if not raw_path.exists():
        raise HTTPException(status_code=422, detail=f"file not found: {req.filePath}")

    resolved = _resolve_chat("ingest", req.model)
    service: IngestJobService | None = getattr(request.app.state, "ingest_service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="ingest service not configured on this sidecar instance",
        )
    job_request = IngestJobRequest(
        workspace_path=workspace.root,
        file_path=raw_path,
        model=resolved.model,
        title=req.title,
        api_key=resolved.apiKey or None,
        base_url=resolved.baseUrl or None,
    )
    try:
        job_id = service.start_ingest(job_request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Map the job back to its service so the WS handler can resolve it —
    # same discipline as ``translation_services_by_job`` (see
    # ``.trellis/spec/backend/error-handling.md``).
    by_job: dict[str, IngestJobService] = request.app.state.ingest_services_by_job
    by_job[job_id] = service
    return IngestJobResponse(jobId=job_id)


# -- Query ----------------------------------------------------------------


@wiki_router.post("/query", response_model=QueryResultResponse)
async def post_query(req: QueryRequest) -> QueryResultResponse:
    """Answer a question using the wiki knowledge base.

    Constructs a ``QueryAgent`` with the resolved model string and delegates
    to the query orchestrator.
    """
    from xreadagent.agents.query import QueryAgent
    from xreadagent.agents.query_orchestrator import answer_query

    workspace = _open_workspace(req.workspacePath)
    resolved = _resolve_chat("query", req.model)
    agent = QueryAgent(
        workspace,
        model=resolved.model,
        api_key=resolved.apiKey or None,
        base_url=resolved.baseUrl or None,
    )
    try:
        result = await answer_query(workspace, req.question, agent=agent, topic=req.topic)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return QueryResultResponse(
        question=result.answer.question,
        answer=result.answer.answer_markdown,
        confidence=result.answer.confidence,
        sourcesCited=list(result.answer.sources_cited),
        queryPagePath=str(result.query_page_path),
        filesTouched=result.files_touched,
        durationS=result.duration_s,
    )

