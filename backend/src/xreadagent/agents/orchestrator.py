# SPDX-License-Identifier: AGPL-3.0-or-later
"""Top-level ingest orchestrator: pipeline + agent in one call.

Plays the role of OpenSciReader's ``IngestSource`` (Wails service entry point).
A typical caller is the FastAPI ``POST /api/ingest`` handler (Phase 2 work);
the function is async to keep the door open for a future streaming variant.

Idempotency: re-running an ingest on an unchanged file is a no-op when the
``wiki/papers/{slug}.md`` is already present. We never re-call the LLM in that
case — see ``IngestResult.cache_hit``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from xreadagent.agents.ingest import IngestAgent, IngestResult
from xreadagent.agents.ingest_schema import IngestPaperPage, IngestPlan
from xreadagent.pipeline.router import convert_source
from xreadagent.schemas.sources import Source
from xreadagent.schemas.wiki_pages import PaperFrontmatter
from xreadagent.wiki.distillation import DistillationPayload
from xreadagent.wiki.workspace import Workspace


def _placeholder_plan(source: Source) -> IngestPlan:
    """A minimal, LLM-free ``IngestPlan`` for a source that has no wiki page.

    Used by the cache-hit path (paper page already present) and by
    ``register_source`` (convert-only import). It carries the source identity
    so the job ``finish`` event has a slug + title, but no synthesized prose.
    """
    return IngestPlan(
        paper=IngestPaperPage(
            slug=source.slug,
            frontmatter=PaperFrontmatter(
                title=source.title,
                source=source.sourcePath,
                source_hash=source.contentHash,
            ),
            background="",
            challenges="",
            solution="",
            positioning="",
            key_concepts="",
            experiments="",
            open_questions="",
        ),
        concepts=[],
        distillation=DistillationPayload(source=source),
        log_subject="(no wiki page)",
        notes=["no LLM call: paper page not synthesized"],
    )


def register_source(
    workspace: Workspace,
    raw_path: Path,
    *,
    title: str | None = None,
    on_phase: Callable[[str], None] | None = None,
) -> IngestResult:
    """Convert + register ``raw_path`` WITHOUT calling the LLM.

    This is the decoupled "import" step: it runs the same conversion +
    ``state/sources.json`` write as ``ingest_source`` but stops before the
    ``analyzing`` / ``writing`` wiki-synthesis phases. Building the wiki later
    is an explicit, separate action (``ingest_source`` on the same file, which
    short-circuits the convert step via the content-hash idempotency check).

    ``cache_hit`` is ``True`` when a wiki page already exists for this source —
    i.e. the document was already fully ingested, so registering is a no-op.
    """
    if on_phase is not None:
        on_phase("converting")
    _convert_result, source = convert_source(workspace, raw_path, title=title)
    paper_path = workspace.papers_dir / f"{source.slug}.md"
    return IngestResult(
        source=source,
        plan=_placeholder_plan(source),
        files_touched=[source.extractPath],
        tokens_used={},
        duration_s=0.0,
        cache_hit=paper_path.exists(),
    )


async def ingest_source(
    workspace: Workspace,
    raw_path: Path,
    *,
    agent: IngestAgent,
    title: str | None = None,
    on_phase: Callable[[str], None] | None = None,
) -> IngestResult:
    """Convert ``raw_path`` then drive ``agent.ingest`` to produce the wiki pages.

    Short-circuits when both the source manifest already knows the content
    hash AND ``wiki/papers/{slug}.md`` exists — that's a "previously ingested,
    nothing changed" hit and we skip the LLM call entirely.

    ``on_phase`` is an optional progress hook (used by the job-based API
    surface): called with ``"converting"`` before the pipeline conversion and
    ``"analyzing"`` before the LLM call; ``agent.ingest`` additionally reports
    ``"writing"`` before the deterministic write-out. Existing callers (CLI,
    MCP tools) omit it and behave exactly as before.
    """
    if on_phase is not None:
        on_phase("converting")
    convert_result, source = convert_source(workspace, raw_path, title=title)

    paper_path = workspace.papers_dir / f"{source.slug}.md"
    if paper_path.exists():
        # Cache hit. Return a lightweight result so the API surface stays the
        # same; ``plan`` is a placeholder produced from the source row alone.
        return IngestResult(
            source=source,
            plan=_placeholder_plan(source),
            files_touched=[],
            tokens_used={},
            duration_s=0.0,
            cache_hit=True,
        )

    start = time.monotonic()
    if on_phase is not None:
        on_phase("analyzing")
        result = await agent.ingest(source, convert_result.output_path, on_phase=on_phase)
    else:
        # Keep the legacy call shape so injected test doubles that don't
        # accept the hook keep working unchanged.
        result = await agent.ingest(source, convert_result.output_path)

    # Preserve the per-call duration; agent.ingest already populates it but
    # callers might want the wall-clock from this orchestrator (which includes
    # the conversion step too).
    return IngestResult(
        source=result.source,
        plan=result.plan,
        files_touched=result.files_touched,
        tokens_used=result.tokens_used,
        duration_s=time.monotonic() - start,
        cache_hit=False,
    )
