# SPDX-License-Identifier: AGPL-3.0-or-later
"""Top-level ingest converter — file → ``extracts/{slug}.md`` + manifest update.

``convert_source`` is the single entry point the agent layer (next dispatch)
will call when the user drops a file into ``raw/``. It:

1. computes a content hash + stable slug,
2. short-circuits if ``state/sources.json`` already has that hash,
3. routes by suffix (PDF → MinerU, office/web → markitdown),
4. writes the markdown under ``extracts/{slug}.md``,
5. archives the raw file under ``raw/_processed/{slug}.{ext}``,
6. records the source in ``SourcesIndex`` and appends to ``wiki/log.md``.

The conversion itself is delegated to ``MarkdownConverter`` / ``MineruConverter``
which are injectable for tests.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from xreadagent.pipeline.markitdown_converter import convert_with_markitdown
from xreadagent.pipeline.mineru_converter import MineruConverter
from xreadagent.pipeline.types import (
    MARKITDOWN_SUFFIXES,
    MINERU_SUFFIXES,
    ConvertResult,
    UnsupportedFormatError,
)
from xreadagent.schemas.sources import Source
from xreadagent.wiki.log import WikiLog
from xreadagent.wiki.paths import stable_source_slug
from xreadagent.wiki.sources import SourcesIndex, compute_content_hash
from xreadagent.wiki.workspace import Workspace


class _PdfConverter(Protocol):
    def convert(self, input_path: Path, output_dir: Path) -> ConvertResult: ...


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _classify(suffix: str) -> str:
    if suffix in MINERU_SUFFIXES:
        return "pdf"
    if suffix in MARKITDOWN_SUFFIXES:
        return "office"
    raise UnsupportedFormatError(
        f"unsupported input suffix {suffix!r}; "
        f"supported: {sorted(MARKITDOWN_SUFFIXES | MINERU_SUFFIXES)}"
    )


def convert_source(
    workspace: Workspace,
    input_path: Path,
    *,
    title: str | None = None,
    markitdown_fn: Callable[[Path, Path], ConvertResult] = convert_with_markitdown,
    pdf_converter: _PdfConverter | None = None,
) -> tuple[ConvertResult, Source]:
    """Convert one file in ``raw/`` to markdown in ``extracts/`` and update state.

    ``markitdown_fn`` / ``pdf_converter`` are injectable so tests can stub the
    heavy ML converters without monkey-patching imports.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"input file does not exist: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"input is not a regular file: {input_path}")

    suffix = input_path.suffix.lower()
    category = _classify(suffix)  # raises if unsupported

    workspace.ensure_layout()

    content_hash = compute_content_hash(input_path)
    sources = SourcesIndex.load(workspace)

    paper_title = (title or input_path.stem).strip() or input_path.stem
    slug = stable_source_slug(paper_title, content_hash)
    extract_path = workspace.extracts_dir / f"{slug}.md"

    cached = sources.find_by_hash(content_hash)
    if cached is not None and extract_path.exists():
        # Idempotent re-ingest path — nothing to redo.
        result = _result_from_disk(extract_path, slug, category, workspace)
        return result, cached

    if category == "pdf":
        if pdf_converter is None:
            pdf_converter = MineruConverter()
        output_dir = workspace.extracts_dir / f"{slug}-mineru"
        raw_result = pdf_converter.convert(input_path, output_dir)
        # Promote MinerU's primary markdown to the canonical extract path.
        shutil.copyfile(raw_result.output_path, extract_path)
        result = ConvertResult(
            output_path=extract_path,
            format=raw_result.format,
            byte_count=raw_result.byte_count,
            markdown_excerpt=raw_result.markdown_excerpt,
            images_dir=raw_result.images_dir,
            blocks_json_path=raw_result.blocks_json_path,
            page_count=raw_result.page_count,
            duration_s=raw_result.duration_s,
        )
    else:
        result = markitdown_fn(input_path, extract_path)

    archived_path = workspace.raw_processed_dir / f"{slug}{suffix}"
    archived_path.parent.mkdir(parents=True, exist_ok=True)
    if input_path.resolve() != archived_path.resolve():
        shutil.copyfile(input_path, archived_path)

    source = Source(
        id=slug,
        title=paper_title,
        slug=slug,
        kind=category,
        sourcePath=archived_path.relative_to(workspace.root).as_posix(),
        contentHash=content_hash,
        ingestedAt=_utc_now_iso(),
        pageCount=result.page_count,
        extractPath=extract_path.relative_to(workspace.root).as_posix(),
        lastError="",
    )
    if sources.add_or_update(source):
        sources.save()

    WikiLog(workspace).append(
        "convert",
        paper_title,
        files_touched=[source.extractPath],
    )
    return result, source


def _result_from_disk(
    extract_path: Path, slug: str, category: str, workspace: Workspace
) -> ConvertResult:
    text = extract_path.read_text(encoding="utf-8")
    candidate_images = workspace.extracts_dir / f"{slug}-mineru" / "images"
    images_dir: Path | None = candidate_images if candidate_images.exists() else None
    blocks_json: Path | None = None
    if category == "pdf":
        candidates = sorted((workspace.extracts_dir / f"{slug}-mineru").rglob("*.json"))
        blocks_json = candidates[0] if candidates else None
    return ConvertResult(
        output_path=extract_path,
        format=category,
        byte_count=len(text.encode("utf-8")),
        markdown_excerpt=text[:200],
        images_dir=images_dir,
        blocks_json_path=blocks_json,
    )
