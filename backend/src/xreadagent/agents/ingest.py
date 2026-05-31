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

Apply discipline (post-planner, pre-write):

- Empty ``ConceptFrontmatter.type`` is defaulted to ``"concept"`` because the
  LLM is asked for the *aliases / canonical name* of a concept, not its
  ontology slot.
- Per-source distillation entities / claims / relations / tasks get their
  infrastructure metadata (``workspaceId``, ``createdAt``, ``updatedAt``,
  ``origin``, ``status``) populated here so the LLM is never asked for facts
  it cannot know.
- Claims with ``entityIds`` that map to concept slugs are reverse-projected
  into the ``## Related Claims`` section of the matching concept page,
  closing the loop the LLM otherwise leaves open.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import ValidationError

from xreadagent.agents._defaults import DEFAULT_AGENT_MAX_TOKENS
from xreadagent.agents._merge import merge_concept_into_page
from xreadagent.agents.ingest_schema import IngestPlan
from xreadagent.agents.json_planner import (
    is_nested_list_string_error,
    is_truncated_output_error,
    make_json_planner,
    should_retry_with_json_planner,
)
from xreadagent.agents.tools import build_ingest_tools
from xreadagent.schemas.entities import Claim, SourceRef
from xreadagent.schemas.sources import Source
from xreadagent.schemas.wiki_pages import ConceptFrontmatter
from xreadagent.wiki.distillation import DistillationPayload, save_distillation
from xreadagent.wiki.index_regen import write_index
from xreadagent.wiki.log import WikiConversationLog, WikiLog
from xreadagent.wiki.pages import (
    CONCEPT_SECTIONS,
    PAPER_SECTIONS,
    read_page_frontmatter,
    write_concept_page,
    write_paper_page,
)
from xreadagent.wiki.workspace import Workspace

PlannerMethod = Literal["auto", "tool", "json"]


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

    concept_slugs: set[str] = set()
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
                # ``type`` defaults to "concept" when the LLM left it blank —
                # the field is metadata about *which kind* of concept page,
                # not something we should bother the LLM about for v1.
                ConceptFrontmatter(
                    title=concept.canonical_name,
                    aliases=concept.aliases,
                    type="concept",
                ),
                {
                    "Summary": concept.summary_section,
                    "Related Papers": related_papers_bullets,
                    "Related Claims": related_claims_bullets,
                    "Open Questions": "",
                },
            )
        touched.append(_relative(concept_path, workspace))
        concept_slugs.add(concept.slug)

    # Per-source distillation JSON — fold in source-side back-pointer so the
    # JSON is self-contained (audit + recompile contract).
    distillation = plan.distillation.model_copy(deep=True)
    if not distillation.source.id.strip():
        distillation = distillation.model_copy(update={"source": source.model_copy()})
    # If the LLM left ``sourceRefs`` empty on any entity/claim/etc., fill in a
    # back-pointer to the canonical source id before we persist.
    _ensure_source_refs(distillation, source.id)
    _inject_infrastructure_metadata(distillation, source=source, workspace=workspace)
    save_distillation(workspace, plan.paper.slug, distillation)
    touched.append(f"state/by-source/{plan.paper.slug}.json")

    # Reverse-project claims into the concept pages they reference. Done after
    # both concept pages and the distillation JSON are written so the entity
    # ↔ concept mapping is stable.
    _reverse_project_claims_into_concepts(
        workspace,
        plan=plan,
        distillation=distillation,
        concept_slugs=concept_slugs,
        source_slug=plan.paper.slug,
    )

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


def _utc_now_iso() -> str:
    """Return ``YYYY-MM-DDTHH:MM:SSZ`` (UTC, second-precision) per spec rules."""
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _inject_infrastructure_metadata(
    payload: DistillationPayload,
    *,
    source: Source,
    workspace: Workspace,
) -> None:
    """Fill the infra-only fields the LLM has no business knowing.

    ``workspaceId``, ``createdAt``, ``updatedAt`` get populated everywhere they
    are missing. ``origin`` defaults to ``ingest:{source.id}`` and ``status``
    defaults to ``"active"`` — both are skipped on Relation entries that
    already carry them (Relation has no ``status`` field meaningful at this
    layer; we still default to ``"active"`` for symmetry).

    The LLM-provided values are preserved when present so a future smarter
    planner can override these defaults.
    """
    now = _utc_now_iso()
    # We use the workspace root's directory name as a stable workspace id when
    # nothing better is available — same convention as the Go workspace_id.
    workspace_id = workspace.root.name or "workspace"
    origin = f"ingest:{source.id}" if source.id.strip() else "ingest"
    for collection in (
        payload.entities,
        payload.claims,
        payload.relations,
        payload.tasks,
    ):
        for item in collection:
            if not item.workspaceId:
                item.workspaceId = workspace_id
            if not item.createdAt:
                item.createdAt = now
            if not item.updatedAt:
                item.updatedAt = now
            if not item.origin:
                item.origin = origin
            if not item.status:
                item.status = "active"


def _reverse_project_claims_into_concepts(
    workspace: Workspace,
    *,
    plan: IngestPlan,
    distillation: DistillationPayload,
    concept_slugs: set[str],
    source_slug: str,
) -> None:
    """Walk ``distillation.claims`` and append each to its concepts' Related Claims.

    A claim references entities by ``entityIds``. An entity *is* a concept
    when one of these holds:
      - The entity's ``id`` matches a written concept slug verbatim.
      - The entity's ``id`` starts with the concept slug (handles the common
        ``ent-{slug}`` prefix the prompt suggests).
      - The entity's ``aliases`` include the concept slug.

    For each match we append a deduped bullet to that concept page's
    ``## Related Claims`` section. Missing concept pages or unmatched entity
    ids are silently skipped — this is best-effort enrichment, not a hard
    contract.
    """
    if not plan.distillation.claims:
        return

    entity_index = _build_entity_to_concept_index(distillation, concept_slugs)

    # Group claim bullets per concept slug so each page is only rewritten once.
    bullets_per_concept: dict[str, list[str]] = {}
    for claim in distillation.claims:
        targets: set[str] = set()
        for entity_id in claim.entityIds:
            slug = entity_index.get(entity_id)
            if slug is not None:
                targets.add(slug)
        if not targets:
            continue
        bullet = _format_claim_bullet(claim, source_slug)
        for slug in targets:
            bullets_per_concept.setdefault(slug, []).append(bullet)

    for slug, bullets in bullets_per_concept.items():
        _append_related_claim_to_concept(workspace, slug, bullets)


def _build_entity_to_concept_index(
    distillation: DistillationPayload, concept_slugs: set[str]
) -> dict[str, str]:
    """Return ``{entity_id: concept_slug}`` mapping for entities that ARE concepts."""
    mapping: dict[str, str] = {}
    for entity in distillation.entities:
        target: str | None = None
        if entity.id in concept_slugs:
            target = entity.id
        else:
            for slug in concept_slugs:
                if not slug:
                    continue
                if entity.id.endswith(slug) or slug in entity.aliases:
                    target = slug
                    break
        if target is not None:
            mapping[entity.id] = target
    return mapping


def _format_claim_bullet(claim: Claim, source_slug: str) -> str:
    title = claim.title.strip() or claim.summary.strip() or claim.id
    return f"- [{claim.id}] {title} ({source_slug})"


def _append_related_claim_to_concept(
    workspace: Workspace, concept_slug: str, bullets: list[str]
) -> None:
    """Append claim bullets to ``concepts/{slug}.md``'s Related Claims section.

    Reads the existing page, splits into sections, replaces the body of
    ``## Related Claims`` with the deduped union of old bullets + new
    bullets, and re-writes the page atomically via ``write_concept_page``
    (which preserves the section skeleton).
    """
    page_path = workspace.concepts_dir / f"{concept_slug}.md"
    if not page_path.exists():
        return

    body = page_path.read_text(encoding="utf-8")
    sections = _split_concept_sections(body)
    fm = read_page_frontmatter(page_path)

    existing_block = sections.get("Related Claims", "").strip()
    if existing_block == "_(not yet filled)_":
        existing_block = ""
    existing_lines = [
        line.strip() for line in existing_block.splitlines() if line.strip()
    ]
    seen = set(existing_lines)
    merged_lines = list(existing_lines)
    for bullet in bullets:
        if bullet not in seen:
            merged_lines.append(bullet)
            seen.add(bullet)
    sections["Related Claims"] = "\n".join(merged_lines)

    title_raw = fm.get("title", concept_slug) if isinstance(fm, dict) else concept_slug
    aliases_raw = fm.get("aliases", []) if isinstance(fm, dict) else []
    type_raw = fm.get("type", "concept") if isinstance(fm, dict) else "concept"
    title = str(title_raw or concept_slug)
    aliases = [str(a) for a in aliases_raw] if isinstance(aliases_raw, list) else []
    type_value = str(type_raw or "concept")
    frontmatter = ConceptFrontmatter(title=title, aliases=aliases, type=type_value)
    write_concept_page(workspace, concept_slug, frontmatter, sections)


def _split_concept_sections(body: str) -> dict[str, str]:
    """Return ``{section_name: body}`` for the four concept sections.

    Defensive — mirrors ``_split_existing_concept`` in ``_merge.py`` but kept
    private here to avoid widening that module's public API.
    """
    sections: dict[str, str] = {name: "" for name in CONCEPT_SECTIONS}
    if not body.strip():
        return sections

    lines = body.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for idx, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                start = idx + 1
                break

    current: str | None = None
    buffer: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            heading = stripped[3:].strip()
            current = heading if heading in sections else None
            buffer = []
            continue
        if current is not None:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    return sections


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

    ``headers`` may be passed through to the underlying chat model so callers
    routing through a Claude-Code-compatible proxy (which often filters by
    User-Agent or rejects ``x-stainless-*`` headers) can override the SDK
    defaults. ``planner_method`` selects the strategy:

    - ``"tool"``  — current behavior, ``with_structured_output`` (tool calling).
    - ``"json"``  — raw JSON-mode planner with repair (see ``json_planner.py``).
    - ``"auto"``  — try ``"tool"`` first; on either a ``list_type`` ValidationError
      (the nested-array-as-string GLM-via-proxy bug) or a ``model_type``-on-None
      ValidationError (the tool path returned nothing because the model's
      ``max_tokens`` budget was eaten by extended thinking) fall back to
      ``"json"`` and log a one-line warning to stderr.

    ``max_tokens`` lets callers raise the token budget the underlying chat
    model uses for its reply. Pass ``None`` (default) to apply
    :data:`xreadagent.agents._defaults.DEFAULT_AGENT_MAX_TOKENS`; pass an int
    to override. Read-only after construction via the ``max_tokens`` property.

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
        headers: dict[str, str] | None = None,
        planner_method: PlannerMethod = "auto",
        max_tokens: int | None = None,
    ) -> None:
        self._workspace = workspace
        self._system_prompt = system_prompt or INGEST_SYSTEM_PROMPT
        self._max_iterations = max_iterations
        self._headers: dict[str, str] = dict(headers or {})
        self._planner_method: PlannerMethod = planner_method
        # Resolve once at construction so the public ``max_tokens`` attribute
        # always reflects what the default planner would use; callers can
        # introspect it without re-deriving the default.
        self._max_tokens: int = (
            max_tokens if max_tokens is not None else DEFAULT_AGENT_MAX_TOKENS
        )
        if planner is not None:
            self._planner: IngestPlanner = planner
        elif model is not None:
            self._planner = _make_default_planner(
                model,
                headers=self._headers,
                planner_method=planner_method,
                max_tokens=self._max_tokens,
            )
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

    @property
    def headers(self) -> dict[str, str]:
        """Read-only view of the custom headers threaded into the default planner."""
        return dict(self._headers)

    @property
    def planner_method(self) -> PlannerMethod:
        return self._planner_method

    @property
    def max_tokens(self) -> int:
        """Read-only ``max_tokens`` the default planner uses for chat replies."""
        return self._max_tokens

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


def _make_default_planner(
    model: str,
    *,
    headers: dict[str, str] | None = None,
    planner_method: PlannerMethod = "auto",
    max_tokens: int | None = None,
) -> IngestPlanner:
    """Build a planner that uses LangChain's structured-output API.

    Imported lazily so the rest of the package stays importable when the
    LangChain extras are not installed. ``headers`` (when non-empty) is
    plumbed via ``default_headers`` which is supported by ``ChatAnthropic``
    and ``ChatOpenAI``; for other providers the kwarg is silently dropped if
    the constructor rejects it.

    ``max_tokens`` is forwarded to ``init_chat_model`` as an unknown kwarg —
    LangChain passes it through to the underlying provider class
    (``ChatAnthropic(max_tokens=...)``, ``ChatOpenAI(max_tokens=...)``). When
    ``None`` we fall back to :data:`DEFAULT_AGENT_MAX_TOKENS`. Providers that
    don't accept the kwarg are tolerated via the same ``TypeError`` retry
    we already use for ``default_headers``.
    """
    from langchain.chat_models import init_chat_model

    resolved_max_tokens = (
        max_tokens if max_tokens is not None else DEFAULT_AGENT_MAX_TOKENS
    )
    init_kwargs: dict[str, Any] = {"max_tokens": resolved_max_tokens}
    if headers:
        init_kwargs["default_headers"] = dict(headers)

    chat = _init_chat_model_with_optional_kwargs(init_chat_model, model, init_kwargs)

    tool_structured = chat.with_structured_output(IngestPlan)
    json_plan = make_json_planner(chat)

    def _invoke_tool(prompt: str) -> IngestPlan:
        result = tool_structured.invoke(prompt)
        if isinstance(result, IngestPlan):
            return result
        return IngestPlan.model_validate(result)

    def _plan(prompt: str, *, schema: type[IngestPlan]) -> IngestPlan:
        if planner_method == "json":
            result: IngestPlan = json_plan(prompt, schema=schema)
            return result
        if planner_method == "tool":
            return _invoke_tool(prompt)
        # ``auto``: prefer the tool path; retry via JSON on documented failures.
        try:
            return _invoke_tool(prompt)
        except ValidationError as exc:
            if not should_retry_with_json_planner(exc):
                raise
            if is_nested_list_string_error(exc):
                reason = "returned a nested list as a string"
            elif is_truncated_output_error(exc):
                reason = "returned no parseable result"
            else:  # pragma: no cover — should_retry already gated this
                reason = "produced a retry-able structured-output failure"
            print(
                f"[xreadagent] structured-output (tool) {reason}; "
                "retrying with JSON-mode planner",
                file=sys.stderr,
                flush=True,
            )
            fallback: IngestPlan = json_plan(prompt, schema=schema)
            return fallback

    return _plan


def _init_chat_model_with_optional_kwargs(
    init_chat_model: Any, model: str, init_kwargs: dict[str, Any]
) -> Any:
    """Call ``init_chat_model`` and gracefully drop kwargs the provider rejects.

    Both ``default_headers`` and ``max_tokens`` are provider-specific kwargs
    that LangChain forwards verbatim. Older providers / niche ones may raise
    ``TypeError`` for unknown kwargs; we retry without the offending kwarg
    rather than crash. The retry order is "drop headers first, then drop
    max_tokens" because losing the budget is the worse failure mode.
    """
    try:
        return init_chat_model(model, **init_kwargs)
    except TypeError:
        pass
    # Drop ``default_headers`` and retry — most common rejection.
    retry_kwargs = {k: v for k, v in init_kwargs.items() if k != "default_headers"}
    try:
        return init_chat_model(model, **retry_kwargs)
    except TypeError:
        # As a last resort drop everything we added and use the raw factory.
        return init_chat_model(model)
