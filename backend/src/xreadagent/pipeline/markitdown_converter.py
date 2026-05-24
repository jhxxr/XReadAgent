# SPDX-License-Identifier: AGPL-3.0-or-later
"""markitdown wrapper — DOCX / PPTX / XLSX / HTML / EPUB / md / txt → markdown.

Per ``plan.md`` §4 and ``research/pdf-pipeline.md``, markitdown is the right
tool for office/web formats but the wrong tool for scientific PDFs. We enforce
that routing rule with an explicit ``WrongConverterError`` when a ``.pdf`` is
passed in — the caller is expected to use the MinerU converter for PDFs.

``markitdown`` is imported lazily so unit tests for unrelated modules don't pay
the ~30 s onnxruntime / magika cold-start tax.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from xreadagent.pipeline.types import (
    MARKITDOWN_SUFFIXES,
    MINERU_SUFFIXES,
    ConvertResult,
    UnsupportedFormatError,
    WrongConverterError,
)

_EXCERPT_LEN = 200


def _load_markitdown() -> Any:
    """Import + instantiate ``MarkItDown`` lazily."""
    from markitdown import MarkItDown  # noqa: PLC0415 — lazy on purpose

    return MarkItDown()


def convert_with_markitdown(input_path: Path, output_path: Path) -> ConvertResult:
    """Convert ``input_path`` to markdown at ``output_path`` via markitdown.

    Raises:
        WrongConverterError: if ``input_path`` is a PDF (route to MinerU).
        UnsupportedFormatError: if the suffix is not in ``MARKITDOWN_SUFFIXES``.
    """
    suffix = input_path.suffix.lower()
    if suffix in MINERU_SUFFIXES:
        raise WrongConverterError(
            "PDFs must route to MinerU; see plan.md §4 — "
            "markitdown's pdfminer path drops equations and corrupts 2-column reading order."
        )
    if suffix not in MARKITDOWN_SUFFIXES:
        raise UnsupportedFormatError(
            f"markitdown converter does not handle {suffix!r}; "
            f"supported suffixes: {sorted(MARKITDOWN_SUFFIXES)}"
        )

    start = time.monotonic()
    converter = _load_markitdown()
    result = converter.convert(str(input_path))
    markdown = result.text_content or ""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    return ConvertResult(
        output_path=output_path,
        format=suffix.lstrip("."),
        byte_count=len(markdown.encode("utf-8")),
        markdown_excerpt=markdown[:_EXCERPT_LEN],
        duration_s=time.monotonic() - start,
    )
