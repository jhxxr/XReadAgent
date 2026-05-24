# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single-pass ingest agent + ``apply_plan`` deterministic writer.

``IngestAgent`` packages the LLM call (model + structured output for
``IngestPlan``). ``apply_plan`` is the pure function that takes a plan and
writes it to the workspace; it has no LLM dependency and is what tests
exercise.

Architecturally the LLM gateway in ``xreadagent.llm`` stays framework-agnostic
(plain ``httpx`` chat). This module is the one place LangChain types are
allowed to leak into the codebase — anything else routes via ``apply_plan``
on plain Pydantic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

from xreadagent.agents._merge import merge_concept_into_page
from xreadagent.agents.ingest_schema import IngestPlan
from xreadagent.agents.tools import build_ingest_tools
from xreadagent.schemas.entities import SourceRef
from xreadagent.schemas.sources import Source
from xreadagent.schemas.wiki_pages import ConceptFrontmatter
from xreadagent.wiki.distillation import DistillationPayload, save_distillation
from xreadagent.wiki.index_regen import write_index
from xreadagent.wiki.log import WikiConversationLog, WikiLog
from xreadagent.wiki.pages import (
    PAPER_SECTIONS,
    read_page_frontmatter,
    write_concept_page,
    write_paper_page,
)
from xreadagent.wiki.workspace import Workspace


def _load_system_prompt() -> str:
    resource = resources.files("xreadagent.agents.prompts").joinpath("ingest_system.md")
    return resource.read_text(encoding="utf-8")


INGEST_SYSTEM_PROMPT = _load_system_prompt()


class IngestPlanner(Protocol):
    """Anything that can turn an extract + workspace context into an ``IngestPlan``.

    The default planner uses LangChain's structured-output API; tests inject
    a stub that returns a pre-built plan so the LLM is never called.
    """

    def __call__(self, prompt: str, *, schema: type[IngestPlan]) -> IngestPlan: ...


@dataclass(frozen=True)
class IngestResult:
    """Outcome of a single ``IngestAgent.ingest`` call."""

    source: Source
    plan: IngestPlan
    files_touched: list[str]
    tokens_used: dict[str, int] = field(default_factory=dict)
    duration_s: float = 0.0
    cache_hit: bool = False


def apply_plan(workspace: Workspace, plan: IngestPlan, source: Source) -> list[str]:
    """Persist ``plan`` to ``workspace``. Returns relative paths that were written.

    Pure function over its inputs: same plan, same workspace ⇒ same on-disk
    state. The LLM is never called from inside this function; tests can drive
    it directly with hand-built plans.
    """
    workspace.ensure_layout()

    touched: list[str] = []

    paper_sections = {
        "Background": plan.paper.background,
        "Challenges": plan.paper.challenges,
        "Solution": plan.paper.solution,
        "Positioning": plan.paper.positioning,
        "Key Concepts": plan.paper.key_concepts,
        "Experiments": plan.paper.experiments,
        "Open Questions": plan.paper.open_questions,
    }
    # Defensive: ensure the seven sections match what ``write_paper_page`` writes.
    assert set(paper_sections.keys()) == set(PAPER_SECTIONS), (
        "paper section names drifted from PAPER_SECTIONS"
    )
    paper_path = write_paper_page(
        workspace,
        plan.paper.slug,
        plan.paper.frontmatter,
        paper_sections,
    )
    touched.append(_relative(paper_path, workspace))

    for concept in plan.concepts:
        if concept.op == "merge":
            concept_path = merge_concept_into_page(
                workspace,
                concept.slug,
                canonical_name=concept.canonical_name,
                aliases_to_add=concept.aliases,
                summary_addition=concept.summary_section,
                summary_section_heading=f"From {plan.paper.slug}",
                related_papers_to_add=concept.related_papers_addition,
                related_claims_to_add=concept.related_claims_addition,
            )
        else:
            related_papers_bullets = "\n".join(
                f"- [[papers/{slug}|{slug}]]" for slug in concept.related_papers_addition
            )
            related_claims_bullets = "\n".join(
                f"- {claim}" for claim in concept.related_claims_addition
            )
            concept_path = write_concept_page(
                workspace,
                concept.slug,
                ConceptFrontmatter(
                    title=concept.canonical_name,
                    aliases=concept.aliases,
                ),
                {
                    "Summary": concept.summary_section,
                    "Related Papers": related_papers_bullets,
                    "Related Claims": related_claims_bullets,
                    "Open Questions": "",
                },
            )
        touched.append(_relative(concept_path, workspace))

    # Per-source distillation JSON — fold in source-side back-pointer so the
    # JSON is self-contained (audit + recompile contract).
    distillation = plan.distillation.model_copy(deep=True)
    if not distillation.source.id.strip():
        distillation = distillation.model_copy(update={"source": source.model_copy()})
    # If the LLM left ``sourceRefs`` empty on any entity/claim/etc., fill in a
    # back-pointer to the canonical source id before we persist.
    _ensure_source_refs(distillation, source.id)
    save_distillation(workspace, plan.paper.slug, distillation)
    touched.append(f"state/by-source/{plan.paper.slug}.json")

    # Regenerate the index from current papers + concepts on disk.
    if write_index(workspace):
        touched.append("wiki/index.md")

    WikiLog(workspace).append(
        "ingest",
        plan.log_subject or plan.paper.frontmatter.title or plan.paper.slug,
        files_touched=touched,
    )
    touched.append("wiki/log.md")

    WikiConversationLog(workspace).append(
        {
            "event": "ingest",
            "source_id": source.id,
            "slug": plan.paper.slug,
            "files_touched": list(touched),
            "concepts_touched": [c.slug for c in plan.concepts],
            "notes": list(plan.notes),
        }
    )
    return touched


def _ensure_source_refs(payload: DistillationPayload, source_id: str) -> None:
    """If the LLM left ``sourceRefs`` empty, fill in a back-pointer to ``source_id``.

    Mutates ``payload`` in place. The ``sourceRefs`` list lives on Entity /
    Claim / Relation / Task — we touch each.
    """
    cleaned_id = source_id.strip()
    if not cleaned_id:
        return
    for collection in (payload.entities, payload.claims, payload.relations, payload.tasks):
        for item in collection:
            if not item.sourceRefs:
                item.sourceRefs = [SourceRef(sourceId=cleaned_id)]


def _relative(path: Path, workspace: Workspace) -> str:
    try:
        return path.relative_to(workspace.root).as_posix()
    except ValueError:
        return path.as_posix()


class IngestAgent:
    """Single-pass ingest agent: tool-free structured output + ``apply_plan``.

    The planner is pluggable so tests can inject a stub that returns a
    pre-built ``IngestPlan`` without any LangChain types. The default
    ``_default_planner`` builds a LangChain model and uses
    ``with_structured_output``.

    A future iteration can swap the planner for a full deepagents loop with
    tool calls — the wiki primitives, ``apply_plan``, and this class's
    contract do not need to change for that.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        planner: IngestPlanner | None = None,
        max_iterations: int = 8,
    ) -> None:
        self._workspace = workspace
        self._system_prompt = system_prompt or INGEST_SYSTEM_PROMPT
        self._max_iterations = max_iterations
        if planner is not None:
            self._planner: IngestPlanner = planner
        elif model is not None:
            self._planner = _make_default_planner(model)
        else:
            raise ValueError(
                "IngestAgent requires either an explicit planner or a model string"
            )
        # Build tools eagerly so callers that want to expose them via MCP have
        # a handle (Phase 3 work). They are not invoked by the default planner.
        self._tools = build_ingest_tools(workspace)

    @property
    def tools(self) -> list[Any]:
        return list(self._tools)

    async def ingest(self, source: Source, extract_path: Path) -> IngestResult:
        if not extract_path.exists():
            raise FileNotFoundError(f"extract not found: {extract_path}")
        extract_md = extract_path.read_text(encoding="utf-8")
        start = time.monotonic()
        prompt = self._build_prompt(source, extract_md)
        plan = self._planner(prompt, schema=IngestPlan)
        files_touched = apply_plan(self._workspace, plan, source)
        return IngestResult(
            source=source,
            plan=plan,
            files_touched=files_touched,
            tokens_used={},
            duration_s=time.monotonic() - start,
            cache_hit=False,
        )

    def _build_prompt(self, source: Source, extract_md: str) -> str:
        # We bundle the system prompt + concise workspace summary + extract
        # into a single prompt string. The default planner prepends this to
        # the model's `messages` slot.
        concept_summary = _summarize_concepts(self._workspace)
        paper_summary = _summarize_papers(self._workspace)
        header = (
            f"{self._system_prompt}\n\n"
            f"## Workspace state\n\n"
            f"Existing papers ({len(paper_summary)}):\n"
            + ("\n".join(f"- {row}" for row in paper_summary) or "_(none)_")
            + "\n\n"
            f"Existing concepts ({len(concept_summary)}):\n"
            + ("\n".join(f"- {row}" for row in concept_summary) or "_(none)_")
            + "\n\n"
            "## Source metadata\n\n"
            f"- id: {source.id}\n"
            f"- title: {source.title}\n"
            f"- slug: {source.slug}\n"
            f"- contentHash: {source.contentHash}\n"
            f"- pageCount: {source.pageCount}\n\n"
            "## Paper extract (markdown)\n\n"
        )
        return header + extract_md


def _summarize_papers(workspace: Workspace) -> list[str]:
    rows: list[str] = []
    if not workspace.papers_dir.exists():
        return rows
    for path in sorted(workspace.papers_dir.iterdir()):
        if not path.is_file() or path.suffix != ".md":
            continue
        try:
            fm = read_page_frontmatter(path)
        except (OSError, UnicodeDecodeError):
            fm = {}
        title = fm.get("title", "") if isinstance(fm, dict) else ""
        rows.append(f"{path.stem} — {title}")
    return rows


def _summarize_concepts(workspace: Workspace) -> list[str]:
    rows: list[str] = []
    if not workspace.concepts_dir.exists():
        return rows
    for path in sorted(workspace.concepts_dir.iterdir()):
        if not path.is_file() or path.suffix != ".md":
            continue
        try:
            fm = read_page_frontmatter(path)
        except (OSError, UnicodeDecodeError):
            fm = {}
        title = fm.get("title", "") if isinstance(fm, dict) else ""
        aliases_raw = fm.get("aliases", []) if isinstance(fm, dict) else []
        aliases = [str(a) for a in aliases_raw] if isinstance(aliases_raw, list) else []
        alias_part = f" (aliases: {', '.join(aliases)})" if aliases else ""
        rows.append(f"{path.stem} — {title}{alias_part}")
    return rows


def _make_default_planner(model: str) -> IngestPlanner:
    """Build a planner that uses LangChain's structured-output API.

    Imported lazily so the rest of the package stays importable when the
    LangChain extras are not installed.
    """
    from langchain.chat_models import init_chat_model

    chat = init_chat_model(model)
    structured = chat.with_structured_output(IngestPlan)

    def _plan(prompt: str, *, schema: type[IngestPlan]) -> IngestPlan:
        result = structured.invoke(prompt)
        if isinstance(result, IngestPlan):
            return result
        # ``with_structured_output`` may return a dict when the schema can't be
        # represented as a Pydantic instance by the provider — validate explicitly.
        return IngestPlan.model_validate(result)

    return _plan
