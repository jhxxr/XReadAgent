# SPDX-License-Identifier: AGPL-3.0-or-later
"""``state/sources.json`` reader / writer.

Idempotency contract (per ``plan.md`` §2.4): we key on ``contentHash`` so
re-running ingest on an unchanged file is a no-op. ``add_or_update`` returns
``True`` only when the manifest actually changed; ``False`` when the incoming
``Source`` was byte-identical to one already on disk.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from xreadagent.schemas.sources import Source, SourcesManifest
from xreadagent.wiki.atomic import atomic_write_text
from xreadagent.wiki.workspace import Workspace

_CHUNK_SIZE: Final[int] = 65536


def compute_content_hash(path: Path) -> str:
    """SHA-256 of the file bytes — the canonical idempotency key."""
    hasher = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


class SourcesIndex:
    """In-memory view of ``state/sources.json`` with atomic persistence."""

    def __init__(self, workspace: Workspace, manifest: SourcesManifest) -> None:
        self._workspace = workspace
        self._manifest = manifest

    @classmethod
    def load(cls, workspace: Workspace) -> SourcesIndex:
        path = workspace.sources_json_path
        if not path.exists():
            return cls(workspace, SourcesManifest())
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return cls(workspace, SourcesManifest())
        manifest = SourcesManifest.model_validate_json(raw)
        return cls(workspace, manifest)

    def save(self) -> None:
        payload = self._manifest.model_dump(mode="json")
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        atomic_write_text(self._workspace.sources_json_path, text)

    def add_or_update(self, source: Source) -> bool:
        """Insert ``source`` (by id), or update an existing row.

        Returns ``True`` if the manifest changed (and should be re-saved),
        ``False`` if the incoming ``source`` was byte-identical to the row
        already on file (idempotent re-ingest).
        """
        existing = self.find_by_id(source.id)
        if existing is not None:
            if existing == source:
                return False
            self._manifest.sources = [
                source if row.id == source.id else row for row in self._manifest.sources
            ]
            return True
        self._manifest.sources = [*self._manifest.sources, source]
        return True

    def find_by_hash(self, content_hash: str) -> Source | None:
        for row in self._manifest.sources:
            if row.contentHash == content_hash:
                return row
        return None

    def find_by_id(self, source_id: str) -> Source | None:
        for row in self._manifest.sources:
            if row.id == source_id:
                return row
        return None

    def all(self) -> list[Source]:
        return list(self._manifest.sources)

    @property
    def manifest(self) -> SourcesManifest:
        return self._manifest
