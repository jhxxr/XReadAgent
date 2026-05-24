# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wiki page writers — Paper / Concept / Query.

The three page types each have a fixed section skeleton (see
``research/llm-wiki-prior-art.md`` § "Page templates"). The writer enforces
the skeleton even when the agent supplies an empty body for a section, so
downstream readers can rely on deterministic structure.

Frontmatter is YAML serialized by ``PyYAML``. We use ``safe_dump`` with
``sort_keys=False`` so the order matches the Pydantic field declaration order,
which keeps diffs stable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Mapping

import yaml

from xreadagent.schemas.wiki_pages import (
    ConceptFrontmatter,
    PaperFrontmatter,
    QueryFrontmatter,
)
from xreadagent.wiki.atomic import atomic_write_text
from xreadagent.wiki.paths import kebab_slug
from xreadagent.wiki.workspace import Workspace

PAPER_SECTIONS: Final[tuple[str, ...]] = (
    "Background",
    "Challenges",
    "Solution",
    "Positioning",
    "Key Concepts",
    "Experiments",
    "Open Questions",
)

CONCEPT_SECTIONS: Final[tuple[str, ...]] = (
    "Summary",
    "Related Papers",
    "Related Claims",
    "Open Questions",
)

QUERY_SECTIONS: Final[tuple[str, ...]] = (
    "Question",
    "Answer",
    "Sources",
)

_PLACEHOLDER: Final[str] = "_(not yet filled)_"


def _frontmatter_block(payload: Mapping[str, object]) -> str:
    body = yaml.safe_dump(
        dict(payload),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip("\n")
    return f"---\n{body}\n---\n"


def _render_sections(
    section_names: tuple[str, ...], sections: Mapping[str, str]
) -> str:
    parts: list[str] = []
    for name in section_names:
        body = sections.get(name, "").strip()
        parts.append(f"\n## {name}\n\n{body or _PLACEHOLDER}\n")
    return "".join(parts)


def write_paper_page(
    workspace: Workspace,
    slug: str,
    frontmatter: PaperFrontmatter,
    sections: Mapping[str, str],
) -> Path:
    clean_slug = _safe_slug(slug)
    path = workspace.papers_dir / f"{clean_slug}.md"
    body = (
        _frontmatter_block(frontmatter.model_dump(mode="json"))
        + f"\n# {frontmatter.title.strip() or clean_slug}\n"
        + _render_sections(PAPER_SECTIONS, sections)
    )
    atomic_write_text(path, body)
    return path


def write_concept_page(
    workspace: Workspace,
    slug: str,
    frontmatter: ConceptFrontmatter,
    sections: Mapping[str, str],
) -> Path:
    clean_slug = _safe_slug(slug)
    path = workspace.concepts_dir / f"{clean_slug}.md"
    body = (
        _frontmatter_block(frontmatter.model_dump(mode="json"))
        + f"\n# {frontmatter.title.strip() or clean_slug}\n"
        + _render_sections(CONCEPT_SECTIONS, sections)
    )
    atomic_write_text(path, body)
    return path


def write_query_page(
    workspace: Workspace,
    topic: str,
    date: str,
    slug: str,
    frontmatter: QueryFrontmatter,
    sections: Mapping[str, str],
) -> Path:
    topic_slug = _safe_slug(topic)
    date_clean = date.strip()
    if not date_clean:
        raise ValueError("date must be non-empty (typically YYYY-MM-DD)")
    body_slug = _safe_slug(slug)

    topic_dir = workspace.queries_dir / topic_slug
    path = topic_dir / f"{date_clean}-{body_slug}.md"
    body = (
        _frontmatter_block(frontmatter.model_dump(mode="json"))
        + f"\n# {frontmatter.question.strip() or body_slug}\n"
        + _render_sections(QUERY_SECTIONS, sections)
    )
    atomic_write_text(path, body)
    return path


def read_page_frontmatter(path: Path) -> dict[str, object]:
    """Return the YAML frontmatter of a wiki page as a dict.

    Cheap — only reads until the closing ``---`` delimiter. Returns ``{}`` if
    the file lacks a frontmatter block.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    block_lines: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        block_lines.append(line)
    if not block_lines:
        return {}
    parsed = yaml.safe_load("\n".join(block_lines))
    if not isinstance(parsed, dict):
        return {}
    return {str(k): v for k, v in parsed.items()}


def _safe_slug(value: str) -> str:
    """Defensive slug normalization for callers passing raw titles."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("slug must be non-empty")
    # If the caller already supplied a kebab slug, ``kebab_slug`` is a no-op.
    return kebab_slug(cleaned)
