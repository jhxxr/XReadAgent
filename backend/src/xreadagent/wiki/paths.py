# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wiki directory layout, path validation, and slug helpers.

Ported from OpenSciReader's Go implementation:
- Path-segment validation: ``workspace_knowledge_files.go:709-723``
- Stable source slug:      ``workspace_wiki_service.go:1227-1240``
- Concept slug + counter:  ``workspace_knowledge_compile.go:634-647``
- Kebab slug:              ``workspace_knowledge_compile.go:816-843``
"""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path
from typing import Final

FORBIDDEN_PATH_CHARS: Final[frozenset[str]] = frozenset('<>:"/\\|?*')

WORKSPACE_LAYOUT: Final[dict[str, str]] = {
    "raw": "raw",
    "raw_processed": "raw/_processed",
    "extracts": "extracts",
    "state": "state",
    "state_by_source": "state/by-source",
    "wiki": "wiki",
    "wiki_papers": "wiki/papers",
    "wiki_concepts": "wiki/concepts",
    "wiki_queries": "wiki/queries",
    "translations": "translations",
}


def kebab_slug(value: str) -> str:
    """ASCII kebab-case slug. Mirrors ``workspaceKnowledgeSlug`` in Go."""
    trimmed = value.strip().lower()
    if not trimmed:
        return "item"

    # Strip diacritics so e.g. "café" maps to "cafe" before the ASCII filter.
    normalized = unicodedata.normalize("NFKD", trimmed)

    builder: list[str] = []
    last_hyphen = False
    for ch in normalized:
        if ch.isalnum() and ord(ch) < 128:
            builder.append(ch)
            last_hyphen = False
        elif builder and not last_hyphen:
            builder.append("-")
            last_hyphen = True

    slug = "".join(builder).strip("-")
    return slug or "item"


def stable_source_slug(title: str, source_key: str) -> str:
    """Append a 12-char sha256 of ``source_key`` to a kebab base.

    Example: ``stable_source_slug("Attention Is All You Need", "doc:123")`` ->
    ``"attention-is-all-you-need-a1b2c3d4e5f6"``.

    The hash collapses two papers with identical titles to distinct slugs and is
    deterministic so re-ingest yields the same on-disk filename.
    """
    base = kebab_slug(title) if title.strip() else "item"
    key = source_key.strip()
    if not key:
        return base
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"{base}-{digest}"


def concept_slug(canonical_name: str, existing: set[str]) -> str:
    """Return a unique concept slug, appending ``-2``, ``-3``, … on collision.

    ``existing`` should contain slugs already chosen in the current compile pass;
    the function does NOT mutate it (caller decides when to commit).
    """
    base = kebab_slug(canonical_name) if canonical_name.strip() else "concept"
    if base not in existing:
        return base
    counter = 2
    while True:
        candidate = f"{base}-{counter}"
        if candidate not in existing:
            return candidate
        counter += 1


def _validate_segment(segment: str) -> str:
    trimmed = segment.strip()
    if not trimmed:
        raise ValueError("path segment must not be empty")
    if trimmed in {".", ".."}:
        raise ValueError("path segment must not contain traversal segments")
    if any(ch in FORBIDDEN_PATH_CHARS for ch in trimmed):
        raise ValueError(
            "path segment must not contain Windows-invalid characters: "
            r'<>:"/\|?*'
        )
    return trimmed


def validate_wiki_path(workspace_root: Path, candidate: str | Path) -> Path:
    """Validate that ``candidate`` is a safe path inside ``workspace_root``.

    Returns the resolved absolute path. Raises ``ValueError`` if the candidate
    is absolute, contains ``..`` traversal, uses forbidden filename characters,
    or otherwise escapes ``workspace_root``.
    """
    if isinstance(candidate, Path):
        # Path objects can carry an absolute prefix on Windows that pure strings don't.
        if candidate.is_absolute():
            raise ValueError("candidate path must not be absolute")
        candidate_str = candidate.as_posix()
    else:
        candidate_str = candidate.strip()
        if not candidate_str:
            raise ValueError("candidate path must not be empty")
        if Path(candidate_str).is_absolute() or candidate_str.startswith(("/", "\\")):
            raise ValueError("candidate path must not be absolute")

    # Normalize backslashes so segment validation works uniformly on Windows.
    parts = [part for part in candidate_str.replace("\\", "/").split("/") if part]
    if not parts:
        raise ValueError("candidate path must contain at least one segment")
    for part in parts:
        _validate_segment(part)

    root_resolved = workspace_root.resolve()
    joined = (root_resolved / Path(*parts)).resolve()
    # Defensive check: ensure no symlink/.. trick escapes root after resolution.
    try:
        joined.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("candidate path escapes the workspace root") from exc
    return joined
