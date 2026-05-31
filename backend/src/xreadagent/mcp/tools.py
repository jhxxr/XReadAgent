# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP tool definitions for XReadAgent.

Each tool delegates to the appropriate wiki primitive or agent orchestrator.
Expensive operations (ingest, translate) use ``ctx.elicit()`` for human
confirmation before proceeding.

Layering rule: tools call wiki/ primitives and agent orchestrators directly,
never the LangChain tools in agents/tools.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict

from xreadagent.mcp._helpers import resolve_model, resolve_workspace

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class ElicitConfirmation(_Strict):
    """Schema for elicit() confirmation prompts."""

    confirm: bool


def _check_elicit_accepted(elicit_result: Any) -> bool:
    """Return True if the user accepted the elicit prompt.

    Handles the union type from ``ctx.elicit()`` which returns
    ``AcceptedElicitation | DeclinedElicitation | CancelledElicitation``.
    Only ``AcceptedElicitation`` has a ``data`` attribute; the others
    indicate the user declined or cancelled.
    """
    action = getattr(elicit_result, "action", None)
    if action == "accept":
        data = getattr(elicit_result, "data", None)
        return getattr(data, "confirm", False)
    return False


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on the given FastMCP instance."""

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True))
    async def ingest_paper(
        source_path: str,
        workspace_path: str | None = None,
        title: str | None = None,
        model: str | None = None,
        ctx: Context[Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Ingest a scientific paper into the workspace wiki.

        Converts the document to markdown, runs the LLM ingest agent,
        and creates paper + concept wiki pages. Returns the paper slug
        and list of files created.

        Idempotent: re-ingesting an unchanged file is a no-op (cache hit).
        """
        workspace = resolve_workspace(workspace_path)

        # Elicit human confirmation — ingest calls an LLM and is not free.
        if ctx is not None:
            elicit_result = await ctx.elicit(
                f"About to ingest '{source_path}' into the workspace. "
                "This will call an LLM and create wiki pages. Proceed?",
                schema=ElicitConfirmation,
            )
            if not _check_elicit_accepted(elicit_result):
                return {"status": "cancelled", "reason": "user declined"}

        raw_path = Path(source_path)
        if not raw_path.exists():
            raise FileNotFoundError(f"source file not found: {source_path}")
        if not raw_path.is_file():
            raise ValueError(f"source path is not a regular file: {source_path}")

        resolved_model = resolve_model(model)

        from xreadagent.agents.ingest import IngestAgent
        from xreadagent.agents.orchestrator import ingest_source

        agent = IngestAgent(workspace, model=resolved_model)
        ingest_result = await ingest_source(workspace, raw_path, agent=agent, title=title)

        return {
            "slug": ingest_result.source.slug,
            "title": ingest_result.source.title,
            "cache_hit": ingest_result.cache_hit,
            "files_touched": ingest_result.files_touched,
            "duration_s": ingest_result.duration_s,
        }

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False))
    async def query_wiki(
        question: str,
        workspace_path: str | None = None,
        topic: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Ask a question against the workspace knowledge base.

        Returns the answer, confidence level, and sources cited.
        The answer is also archived under wiki/queries/.
        """
        workspace = resolve_workspace(workspace_path)
        resolved_model = resolve_model(model)

        from xreadagent.agents.query import QueryAgent
        from xreadagent.agents.query_orchestrator import answer_query

        agent = QueryAgent(workspace, model=resolved_model)
        result = await answer_query(workspace, question, agent=agent, topic=topic)

        return {
            "question": result.answer.question,
            "answer": result.answer.answer_markdown,
            "confidence": result.answer.confidence,
            "sources_cited": list(result.answer.sources_cited),
            "query_page_path": str(result.query_page_path),
            "files_touched": result.files_touched,
            "duration_s": result.duration_s,
        }

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False))
    async def translate_paper(
        source_path: str,
        workspace_path: str | None = None,
        model: str | None = None,
        target_lang: str = "zh",
        source_lang: str = "en",
        ctx: Context[Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Translate a PDF document while preserving layout.

        Starts a BabelDOC translation job. Returns a job_id for
        tracking progress via check_translation_status.
        """
        workspace = resolve_workspace(workspace_path)

        # Elicit human confirmation — translation is expensive.
        if ctx is not None:
            elicit_result = await ctx.elicit(
                f"About to translate '{source_path}' to {target_lang}. "
                "This will call an LLM per page and may take several minutes. Proceed?",
                schema=ElicitConfirmation,
            )
            if not _check_elicit_accepted(elicit_result):
                return {"status": "cancelled", "reason": "user declined"}

        raw_path = Path(source_path)
        if not raw_path.exists():
            raise FileNotFoundError(f"source file not found: {source_path}")

        resolved_model = resolve_model(model)

        from xreadagent.translation.service import TranslationRequest, TranslationService

        service = TranslationService(workspace)
        request = TranslationRequest(
            source_path=raw_path,
            model=resolved_model,
            target_lang=target_lang,
            source_lang=source_lang,
        )
        job_id = service.start_translation(request)
        return {"job_id": job_id, "status": "started"}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def check_translation_status(
        job_id: str,
        workspace_path: str | None = None,
    ) -> dict[str, Any]:
        """Check the status of a translation job.

        Returns the job_id and its current state. If the job has
        finished, includes the output paths and duration.
        """
        # Translation jobs are tracked in-process by TranslationService.
        # The MCP stdio mode creates a fresh process each invocation, so
        # job status is only available within the same HTTP-mounted session.
        return {
            "job_id": job_id,
            "status": "unknown",
            "note": (
                "Translation job tracking requires the HTTP-mounted MCP "
                "server (same process). In stdio mode, each invocation "
                "is a fresh process and cannot access prior job state."
            ),
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_paper_summary(
        slug: str,
        workspace_path: str | None = None,
    ) -> dict[str, Any]:
        """Get a summary of a paper by its slug.

        Returns the paper's frontmatter (title, authors, year) and
        the content of the Background section.
        """
        workspace = resolve_workspace(workspace_path)
        path = workspace.papers_dir / f"{slug}.md"
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"paper not found: {slug}")

        from xreadagent.wiki.frontmatter_utils import (
            read_page_content,
            read_page_frontmatter,
        )

        fm = read_page_frontmatter(path)
        content = read_page_content(path)

        # Extract the Background section as a summary hint.
        summary = ""
        for section_name in ("Background", "Summary"):
            marker = f"## {section_name}"
            idx = content.find(marker)
            if idx >= 0:
                start = idx + len(marker)
                next_section = content.find("\n## ", start)
                if next_section >= 0:
                    summary = content[start:next_section].strip()
                else:
                    summary = content[start:].strip()
                break

        return {
            "slug": slug,
            "frontmatter": fm,
            "summary": summary,
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_papers(
        workspace_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all ingested papers in the workspace.

        Returns a list of paper summaries with slug, title, authors, year,
        and ingestion timestamp.
        """
        workspace = resolve_workspace(workspace_path)

        from xreadagent.wiki.frontmatter_utils import list_papers as _list_papers

        return _list_papers(workspace)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_concepts(
        workspace_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all concepts in the workspace.

        Returns a list of concept summaries with slug, title, aliases,
        and related paper count.
        """
        workspace = resolve_workspace(workspace_path)

        from xreadagent.wiki.frontmatter_utils import list_concepts as _list_concepts

        return _list_concepts(workspace)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def browse_wiki(
        path: str,
        workspace_path: str | None = None,
    ) -> dict[str, Any]:
        """Read a wiki page by its relative path.

        The path is relative to the workspace wiki directory. Examples:
        - "papers/my-paper-slug.md"
        - "concepts/my-concept-slug.md"
        - "index.md"
        - "overview.md"

        Returns the page content (after frontmatter) and frontmatter dict.
        """
        from xreadagent.wiki.paths import validate_wiki_path

        workspace = resolve_workspace(workspace_path)
        resolved = validate_wiki_path(workspace.wiki_dir, path)
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"wiki page not found: {path}")

        from xreadagent.wiki.frontmatter_utils import (
            read_page_content,
            read_page_frontmatter,
        )

        fm = read_page_frontmatter(resolved)
        content = read_page_content(resolved)

        try:
            rel = resolved.relative_to(workspace.root).as_posix()
        except ValueError:
            rel = resolved.as_posix()

        return {
            "path": rel,
            "frontmatter": fm,
            "content": content,
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def semantic_search(
        query: str,
        workspace_path: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search wiki pages by keyword (case-insensitive grep).

        Scans paper and concept pages, scoring each by the number of times
        the query appears, and returns the top matches. Each result has
        slug, title, page type, score, and a short snippet.
        """
        workspace = resolve_workspace(workspace_path)

        from xreadagent.wiki.keyword_search import search_wiki_pages

        return search_wiki_pages(workspace, query, top_k=top_k)


__all__ = ["register_tools"]
