# SPDX-License-Identifier: AGPL-3.0-or-later
"""Workspace bootstrap — the on-disk root of a single XReadAgent vault.

The ``Workspace`` is a thin runtime object (not a Pydantic schema): it knows
its root directory plus the canonical paths inside it. It does NOT cache state
beyond that, so a single instance is safe to share across threads.

See ``plan.md`` §2.1 for the directory contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from xreadagent.wiki.paths import WORKSPACE_LAYOUT

_MANAGED_NOTE: Final[str] = (
    "<!-- Managed by XReadAgent. Sections delimited by `<!-- xread:managed -->` "
    "are regenerated automatically; hand-edits inside those blocks may be overwritten. -->"
)


def _initial_index_md(title: str) -> str:
    return (
        f"# {title}\n\n"
        f"{_MANAGED_NOTE}\n\n"
        "## Documents\n\n"
        "_(no documents yet — run an ingest to populate)_\n\n"
        "## Concepts\n\n"
        "_(no concepts yet)_\n\n"
        "## Stats\n\n"
        "- documents: 0\n"
        "- concepts: 0\n"
        "- last_ingest_at: never\n"
    )


def _initial_log_md(title: str) -> str:
    return (
        f"# {title} — log\n\n"
        "Append-only ledger of ingest / query / lint / crystallize operations.\n"
        "Newest entries are appended at the bottom.\n"
    )


def _initial_overview_md(title: str) -> str:
    return (
        f"# {title} — overview\n\n"
        f"{_MANAGED_NOTE}\n\n"
        "_(empty — overview is rebuilt by the ingest agent as papers are added)_\n"
    )


def _initial_open_questions_md(title: str) -> str:
    return (
        f"# {title} — open questions\n\n"
        f"{_MANAGED_NOTE}\n\n"
        "_(no open questions yet)_\n"
    )


def _initial_sources_manifest(workspace_id: str) -> str:
    payload = {"workspaceId": workspace_id, "sources": []}
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _initial_compile_summary() -> str:
    payload = {
        "sourceCount": 0,
        "entityCount": 0,
        "claimCount": 0,
        "relationCount": 0,
        "taskCount": 0,
        "compileDirty": False,
        "wikiDirty": False,
        "lastCompiledAt": "",
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _initial_translations_manifest() -> str:
    """Seed for ``translations/manifest.json``.

    Stays a stable shape from v1 — see ``translation/manifest.py`` for the
    Pydantic schema that reads / writes this file.
    """
    payload = {"version": 1, "entries": []}
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


@dataclass(frozen=True)
class Workspace:
    """Filesystem root + derived canonical paths for one XReadAgent vault."""

    root: Path
    paths: dict[str, Path] = field(default_factory=dict)

    @classmethod
    def at(cls, root: Path | str) -> Workspace:
        """Build a ``Workspace`` rooted at ``root`` (resolved to absolute)."""
        root_path = Path(root).resolve()
        paths = {key: root_path / rel for key, rel in WORKSPACE_LAYOUT.items()}
        return cls(root=root_path, paths=paths)

    def ensure_layout(self) -> None:
        """Create every layout directory. Idempotent — safe to call repeatedly."""
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in self.paths.values():
            directory.mkdir(parents=True, exist_ok=True)

    def is_initialized(self) -> bool:
        """True iff a previous ``init_empty`` (or equivalent) ran on this root."""
        return self.index_md_path.exists()

    def init_empty(self, title: str, *, workspace_id: str = "") -> None:
        """Create the seed wiki files. Existing files are NOT overwritten."""
        clean_title = title.strip() or "Workspace"
        self.ensure_layout()

        _write_if_missing(self.index_md_path, _initial_index_md(clean_title))
        _write_if_missing(self.log_md_path, _initial_log_md(clean_title))
        _write_if_missing(self.overview_md_path, _initial_overview_md(clean_title))
        _write_if_missing(self.open_questions_md_path, _initial_open_questions_md(clean_title))
        _write_if_missing(self.sources_json_path, _initial_sources_manifest(workspace_id))
        _write_if_missing(self.compile_summary_json_path, _initial_compile_summary())
        _write_if_missing(
            self.translations_manifest_path, _initial_translations_manifest()
        )

    # ------------------------------------------------------------------
    # Convenience accessors — keep all path arithmetic in one place so call
    # sites never have to know the exact relative layout.
    # ------------------------------------------------------------------

    @property
    def wiki_dir(self) -> Path:
        return self.paths["wiki"]

    @property
    def papers_dir(self) -> Path:
        return self.paths["wiki_papers"]

    @property
    def concepts_dir(self) -> Path:
        return self.paths["wiki_concepts"]

    @property
    def queries_dir(self) -> Path:
        return self.paths["wiki_queries"]

    @property
    def raw_dir(self) -> Path:
        return self.paths["raw"]

    @property
    def raw_processed_dir(self) -> Path:
        return self.paths["raw_processed"]

    @property
    def extracts_dir(self) -> Path:
        return self.paths["extracts"]

    @property
    def state_dir(self) -> Path:
        return self.paths["state"]

    @property
    def state_by_source_dir(self) -> Path:
        return self.paths["state_by_source"]

    @property
    def translations_dir(self) -> Path:
        return self.paths["translations"]

    @property
    def translations_manifest_path(self) -> Path:
        return self.translations_dir / "manifest.json"

    @property
    def index_md_path(self) -> Path:
        return self.wiki_dir / "index.md"

    @property
    def log_md_path(self) -> Path:
        return self.wiki_dir / "log.md"

    @property
    def overview_md_path(self) -> Path:
        return self.wiki_dir / "overview.md"

    @property
    def open_questions_md_path(self) -> Path:
        return self.wiki_dir / "open-questions.md"

    @property
    def sources_json_path(self) -> Path:
        return self.state_dir / "sources.json"

    @property
    def compile_summary_json_path(self) -> Path:
        return self.state_dir / "compile-summary.json"

    @property
    def conversation_log_path(self) -> Path:
        return self.state_dir / "conversation-log.jsonl"

    @property
    def vec_sqlite_path(self) -> Path:
        return self.state_dir / "vec.sqlite"


def _write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
