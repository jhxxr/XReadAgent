# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crystallize agent: propose patches from a query archive; ``apply_crystallize``
applies them after user review.

``CrystallizeAgent.propose`` reads the query archive + relevant pages and
emits a ``CrystallizePlan``. It does NOT write anything — review is the whole
point of the explicit ``/crystallize`` flow (D4 in ``plan.md`` §11).

``apply_crystallize`` is the user-confirmed write path. Section-targeted
append / replace_subsection on paper pages; create-or-merge on concept pages
(reusing the shared ``merge_concept_into_page`` helper); index regenerate;
log + conversation-log append.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import ValidationError

from xreadagent.agents._defaults import DEFAULT_AGENT_MAX_TOKENS
from xreadagent.agents._merge import merge_concept_into_page
from xreadagent.agents.crystallize_schema import (
    CrystallizeConceptPatch,
    CrystallizePaperPatch,
    CrystallizePlan,
)
from xreadagent.agents.json_planner import (
    is_nested_list_string_error,
    is_truncated_output_error,
    make_json_planner,
    should_retry_with_json_planner,
)
from xreadagent.schemas.wiki_pages import ConceptFrontmatter
from xreadagent.wiki.atomic import atomic_write_text
from xreadagent.wiki.index_regen import write_index
from xreadagent.wiki.log import WikiConversationLog, WikiLog
from xreadagent.wiki.pages import (
    PAPER_SECTIONS,
    read_page_frontmatter,
    write_concept_page,
)
from xreadagent.wiki.workspace import Workspace

PlannerMethod = Literal["auto", "tool", "json"]

# Map snake_case schema section names to the title-case headings the writer uses.
_PAPER_SECTION_HEADINGS: dict[str, str] = {
    "background": "Background",
    "challenges": "Challenges",
    "solution": "Solution",
    "positioning": "Positioning",
    "key_concepts": "Key Concepts",
    "experiments": "Experiments",
    "open_questions": "Open Questions",
}

# Defensive: heading map must cover every section in PAPER_SECTIONS.
assert set(_PAPER_SECTION_HEADINGS.values()) == set(PAPER_SECTIONS), (
    "_PAPER_SECTION_HEADINGS drifted from PAPER_SECTIONS"
)


def _load_system_prompt() -> str:
    resource = resources.files("xreadagent.agents.prompts").joinpath("crystallize_system.md")
    return resource.read_text(encoding="utf-8")


CRYSTALLIZE_SYSTEM_PROMPT = _load_system_prompt()


class CrystallizePlanner(Protocol):
    """Anything that can turn a query archive into a ``CrystallizePlan``."""

    def __call__(self, prompt: str, *, schema: type[CrystallizePlan]) -> CrystallizePlan: ...


@dataclass(frozen=True)
class CrystallizeResult:
    """Outcome of one ``apply_crystallize`` call."""

    plan: CrystallizePlan
    files_touched: list[str]
    duration_s: float = 0.0


@dataclass(frozen=True)
class CrystallizeProposal:
    """Outcome of one ``CrystallizeAgent.propose`` call (no writes performed)."""

    plan: CrystallizePlan
    tokens_used: dict[str, int] = field(default_factory=dict)
    duration_s: float = 0.0


class CrystallizeAgent:
    """LLM proposer for ``/crystallize``. Does NOT write.

    ``max_tokens`` lets callers raise the token budget the underlying chat
    model uses for its reply. Pass ``None`` (default) to apply
    :data:`xreadagent.agents._defaults.DEFAULT_AGENT_MAX_TOKENS`; pass an int
    to override. Read-only after construction via the ``max_tokens`` property.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        planner: CrystallizePlanner | None = None,
        headers: dict[str, str] | None = None,
        planner_method: PlannerMethod = "auto",
        max_tokens: int | None = None,
    ) -> None:
        self._workspace = workspace
        self._system_prompt = system_prompt or CRYSTALLIZE_SYSTEM_PROMPT
        self._headers: dict[str, str] = dict(headers or {})
        self._planner_method: PlannerMethod = planner_method
        self._max_tokens: int = (
            max_tokens if max_tokens is not None else DEFAULT_AGENT_MAX_TOKENS
        )
        if planner is not None:
            self._planner: CrystallizePlanner = planner
        elif model is not None:
            self._planner = _make_default_planner(
                model,
                headers=self._headers,
                planner_method=planner_method,
                max_tokens=self._max_tokens,
            )
        else:
            raise ValueError(
                "CrystallizeAgent requires either an explicit planner or a model string"
            )

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._headers)

    @property
    def planner_method(self) -> PlannerMethod:
        return self._planner_method

    @property
    def max_tokens(self) -> int:
        """Read-only ``max_tokens`` the default planner uses for chat replies."""
        return self._max_tokens

    async def propose(self, query_archive_path: Path) -> CrystallizeProposal:
        if not query_archive_path.exists():
            raise FileNotFoundError(f"query archive not found: {query_archive_path}")
        start = time.monotonic()
        prompt = self._build_prompt(query_archive_path)
        plan = self._planner(prompt, schema=CrystallizePlan)
        return CrystallizeProposal(
            plan=plan,
            tokens_used={},
            duration_s=time.monotonic() - start,
        )

    def _build_prompt(self, query_archive_path: Path) -> str:
        archive_body = query_archive_path.read_text(encoding="utf-8")
        try:
            rel = query_archive_path.relative_to(self._workspace.root).as_posix()
        except ValueError:
            rel = query_archive_path.as_posix()
        paper_summary = _summarize_papers(self._workspace)
        concept_summary = _summarize_concepts(self._workspace)
        return (
            f"{self._system_prompt}\n\n"
            "## Workspace state\n\n"
            f"Existing papers ({len(paper_summary)}):\n"
            + ("\n".join(f"- {row}" for row in paper_summary) or "_(none)_")
            + "\n\n"
            f"Existing concepts ({len(concept_summary)}):\n"
            + ("\n".join(f"- {row}" for row in concept_summary) or "_(none)_")
            + "\n\n"
            "## Query archive\n\n"
            f"- path: {rel}\n\n"
            f"{archive_body}\n"
        )


def _make_default_planner(
    model: str,
    *,
    headers: dict[str, str] | None = None,
    planner_method: PlannerMethod = "auto",
    max_tokens: int | None = None,
) -> CrystallizePlanner:
    from langchain.chat_models import init_chat_model

    from xreadagent.agents.ingest import _init_chat_model_with_optional_kwargs

    resolved_max_tokens = (
        max_tokens if max_tokens is not None else DEFAULT_AGENT_MAX_TOKENS
    )
    init_kwargs: dict[str, Any] = {"max_tokens": resolved_max_tokens}
    if headers:
        init_kwargs["default_headers"] = dict(headers)

    chat = _init_chat_model_with_optional_kwargs(init_chat_model, model, init_kwargs)

    tool_structured = chat.with_structured_output(CrystallizePlan)
    json_plan = make_json_planner(chat)

    def _invoke_tool(prompt: str) -> CrystallizePlan:
        result = tool_structured.invoke(prompt)
        if isinstance(result, CrystallizePlan):
            return result
        return CrystallizePlan.model_validate(result)

    def _plan(prompt: str, *, schema: type[CrystallizePlan]) -> CrystallizePlan:
        if planner_method == "json":
            result: CrystallizePlan = json_plan(prompt, schema=schema)
            return result
        if planner_method == "tool":
            return _invoke_tool(prompt)
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
            fallback: CrystallizePlan = json_plan(prompt, schema=schema)
            return fallback

    return _plan


def apply_crystallize(workspace: Workspace, plan: CrystallizePlan) -> CrystallizeResult:
    """Apply ``plan`` to the workspace. User-confirmed write path.

    Behavior:

    - For each ``paper_patches[i]``: load the existing paper page, modify the
      targeted section (append or replace_subsection), write atomically.
      Missing paper pages are skipped (we report them via the touched list
      with a ``[missing]`` marker so the caller can surface the failure).
    - For each ``concept_patches[i]``: route through ``merge_concept_into_page``
      so the alias dedup + summary append logic is shared with ingest.
    - Regenerate ``index.md`` if any paper or concept was touched.
    - Append to ``wiki/log.md`` with op ``crystallize``.
    - Append to the JSONL conversation log.
    """
    start = time.monotonic()
    workspace.ensure_layout()

    topic = _extract_topic_from_archive_path(plan.query_archive_path)
    touched: list[str] = []

    for paper_patch in plan.paper_patches:
        path = workspace.papers_dir / f"{paper_patch.paper_slug}.md"
        if not path.exists():
            touched.append(f"[missing] wiki/papers/{paper_patch.paper_slug}.md")
            continue
        new_body = _apply_paper_patch(path.read_text(encoding="utf-8"), paper_patch)
        atomic_write_text(path, new_body)
        touched.append(_relative(path, workspace))

    for concept_patch in plan.concept_patches:
        concept_path = _apply_concept_patch(workspace, concept_patch, topic=topic)
        touched.append(_relative(concept_path, workspace))

    if plan.paper_patches or plan.concept_patches:
        if write_index(workspace):
            touched.append("wiki/index.md")

    log_subject = plan.log_subject.strip() or "crystallize"
    WikiLog(workspace).append(
        "crystallize",
        log_subject,
        files_touched=touched,
    )
    touched.append("wiki/log.md")

    WikiConversationLog(workspace).append(
        {
            "event": "crystallize",
            "query_archive_path": plan.query_archive_path,
            "rationale": plan.rationale,
            "log_subject": log_subject,
            "files_touched": list(touched),
            "paper_patches": [p.model_dump(mode="json") for p in plan.paper_patches],
            "concept_patches": [c.model_dump(mode="json") for c in plan.concept_patches],
        }
    )

    return CrystallizeResult(
        plan=plan,
        files_touched=touched,
        duration_s=time.monotonic() - start,
    )


def _apply_paper_patch(body: str, patch: CrystallizePaperPatch) -> str:
    """Apply a single section-targeted patch to a paper page body."""
    heading = _PAPER_SECTION_HEADINGS[patch.section]
    parts = _split_paper_sections(body)
    section_body = parts["sections"].get(heading, "").rstrip()

    if patch.op == "append":
        addition = patch.new_content.strip()
        if not addition:
            parts["sections"][heading] = section_body
        else:
            merged = (section_body + ("\n\n" if section_body else "") + addition).rstrip()
            parts["sections"][heading] = merged
    else:
        sub_heading = (patch.subsection_heading or "").strip()
        if not sub_heading:
            raise ValueError(
                "replace_subsection requires a non-empty subsection_heading"
            )
        new_section = _replace_subsection(section_body, sub_heading, patch.new_content)
        parts["sections"][heading] = new_section

    return _render_paper_body(parts)


def _split_paper_sections(body: str) -> dict[str, Any]:
    """Split a paper page into ``{preamble, sections: {heading: body}}``.

    The preamble holds the frontmatter (``---``-fenced) and the ``# Title``
    line; everything else is a sequence of ``## {heading}`` blocks.
    """
    lines = body.splitlines()
    idx = 0

    # Frontmatter — preserve verbatim.
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                idx = j + 1
                break

    # H1 title line + a blank line. The writer renders this as
    # ``\n# {title}\n`` after the frontmatter — preserve verbatim too.
    while idx < len(lines) and not lines[idx].startswith("## "):
        idx += 1

    preamble = "\n".join(lines[:idx])

    sections: dict[str, str] = {name: "" for name in PAPER_SECTIONS}
    current: str | None = None
    buffer: list[str] = []
    for line in lines[idx:]:
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

    return {"preamble": preamble, "sections": sections}


def _render_paper_body(parts: dict[str, Any]) -> str:
    """Render the parts dict back into a full paper page body."""
    preamble = parts["preamble"]
    sections: dict[str, str] = parts["sections"]
    out: list[str] = [preamble.rstrip(), ""]
    for name in PAPER_SECTIONS:
        body = sections.get(name, "").strip() or "_(not yet filled)_"
        out.append(f"## {name}")
        out.append("")
        out.append(body)
        out.append("")
    return "\n".join(out)


def _replace_subsection(section_body: str, heading: str, new_content: str) -> str:
    """Replace one ``### {heading}`` block; append if it doesn't exist."""
    lines = section_body.splitlines()
    target = f"### {heading.strip()}"
    new_block = f"{target}\n\n{new_content.strip()}".rstrip()

    found_start: int | None = None
    block_end: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == target:
            found_start = i
            break
    if found_start is None:
        # Subsection didn't exist — append it as a new sub-section.
        suffix = "" if not section_body.strip() else "\n\n"
        return (section_body.rstrip() + suffix + new_block).strip()

    for j in range(found_start + 1, len(lines)):
        if lines[j].startswith("### "):
            block_end = j
            break
    if block_end is None:
        block_end = len(lines)

    rebuilt = "\n".join(
        [
            *lines[:found_start],
            new_block,
            *lines[block_end:],
        ]
    ).rstrip()
    return rebuilt


def _apply_concept_patch(
    workspace: Workspace,
    patch: CrystallizeConceptPatch,
    *,
    topic: str,
) -> Path:
    """Apply one concept patch via the shared merge helper or write a fresh page."""
    heading = f"From query: {topic}" if topic else "From query"
    if patch.op == "merge" or (workspace.concepts_dir / f"{patch.concept_slug}.md").exists():
        # Merge handles both "page exists" and the case where the LLM tagged
        # the patch as merge defensively — same logic either way.
        return merge_concept_into_page(
            workspace,
            patch.concept_slug,
            canonical_name=patch.canonical_name,
            aliases_to_add=patch.aliases_to_add,
            summary_addition=patch.summary_addition,
            summary_section_heading=heading,
            related_papers_to_add=patch.related_papers_to_add,
            related_claims_to_add=patch.related_claims_to_add,
        )

    related_papers_bullets = "\n".join(
        f"- [[papers/{slug}|{slug}]]" for slug in patch.related_papers_to_add
    )
    related_claims_bullets = "\n".join(f"- {claim}" for claim in patch.related_claims_to_add)
    title = (patch.canonical_name or patch.concept_slug).strip() or patch.concept_slug
    return write_concept_page(
        workspace,
        patch.concept_slug,
        ConceptFrontmatter(
            title=title,
            aliases=list(patch.aliases_to_add),
        ),
        {
            "Summary": patch.summary_addition,
            "Related Papers": related_papers_bullets,
            "Related Claims": related_claims_bullets,
            "Open Questions": "",
        },
    )


def _extract_topic_from_archive_path(archive_path: str) -> str:
    """Pull the topic slug out of ``wiki/queries/{topic}/{date}-{slug}.md``."""
    cleaned = archive_path.replace("\\", "/").strip("/")
    parts = cleaned.split("/")
    try:
        idx = parts.index("queries")
    except ValueError:
        return ""
    if idx + 1 < len(parts):
        return parts[idx + 1]
    return ""


def _relative(path: Path, workspace: Workspace) -> str:
    try:
        return path.relative_to(workspace.root).as_posix()
    except ValueError:
        return path.as_posix()


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


__all__ = [
    "CRYSTALLIZE_SYSTEM_PROMPT",
    "CrystallizeAgent",
    "CrystallizePlanner",
    "CrystallizeProposal",
    "CrystallizeResult",
    "apply_crystallize",
]
