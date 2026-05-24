# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pipeline package — document → markdown converters and ingest routing."""

from xreadagent.pipeline.markitdown_converter import convert_with_markitdown
from xreadagent.pipeline.mineru_converter import MineruConverter
from xreadagent.pipeline.router import convert_source
from xreadagent.pipeline.types import (
    MARKITDOWN_SUFFIXES,
    MINERU_SUFFIXES,
    ConvertResult,
    MineruNotInstalledError,
    PipelineError,
    UnsupportedFormatError,
    WrongConverterError,
)

__all__ = [
    "MARKITDOWN_SUFFIXES",
    "MINERU_SUFFIXES",
    "ConvertResult",
    "MineruConverter",
    "MineruNotInstalledError",
    "PipelineError",
    "UnsupportedFormatError",
    "WrongConverterError",
    "convert_source",
    "convert_with_markitdown",
]
