# SPDX-License-Identifier: AGPL-3.0-or-later
"""End-to-end ``convert_source`` router test with stubbed converters."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xreadagent.pipeline.router import convert_source
from xreadagent.pipeline.types import (
    ConvertResult,
    UnsupportedFormatError,
)
from xreadagent.wiki.sources import SourcesIndex
from xreadagent.wiki.workspace import Workspace


def _stub_markitdown(input_path: Path, output_path: Path) -> ConvertResult:
    """Copy the file's text content as "extracted" markdown."""
    content = f"# stubbed extract\n\nfrom {input_path.name}\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return ConvertResult(
        output_path=output_path,
        format=input_path.suffix.lstrip("."),
        byte_count=len(content.encode("utf-8")),
        markdown_excerpt=content[:200],
    )


class _StubPdfConverter:
    def convert(self, input_path: Path, output_dir: Path) -> ConvertResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / f"{input_path.stem}.md"
        md_path.write_text(f"# pdf stub\n\n{input_path.name}\n", encoding="utf-8")
        (output_dir / "images").mkdir(exist_ok=True)
        blocks_path = output_dir / "content_list.json"
        blocks_path.write_text(
            '[{"type":"text","page_idx":0},{"type":"text","page_idx":1}]',
            encoding="utf-8",
        )
        return ConvertResult(
            output_path=md_path,
            format="pdf",
            byte_count=md_path.stat().st_size,
            markdown_excerpt="# pdf stub",
            images_dir=output_dir / "images",
            blocks_json_path=blocks_path,
            page_count=2,
        )


def _drop_raw(workspace: Workspace, name: str, content: str) -> Path:
    path = workspace.raw_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_convert_source_with_html_writes_extract_and_updates_state(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    raw_html = _drop_raw(workspace, "intro.html", "<html><body>hi</body></html>")

    result, source = convert_source(
        workspace, raw_html, markitdown_fn=_stub_markitdown
    )

    # Extract was written.
    assert result.output_path.exists()
    assert result.output_path.parent == workspace.extracts_dir
    assert result.output_path.name == f"{source.slug}.md"

    # Manifest was updated.
    sources = SourcesIndex.load(workspace)
    assert sources.find_by_id(source.id) is not None
    assert sources.find_by_hash(source.contentHash) is not None
    assert source.kind == "office"

    # Archived copy lives under raw/_processed/.
    archived = workspace.raw_processed_dir / f"{source.slug}.html"
    assert archived.exists()

    # Wiki log got a "convert" entry.
    log_body = workspace.log_md_path.read_text(encoding="utf-8")
    assert "convert" in log_body
    assert source.title in log_body


def test_convert_source_is_idempotent(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    raw_html = _drop_raw(workspace, "intro.html", "<html><body>hi</body></html>")

    first_result, first_source = convert_source(
        workspace, raw_html, markitdown_fn=_stub_markitdown
    )
    first_mtime = first_result.output_path.stat().st_mtime_ns

    # Second call with unchanged content is a no-op for the extract file.
    second_result, second_source = convert_source(
        workspace, raw_html, markitdown_fn=_stub_markitdown
    )
    assert second_source.id == first_source.id
    assert second_source.contentHash == first_source.contentHash
    # Same extract file path, same content — re-write should not have occurred.
    second_mtime = second_result.output_path.stat().st_mtime_ns
    assert second_mtime == first_mtime


def test_convert_source_routes_pdf_to_pdf_converter(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    pdf_path = workspace.raw_dir / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 stubbed pdf bytes")

    result, source = convert_source(
        workspace,
        pdf_path,
        pdf_converter=_StubPdfConverter(),
    )

    assert source.kind == "pdf"
    assert source.pageCount == 2
    assert result.output_path == workspace.extracts_dir / f"{source.slug}.md"
    assert result.images_dir is not None
    assert result.blocks_json_path is not None

    sources = SourcesIndex.load(workspace)
    record = sources.find_by_id(source.id)
    assert record is not None
    assert record.pageCount == 2


def test_convert_source_rejects_unsupported_suffix(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    binary = workspace.raw_dir / "weird.bin"
    binary.write_bytes(b"\x00\x01\x02")
    with pytest.raises(UnsupportedFormatError):
        convert_source(workspace, binary, markitdown_fn=_stub_markitdown)


def test_convert_source_writes_iso_timestamp(tmp_path: Path) -> None:
    workspace = Workspace.at(tmp_path)
    workspace.init_empty("Test")
    raw_html = _drop_raw(workspace, "page.html", "<html></html>")
    _, source = convert_source(workspace, raw_html, markitdown_fn=_stub_markitdown)

    # ISO 8601 UTC with Z suffix.
    assert source.ingestedAt.endswith("Z")
    assert "T" in source.ingestedAt

    # Manifest on disk is valid JSON with the same row.
    payload = json.loads(workspace.sources_json_path.read_text(encoding="utf-8"))
    assert payload["sources"][0]["id"] == source.id
