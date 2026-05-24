# SPDX-License-Identifier: AGPL-3.0-or-later
"""MinerU subprocess wrapper tests.

We mock ``subprocess.Popen`` so the test runs in milliseconds and does not
require the (~20 GB) MinerU CLI to be installed. A real smoke test is gated
behind the ``mineru`` pytest marker for the user to opt into manually.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from xreadagent.pipeline.mineru_converter import MineruConverter
from xreadagent.pipeline.types import (
    MineruNotInstalledError,
    UnsupportedFormatError,
)


class _FakePopen:
    """Minimal ``Popen`` stand-in: streams a fixed log + writes the markdown."""

    def __init__(
        self,
        cmd: list[str],
        *,
        markdown_text: str,
        return_code: int = 0,
        log_lines: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        self.cmd = cmd
        self.returncode = return_code
        self._markdown_text = markdown_text
        self.stdout = iter(
            (log_lines or ["loading model...", "page 1/1 parsed", "writing markdown..."])
        )

        # Locate the ``-p`` (input) and ``-o`` (output) flags from the assembled cmd.
        try:
            input_path = Path(cmd[cmd.index("-p") + 1])
            output_dir = Path(cmd[cmd.index("-o") + 1])
        except (ValueError, IndexError) as exc:  # pragma: no cover — defensive
            raise AssertionError(f"unexpected mineru invocation: {cmd}") from exc

        output_dir.mkdir(parents=True, exist_ok=True)
        # Write the canonical MinerU layout: {stem}.md + images/ + content_list.json.
        (output_dir / f"{input_path.stem}.md").write_text(markdown_text, encoding="utf-8")
        (output_dir / "images").mkdir(exist_ok=True)
        (output_dir / "content_list.json").write_text(
            '[{"type":"text","page_idx":0,"text":"hi"}]',
            encoding="utf-8",
        )

    def __enter__(self) -> _FakePopen:
        return self

    def __exit__(self, *_args: Any) -> None:
        pass

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode


def test_is_available_false_when_binary_missing() -> None:
    converter = MineruConverter(binary="definitely-not-on-path-mineru-xyz")
    assert converter.is_available() is False


def test_convert_raises_when_mineru_missing(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")
    converter = MineruConverter(binary="definitely-not-on-path-mineru-xyz")
    with pytest.raises(MineruNotInstalledError):
        converter.convert(pdf, tmp_path / "out")


def test_convert_raises_on_non_pdf(tmp_path: Path) -> None:
    text = tmp_path / "doc.txt"
    text.write_text("hi", encoding="utf-8")
    converter = MineruConverter()
    with pytest.raises(UnsupportedFormatError):
        converter.convert(text, tmp_path / "out")


def test_convert_assembles_cli_args_and_streams_progress(tmp_path: Path) -> None:
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")
    output_dir = tmp_path / "out"

    received_progress: list[str] = []
    captured_cmd: list[str] = []

    def _fake_popen(cmd: list[str], **kwargs: Any) -> _FakePopen:
        captured_cmd.extend(cmd)
        return _FakePopen(cmd, markdown_text="# Title\n\nbody", **kwargs)

    with (
        patch(
            "xreadagent.pipeline.mineru_converter.subprocess.Popen",
            new=_fake_popen,
        ),
        patch(
            "xreadagent.pipeline.mineru_converter.shutil.which",
            return_value="/fake/bin/mineru",
        ),
    ):
        converter = MineruConverter()
        result = converter.convert(
            pdf,
            output_dir,
            progress=received_progress.append,
        )

    # Verify expected flags were on the command line.
    assert "-p" in captured_cmd and str(pdf) in captured_cmd
    assert "-o" in captured_cmd and str(output_dir) in captured_cmd
    assert "-b" in captured_cmd and "pipeline" in captured_cmd
    assert "-l" in captured_cmd and "en" in captured_cmd

    assert received_progress, "progress callback should fire for each stdout line"
    assert "# Title" in result.output_path.read_text(encoding="utf-8")
    assert result.format == "pdf"
    assert result.images_dir is not None
    assert result.blocks_json_path is not None
    assert result.page_count >= 1


def test_convert_raises_on_non_zero_exit(tmp_path: Path) -> None:
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")

    def _fake_popen(cmd: list[str], **kwargs: Any) -> _FakePopen:
        return _FakePopen(
            cmd,
            markdown_text="",
            return_code=1,
            log_lines=["error: malformed pdf"],
            **kwargs,
        )

    with (
        patch(
            "xreadagent.pipeline.mineru_converter.subprocess.Popen",
            new=_fake_popen,
        ),
        patch(
            "xreadagent.pipeline.mineru_converter.shutil.which",
            return_value="/fake/bin/mineru",
        ),
    ):
        converter = MineruConverter()
        with pytest.raises(RuntimeError, match="exited with code 1"):
            converter.convert(pdf, tmp_path / "out")


@pytest.mark.mineru
def test_mineru_smoke_real_install(tmp_path: Path) -> None:  # pragma: no cover
    """Opt-in: requires the real ``mineru`` CLI on PATH."""
    converter = MineruConverter()
    if not converter.is_available():
        pytest.skip("mineru CLI not installed")
    # Caller must drop a sample.pdf in the workspace for this to be useful.
    sample = Path(__file__).parent / "fixtures" / "sample.pdf"
    if not sample.exists():
        pytest.skip("no sample.pdf fixture provided")
    result = converter.convert(sample, tmp_path / "out", timeout_s=300)
    assert result.byte_count > 0
