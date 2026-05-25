# SPDX-License-Identifier: AGPL-3.0-or-later
"""``xreadagent translate`` subcommand — drives :class:`TranslationService`.

Mirrors ``ingest`` / ``query`` in shape:

- ``--workspace`` is required.
- ``--model provider:name`` resolves the LLM provider that BabelDOC's
  translator callable uses.
- ``--target``, ``--mono-only`` / ``--dual-only`` / ``--both`` control the
  output PDFs.
- All the proxy-compatibility flags from Phase 1 (``--header`` / ``--user-agent``
  / ``--max-tokens`` / ``--env-override``) are exposed via
  :mod:`xreadagent.cli.llm_flags` so the same incantation works across
  ingest / query / translate.

Output convention:

- Stage events stream to **stderr** (one per line, ``[xreadagent] ...``).
- Final result emits **stdout** in the standard ``key: value`` shape so
  downstream scripts can ``grep`` for ``mono_path:`` / ``dual_path:`` /
  ``cached:``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from xreadagent.cli.env import (
    ensure_provider_credentials,
    load_env_files,
    required_env_var_for_model,
)
from xreadagent.cli.llm_flags import (
    add_llm_runtime_flags,
    resolve_env_override,
    resolve_headers,
    resolve_max_tokens,
)
from xreadagent.cli.output import emit_many, error, progress
from xreadagent.translation.events import (
    ErrorEvent,
    FinishEvent,
    ModelDownloadEvent,
    StageEvent,
)
from xreadagent.translation.service import TranslationRequest, TranslationService
from xreadagent.wiki.workspace import Workspace


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "translate",
        help="Translate a PDF in place with BabelDOC layout preservation.",
        description=(
            "Run BabelDOC's layout-preserving translation on a PDF and write "
            "mono / dual PDFs under ``translations/`` in the workspace. "
            "Wiki + extracts are NOT touched."
        ),
    )
    parser.add_argument("source_path", type=Path)
    parser.add_argument(
        "--workspace",
        dest="workspace_path",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--model",
        type=str,
        default="anthropic:claude-sonnet-4-6",
        help="LangChain provider:model string used for the translator callable.",
    )
    parser.add_argument(
        "--target",
        dest="target_lang",
        type=str,
        default="zh",
        help="Target language code (default: zh = simplified Chinese).",
    )
    parser.add_argument(
        "--source",
        dest="source_lang",
        type=str,
        default="en",
        help="Source language code (default: en).",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--mono-only",
        dest="mono_only",
        action="store_true",
        help="Emit only the translated-text-only PDF (skip the dual).",
    )
    output_group.add_argument(
        "--dual-only",
        dest="dual_only",
        action="store_true",
        help="Emit only the dual side-by-side PDF (skip the mono).",
    )
    output_group.add_argument(
        "--both",
        dest="both",
        action="store_true",
        help="Emit both mono and dual PDFs (default).",
    )
    add_llm_runtime_flags(parser)
    parser.set_defaults(handler=run)


def _resolve_outputs(args: argparse.Namespace) -> tuple[bool, bool]:
    """Return ``(mono, dual)`` flags from the mutually exclusive group."""
    if bool(getattr(args, "mono_only", False)):
        return True, False
    if bool(getattr(args, "dual_only", False)):
        return False, True
    return True, True


def _emit_stage_event(event: StageEvent) -> None:
    parts: list[str] = [event.type, event.stage]
    if event.page is not None:
        parts.append(f"page={event.page}")
    if event.percent is not None:
        parts.append(f"{event.percent:.1f}%")
    progress(" ".join(parts))


def _emit_download_event(event: ModelDownloadEvent) -> None:
    parts: list[str] = [event.type, event.asset]
    bytes_done = event.bytes_downloaded
    bytes_total = event.bytes_total
    if bytes_done is not None and bytes_total is not None and bytes_total > 0:
        ratio = bytes_done / bytes_total * 100.0
        parts.append(f"{bytes_done}/{bytes_total} ({ratio:.1f}%)")
    elif bytes_done is not None:
        parts.append(f"{bytes_done}B")
    progress(" ".join(parts))


async def _drive_stream(
    service: TranslationService, job_id: str
) -> tuple[FinishEvent | None, ErrorEvent | None]:
    finish: FinishEvent | None = None
    err: ErrorEvent | None = None
    async for event in service.event_stream(job_id):
        if isinstance(event, StageEvent):
            _emit_stage_event(event)
        elif isinstance(event, ModelDownloadEvent):
            _emit_download_event(event)
        elif isinstance(event, FinishEvent):
            finish = event
        elif isinstance(event, ErrorEvent):
            err = event
            progress(f"error stage={event.stage} message={event.message}")
    return finish, err


def run(args: argparse.Namespace) -> int:
    source_path: Path = args.source_path
    workspace_path: Path = args.workspace_path
    model: str = args.model
    target_lang: str = args.target_lang
    source_lang: str = args.source_lang
    headers = resolve_headers(args)
    env_override = resolve_env_override(args)
    max_tokens = resolve_max_tokens(args)
    mono, dual = _resolve_outputs(args)

    if not source_path.exists():
        error(f"source file does not exist: {source_path}")
        return 1
    if not source_path.is_file():
        error(f"source path is not a regular file: {source_path}")
        return 1

    workspace = Workspace.at(workspace_path)
    if not workspace.is_initialized():
        error(
            f"workspace at {workspace.root} is not initialized; "
            "run 'xreadagent init' first"
        )
        return 1

    load_env_files(
        workspace.root / ".env.local",
        Path.cwd() / ".env.local",
        override=env_override,
    )

    try:
        ensure_provider_credentials(model)
    except (RuntimeError, ValueError) as exc:
        error(str(exc))
        return 1

    progress(f"translating {source_path.name} → {target_lang} via {model}")
    if headers:
        progress(f"custom headers: {sorted(headers)}")
    if env_override:
        progress(".env.local override enabled (winning over shell env)")
    if max_tokens is not None:
        progress(f"max_tokens = {max_tokens}")

    api_env_var = _provider_api_env(model)
    api_key = os.environ.get(api_env_var) if api_env_var else None

    request = TranslationRequest(
        source_path=source_path,
        model=model,
        target_lang=target_lang,
        source_lang=source_lang,
        mono=mono,
        dual=dual,
        api_key=api_key,
        default_headers=headers,
        max_tokens=max_tokens,
    )

    service = TranslationService(workspace)
    try:
        job_id = service.start_translation(request)
    except FileNotFoundError as exc:
        error(str(exc))
        return 1
    except ValueError as exc:
        error(str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        error(f"unexpected failure: {exc!r}")
        return 2

    progress(f"job_id = {job_id}")

    try:
        finish, err = asyncio.run(_drive_stream(service, job_id))
    except KeyboardInterrupt:
        service.cancel(job_id)
        error("interrupted")
        return 1
    except Exception as exc:  # noqa: BLE001
        error(f"event stream failed: {exc!r}")
        return 2

    if err is not None:
        emit_many(
            {
                "workspace": str(workspace.root),
                "job_id": job_id,
                "status": "error",
                "stage": err.stage or "(unknown)",
                "message": err.message,
            }
        )
        return 2
    if finish is None:
        error("translation stream ended without a finish event")
        return 2

    emit_many(
        {
            "workspace": str(workspace.root),
            "job_id": job_id,
            "status": "ok",
            "cached": "true" if finish.cached else "false",
            "mono_path": finish.mono_path or "(none)",
            "dual_path": finish.dual_path or "(none)",
            "duration_s": f"{finish.duration_s:.3f}",
        }
    )
    return 0


def _provider_api_env(model: str) -> str | None:
    """Map a provider prefix to the env var that holds its API key.

    Wraps :func:`xreadagent.cli.env.required_env_var_for_model` so we share
    the canonical provider table with ``ingest`` / ``query``. Returns
    ``None`` (instead of raising) on unknown providers so the CLI flow can
    proceed for cases where the user is using a provider that doesn't need
    an API key (e.g. Ollama) — :func:`ensure_provider_credentials` has
    already validated the provider by this point in :func:`run`.
    """
    try:
        return required_env_var_for_model(model)
    except ValueError:
        return None


__all__ = ["add_parser", "run"]
