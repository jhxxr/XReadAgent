# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wiki read API + ingest/query HTTP endpoints.

Included in the main FastAPI app via ``app.include_router(wiki_router)``.
All routes are prefixed with ``/api/wiki`` (papers, concepts, queries,
index, overview) or ``/api`` (ingest, query).

Read-only wiki endpoints parse frontmatter + content from the markdown
pages on disk. Ingest and query delegates to the existing agent
orchestrators.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from xreadagent.wiki.frontmatter_utils import (
    list_concepts,
    list_papers,
    list_queries,
    read_page_content,
    read_page_frontmatter,
)
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


class IngestRequest(_Strict):
    workspacePath: str
    filePath: str
    title: str | None = None
    model: str | None = None


class IngestResultResponse(_Strict):
    slug: str
    title: str
    cacheHit: bool = False
    filesTouched: list[str] = Field(default_factory=list)
    durationS: float = 0.0


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


def _resolve_model(model_override: str | None) -> str:
    """Return the model string from the request body, settings, or the environment."""
    if model_override and model_override.strip():
        return model_override.strip()
    # Check persisted settings next.
    from xreadagent.api.settings import load_settings

    settings_model: str = load_settings().model.strip()
    if settings_model:
        return settings_model
    env_model = os.environ.get("XREAD_AGENT_MODEL", "").strip()
    if env_model:
        return env_model
    raise HTTPException(
        status_code=422,
        detail=(
            "No model specified. Pass `model` in the request body, configure "
            "it in settings, or set the XREAD_AGENT_MODEL environment variable."
        ),
    )


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
    return WikiPageResponse(
        slug=slug,
        content=read_page_content(path),
        frontmatter=read_page_frontmatter(path),
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


@wiki_router.post("/ingest", response_model=IngestResultResponse)
async def post_ingest(req: IngestRequest) -> IngestResultResponse:
    """Ingest a document into the wiki.

    Constructs an ``IngestAgent`` with the resolved model string and delegates
    to the ingest orchestrator.
    """
    from xreadagent.agents.ingest import IngestAgent
    from xreadagent.agents.orchestrator import ingest_source

    workspace = _open_workspace(req.workspacePath)
    raw_path = Path(req.filePath)
    if not raw_path.exists():
        raise HTTPException(status_code=422, detail=f"file not found: {req.filePath}")

    model = _resolve_model(req.model)
    agent = IngestAgent(workspace, model=model)
    try:
        result = await ingest_source(workspace, raw_path, agent=agent, title=req.title)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return IngestResultResponse(
        slug=result.source.slug,
        title=result.source.title,
        cacheHit=result.cache_hit,
        filesTouched=result.files_touched,
        durationS=result.duration_s,
    )


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
    model = _resolve_model(req.model)
    agent = QueryAgent(workspace, model=model)
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
