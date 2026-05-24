# SPDX-License-Identifier: AGPL-3.0-or-later
"""MinerU 3.x subprocess wrapper for PDF → markdown extraction.

We invoke the ``mineru`` CLI as a subprocess (per the discussion in
``research/pdf-pipeline.md`` and the BabelDOC isolation pattern in
``research/layout-translation.md``): heavy ML inference state is kept out of
the sidecar process and a malformed PDF that crashes MinerU cannot crash the
FastAPI worker.

MinerU itself is NOT a runtime dependency (it's a ~20 GB install). The user
opts in via Phase 3 packaging; ``MineruConverter.is_available()`` is True iff
the CLI is on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from xreadagent.pipeline.types import (
    MINERU_SUFFIXES,
    ConvertResult,
    MineruNotInstalledError,
    UnsupportedFormatError,
)

_INSTALL_HINT: Final[str] = (
    "MinerU is not on PATH. Install it per https://github.com/opendatalab/MinerU "
    "(`uv pip install mineru` or download the standalone bundle), then restart the sidecar."
)
_DEFAULT_LANG = "en"
_EXCERPT_LEN = 200


def _default_cli_args(input_path: Path, output_dir: Path, lang: str) -> list[str]:
    """Compose the standard `mineru` invocation for the pipeline backend.

    Flags per MinerU 3.x CLI docs: ``-p`` input, ``-o`` output dir, ``-b
    pipeline`` (the CPU-OK backend), ``-l`` language hint. See
    research/pdf-pipeline.md.
    """
    return [
        "-p",
        str(input_path),
        "-o",
        str(output_dir),
        "-b",
        "pipeline",
        "-l",
        lang,
    ]


class MineruConverter:
    """Subprocess wrapper around the MinerU 3.x CLI.

    The CLI binary defaults to ``mineru`` on PATH but a custom binary path can
    be injected for tests or for shipping a portable MinerU bundle.
    """

    def __init__(self, binary: str | Path = "mineru") -> None:
        self._binary = str(binary)

    def is_available(self) -> bool:
        """True iff ``mineru`` is resolvable as an executable."""
        return shutil.which(self._binary) is not None

    def convert(
        self,
        input_path: Path,
        output_dir: Path,
        *,
        lang: str = _DEFAULT_LANG,
        timeout_s: float = 600.0,
        progress: Callable[[str], None] | None = None,
        extra_args: Sequence[str] | None = None,
    ) -> ConvertResult:
        """Run MinerU on ``input_path`` and return the converted markdown.

        ``progress`` (if provided) is called with each line written to MinerU's
        stdout/stderr so a UI can show streaming logs.

        Raises:
            MineruNotInstalledError: if the CLI is missing.
            UnsupportedFormatError: if ``input_path`` is not a PDF.
            subprocess.TimeoutExpired: on hang.
            RuntimeError: if MinerU exits non-zero.
        """
        suffix = input_path.suffix.lower()
        if suffix not in MINERU_SUFFIXES:
            raise UnsupportedFormatError(
                f"MinerU only handles PDF; got {suffix!r} (route to markitdown instead)"
            )
        if not self.is_available():
            raise MineruNotInstalledError(_INSTALL_HINT)

        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [self._binary, *_default_cli_args(input_path, output_dir, lang)]
        if extra_args:
            cmd.extend(extra_args)

        start = time.monotonic()
        # ``Popen`` (not ``run``) so we can stream stdout to the progress
        # callback in real time. Combine stderr into stdout so a single reader
        # sees everything ordered.
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        ) as proc:
            assert proc.stdout is not None
            collected: list[str] = []
            try:
                for line in proc.stdout:
                    stripped = line.rstrip()
                    collected.append(stripped)
                    if progress is not None:
                        progress(stripped)
                rc = proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                raise

        if rc != 0:
            tail = "\n".join(collected[-20:])
            raise RuntimeError(
                f"mineru exited with code {rc}. Last log lines:\n{tail}"
            )

        duration = time.monotonic() - start
        return _read_mineru_output(input_path, output_dir, duration)


def _read_mineru_output(
    input_path: Path, output_dir: Path, duration: float
) -> ConvertResult:
    """Locate the markdown / images / blocks artifacts MinerU just wrote."""
    markdown_path = _find_markdown(output_dir, input_path.stem)
    if markdown_path is None:
        raise RuntimeError(
            f"MinerU completed but no markdown was found under {output_dir}"
        )

    markdown_text = markdown_path.read_text(encoding="utf-8")
    images_dir = _find_subdir(output_dir, "images")
    blocks_json = _find_blocks_json(output_dir)
    page_count = _read_page_count(blocks_json)

    return ConvertResult(
        output_path=markdown_path,
        format="pdf",
        byte_count=len(markdown_text.encode("utf-8")),
        markdown_excerpt=markdown_text[:_EXCERPT_LEN],
        images_dir=images_dir,
        blocks_json_path=blocks_json,
        page_count=page_count,
        duration_s=duration,
    )


def _find_markdown(output_dir: Path, stem: str) -> Path | None:
    candidates = sorted(output_dir.rglob("*.md"))
    if not candidates:
        return None
    # Prefer a file whose stem matches the input PDF stem; otherwise first.
    for candidate in candidates:
        if candidate.stem == stem:
            return candidate
    return candidates[0]


def _find_subdir(output_dir: Path, name: str) -> Path | None:
    for candidate in output_dir.rglob(name):
        if candidate.is_dir():
            return candidate
    return None


def _find_blocks_json(output_dir: Path) -> Path | None:
    for candidate in output_dir.rglob("*.json"):
        # MinerU writes a few JSONs; the ``content_list`` / ``middle`` ones
        # carry block info. Be permissive — caller can verify the schema.
        if candidate.is_file():
            return candidate
    return None


def _read_page_count(blocks_json: Path | None) -> int:
    if blocks_json is None or not blocks_json.exists():
        return 0
    try:
        data = json.loads(blocks_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(data, list):
        pages = {row.get("page_idx") for row in data if isinstance(row, dict)}
        pages.discard(None)
        return len(pages)
    if isinstance(data, dict):
        page_field = data.get("pageCount") or data.get("page_count")
        if isinstance(page_field, int):
            return page_field
    return 0
