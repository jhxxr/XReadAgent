# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic stub planners used when ``XREADAGENT_STUB_PLANNER=1``.

Never invoke real LLMs. The plans they return are intentionally minimal but
schema-valid so the CLI can exercise the end-to-end ingest / query loop
without a network call. Tests use these instead of mocking ``langchain``
inside ``IngestAgent`` / ``QueryAgent``.
"""

from __future__ import annotations

import re

from xreadagent.agents.ingest_schema import (
    IngestConceptTouch,
    IngestPaperPage,
    IngestPlan,
)
from xreadagent.agents.query_schema import CitedEvidence, QueryAnswer
from xreadagent.schemas.entities import Entity, SourceRef
from xreadagent.schemas.sources import Source
from xreadagent.schemas.wiki_pages import PaperFrontmatter
from xreadagent.wiki.distillation import DistillationPayload


def _slug_from_prompt(prompt: str) -> str:
    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped.startswith("- slug:"):
            return stripped.split(":", 1)[1].strip()
    return "stub-paper"


def _title_from_prompt(prompt: str) -> str:
    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped.startswith("- title:"):
            return stripped.split(":", 1)[1].strip() or "Stub Paper"
    return "Stub Paper"


def _hash_from_prompt(prompt: str) -> str:
    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped.startswith("- contentHash:"):
            return stripped.split(":", 1)[1].strip()
    return "stubhash"


def _source_path_from_prompt(prompt: str) -> str:
    return "raw/_processed/stub-source"


def stub_ingest_planner(prompt: str, *, schema: type[IngestPlan]) -> IngestPlan:
    """Return a tiny but schema-valid ``IngestPlan``.

    Deterministic from the prompt: slug / title / contentHash are extracted
    from the workspace-summary block the IngestAgent inserts into the prompt.
    """
    assert schema is IngestPlan
    slug = _slug_from_prompt(prompt)
    title = _title_from_prompt(prompt)
    content_hash = _hash_from_prompt(prompt)

    placeholder_source = Source(
        id=slug,
        title=title,
        slug=slug,
        contentHash=content_hash,
        sourcePath=_source_path_from_prompt(prompt),
    )

    return IngestPlan(
        paper=IngestPaperPage(
            slug=slug,
            frontmatter=PaperFrontmatter(
                title=title,
                source=placeholder_source.sourcePath,
                source_hash=content_hash,
            ),
            background="(stub) background section",
            challenges="(stub) challenges section",
            solution="(stub) solution section",
            positioning="(stub) positioning section",
            key_concepts="- [[concepts/stub-concept|Stub Concept]]",
            experiments="(stub) experiments section",
            open_questions="(stub) open questions",
        ),
        concepts=[
            IngestConceptTouch(
                slug="stub-concept",
                canonical_name="Stub Concept",
                op="create",
                summary_section=f"Auto-stub concept from {slug}.",
                related_papers_addition=[slug],
            )
        ],
        distillation=DistillationPayload(
            source=placeholder_source,
            entities=[
                Entity(
                    id="ent-stub-concept",
                    title="Stub Concept",
                    sourceRefs=[SourceRef(sourceId=slug)],
                )
            ],
        ),
        log_subject=title,
        notes=["stub-planner: no LLM call was made"],
    )


_QUESTION_RE = re.compile(r"^- question:\s*(.+)$", re.MULTILINE)


def _question_from_prompt(prompt: str) -> str:
    match = _QUESTION_RE.search(prompt)
    if match is None:
        return ""
    return match.group(1).strip()


def stub_query_planner(prompt: str, *, schema: type[QueryAnswer]) -> QueryAnswer:
    """Return a minimal ``QueryAnswer`` whose evidence references no real page."""
    assert schema is QueryAnswer
    question = _question_from_prompt(prompt) or "(unknown question)"
    return QueryAnswer(
        question=question,
        answer_markdown=(
            "(stub answer) The stub planner is active because "
            "XREADAGENT_STUB_PLANNER=1 was set; no real LLM was called."
        ),
        evidence=[
            CitedEvidence(
                source_wiki_path="wiki/index.md",
                quote="",
                confidence="low",
            )
        ],
        layers_used=["index"],
        sources_cited=["wiki/index.md"],
        confidence="low",
        notes=["stub-planner: deterministic answer, no LLM call"],
        open_questions_raised=[],
    )


def use_stub_planner() -> bool:
    """Return ``True`` iff the env opt-in for the stub planner is set."""
    import os

    return os.environ.get("XREADAGENT_STUB_PLANNER", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


__all__ = [
    "stub_ingest_planner",
    "stub_query_planner",
    "use_stub_planner",
]
