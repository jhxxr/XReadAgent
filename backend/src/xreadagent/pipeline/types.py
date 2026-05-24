# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared pipeline types — converter results, exceptions, suffix routing rules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

# Per plan.md §4, markitdown is only the right tool for office / web formats.
# PDFs go to MinerU because markitdown's pdfminer path drops equations, breaks
# 2-column reading order, and silently truncates text after inline images (see
# research/pdf-pipeline.md for the GH issue list).
MARKITDOWN_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".docx", ".pptx", ".xlsx", ".html", ".htm", ".epub", ".md", ".txt"}
)
MINERU_SUFFIXES: Final[frozenset[str]] = frozenset({".pdf"})


@dataclass(frozen=True)
class ConvertResult:
    """Result of a document → markdown conversion.

    ``images_dir`` / ``blocks_json_path`` are only populated by the MinerU
    pipeline; the markitdown converter leaves them ``None``.
    """

    output_path: Path
    format: str
    byte_count: int
    markdown_excerpt: str
    images_dir: Path | None = None
    blocks_json_path: Path | None = None
    page_count: int = 0
    duration_s: float = 0.0


class PipelineError(Exception):
    """Base error raised by pipeline converters."""


class UnsupportedFormatError(PipelineError):
    """The file's suffix is not handled by any registered converter."""


class WrongConverterError(PipelineError):
    """The wrong converter was invoked for this file's suffix (routing bug)."""


class MineruNotInstalledError(PipelineError):
    """MinerU CLI is not on PATH — guides the user to install it."""
