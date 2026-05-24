# SPDX-License-Identifier: AGPL-3.0-or-later
"""markitdown converter routing + integration tests.

The lightweight ``.html`` test is the only ``markitdown.convert`` call we make
during the regular test run — it avoids docx/xlsx optional deps and the slow
magika ONNX model preload that triggers when ``MarkItDown()`` is instantiated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xreadagent.pipeline.markitdown_converter import convert_with_markitdown
from xreadagent.pipeline.types import (
    UnsupportedFormatError,
    WrongConverterError,
)


def test_markitdown_rejects_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    out = tmp_path / "paper.md"
    with pytest.raises(WrongConverterError):
        convert_with_markitdown(pdf, out)


def test_markitdown_rejects_unknown_suffix(tmp_path: Path) -> None:
    weird = tmp_path / "weird.foo"
    weird.write_text("nothing", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        convert_with_markitdown(weird, tmp_path / "out.md")


def test_markitdown_converts_html(tmp_path: Path) -> None:
    html = tmp_path / "doc.html"
    html.write_text(
        "<html><body><h1>Hello</h1><p>World</p></body></html>",
        encoding="utf-8",
    )
    out = tmp_path / "doc.md"
    result = convert_with_markitdown(html, out)

    body = out.read_text(encoding="utf-8")
    assert "Hello" in body
    assert "World" in body
    assert result.format == "html"
    assert result.byte_count > 0
    assert result.markdown_excerpt
