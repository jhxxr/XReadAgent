# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared concept-page merge helper.

Used by ingest (``apply_plan``) and crystallize (``apply_crystallize``). Both
flows need to append a contribution sub-section under ``Summary`` plus extend
``Related Papers`` / ``Related Claims`` lists without losing prior content;
keeping the logic in one place avoids drift between two near-duplicate code
paths.

The merge rules are intentionally narrow — replacement / rewriting of prior
content is reserved for ``/crystallize`` with explicit user confirmation, and
even then is expressed via a ``CrystallizeConceptPatch`` so the call site reads
declaratively.
"""

from __future__ import annotations

from pathlib import Path

from xreadagent.schemas.wiki_pages import ConceptFrontmatter
from xreadagent.wiki.pages import (
    CONCEPT_SECTIONS,
    read_page_frontmatter,
    write_concept_page,
)
from xreadagent.wiki.workspace import Workspace


def merge_concept_into_page(
    workspace: Workspace,
    slug: str,
    *,
    canonical_name: str | None = None,
    aliases_to_add: list[str],
    summary_addition: str,
    summary_section_heading: str,
    related_papers_to_add: list[str],
    related_claims_to_add: list[str],
) -> Path:
    """Append a contribution to an existing (or new) concept page.

    - ``canonical_name`` — if the page does not exist yet, this becomes the
      page title; if the page exists, the existing title is preserved.
    - ``aliases_to_add`` — merged into the frontmatter alias list, deduped.
    - ``summary_addition`` — appended under ``## Summary`` as a sub-section
      headed ``### {summary_section_heading}``. Empty additions are skipped.
    - ``summary_section_heading`` — caller-chosen heading text. Ingest uses
      ``From {paper_slug}``; crystallize uses ``From query: {topic}``.
    - ``related_papers_to_add`` — paper slugs to add as ``[[papers/...|...]]``
      bullets in ``## Related Papers``, deduped.
    - ``related_claims_to_add`` — raw claim strings to add as bullets in
      ``## Related Claims``, deduped.
    """
    page_path = workspace.concepts_dir / f"{slug}.md"
    body = page_path.read_text(encoding="utf-8") if page_path.exists() else ""
    sections = _split_existing_concept(body)

    existing_aliases: list[str] = []
    existing_title = ""
    if page_path.exists():
        fm = read_page_frontmatter(page_path)
        raw_aliases = fm.get("aliases", [])
        if isinstance(raw_aliases, list):
            existing_aliases = [str(a) for a in raw_aliases]
        if isinstance(fm.get("title"), str):
            existing_title = str(fm["title"])
    merged_aliases = list(dict.fromkeys([*existing_aliases, *aliases_to_add]))

    addition = summary_addition.strip()
    if addition:
        heading = summary_section_heading.strip() or "Update"
        suffix = f"\n\n### {heading}\n\n{addition}\n"
        sections["Summary"] = sections.get("Summary", "").rstrip() + suffix

    if related_papers_to_add:
        sections["Related Papers"] = _append_bullets(
            sections.get("Related Papers", ""),
            [f"[[papers/{paper_slug}|{paper_slug}]]" for paper_slug in related_papers_to_add],
        )
    if related_claims_to_add:
        sections["Related Claims"] = _append_bullets(
            sections.get("Related Claims", ""),
            related_claims_to_add,
        )

    frontmatter = ConceptFrontmatter(
        title=existing_title or (canonical_name or slug),
        aliases=merged_aliases,
    )
    return write_concept_page(workspace, slug, frontmatter, sections)


def _split_existing_concept(body: str) -> dict[str, str]:
    """Return ``{section_name: body}`` for the four concept sections.

    Defensive — when the page is missing or malformed, return placeholders so
    downstream writers still emit a complete page.
    """
    if not body.strip():
        return {name: "" for name in CONCEPT_SECTIONS}

    lines = body.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for idx, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                start = idx + 1
                break

    sections: dict[str, str] = {name: "" for name in CONCEPT_SECTIONS}
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


def _append_bullets(existing: str, additions: list[str]) -> str:
    """Append bullets to an existing markdown bullet list, deduplicating."""
    existing_lines = [line for line in existing.splitlines() if line.strip()]
    have = {line.strip() for line in existing_lines if line.strip().startswith("- ")}
    new_bullets: list[str] = []
    for item in additions:
        formatted = f"- {item}".strip()
        if formatted not in have:
            new_bullets.append(formatted)
            have.add(formatted)
    if not new_bullets:
        return existing.strip()
    if existing_lines:
        return "\n".join([*existing_lines, *new_bullets])
    return "\n".join(new_bullets)


__all__ = ["merge_concept_into_page"]
