# SPDX-License-Identifier: AGPL-3.0-or-later
"""``translations/manifest.json`` reader / writer.

State JSON sidecar → **camelCase** wire schema per the backend guideline.

Cache lookup is keyed on the triple ``(sourceHash, targetLang, model)``:

- ``sourceHash`` because re-translating an edited PDF must actually re-run
  the engine (the bytes changed → the source slug may match but the work is
  different).
- ``targetLang`` because users may translate the same paper to two languages.
- ``model`` because output quality varies materially across providers; a
  user who upgrades from a budget model to a flagship one should NOT get
  the cached budget output.

Idempotency promise: ``find()`` returning a hit is the signal that the
on-disk PDFs are still valid for that triple. The orchestrator never deletes
old translations — only ``add`` replaces an existing entry with a freshly
translated one.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from xreadagent.wiki.atomic import atomic_write_text
from xreadagent.wiki.workspace import Workspace


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class TranslationEntry(_Strict):
    """One row in ``translations/manifest.json``.

    All paths are relative to the workspace root (e.g.
    ``translations/attention-aaa.dual.pdf``) so a workspace can be moved
    between machines without manifest rewrites.
    """

    sourceSlug: str
    sourceHash: str
    targetLang: str
    model: str
    monoPath: str | None = None
    dualPath: str | None = None
    translatedAt: str
    durationS: float
    babeldocVersion: str = ""


class TranslationsManifest(_Strict):
    """Top-level container persisted to ``translations/manifest.json``."""

    version: int = 1
    entries: list[TranslationEntry] = Field(default_factory=list)


class TranslationsIndex:
    """In-memory view of ``translations/manifest.json`` with atomic persistence.

    Mirrors :class:`xreadagent.wiki.sources.SourcesIndex` so callers familiar
    with the sources manifest see the same shape (load/save/find/add).
    """

    def __init__(self, workspace: Workspace, manifest: TranslationsManifest) -> None:
        self._workspace = workspace
        self._manifest = manifest

    @classmethod
    def load(cls, workspace: Workspace) -> TranslationsIndex:
        path = workspace.translations_manifest_path
        if not path.exists():
            return cls(workspace, TranslationsManifest())
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return cls(workspace, TranslationsManifest())
        manifest = TranslationsManifest.model_validate_json(raw)
        return cls(workspace, manifest)

    def save(self) -> None:
        payload = self._manifest.model_dump(mode="json")
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        atomic_write_text(self._workspace.translations_manifest_path, text)

    def find(
        self, source_hash: str, target_lang: str, model: str
    ) -> TranslationEntry | None:
        """Return the matching entry by ``(hash, lang, model)`` or ``None``."""
        for row in self._manifest.entries:
            if (
                row.sourceHash == source_hash
                and row.targetLang == target_lang
                and row.model == model
            ):
                return row
        return None

    def add(self, entry: TranslationEntry) -> None:
        """Insert ``entry``, replacing any existing row with the same key.

        Replacement (not de-dup) because a re-run of the same triple means
        the user explicitly asked for a fresh translation (e.g. they cleared
        the on-disk PDF). The new ``translatedAt`` timestamp should win.
        """
        key = (entry.sourceHash, entry.targetLang, entry.model)
        existing = [
            row
            for row in self._manifest.entries
            if (row.sourceHash, row.targetLang, row.model) != key
        ]
        self._manifest.entries = [*existing, entry]

    def all(self) -> list[TranslationEntry]:
        return list(self._manifest.entries)

    @property
    def manifest(self) -> TranslationsManifest:
        return self._manifest


__all__ = [
    "TranslationEntry",
    "TranslationsIndex",
    "TranslationsManifest",
]
