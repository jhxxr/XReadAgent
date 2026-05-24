# SPDX-License-Identifier: AGPL-3.0-or-later
"""Top-level query orchestrator: drives ``QueryAgent`` and writes the archive.

Plays the role of OpenSciReader's ``QueryWorkspaceKnowledge`` (Wails service
entry point). A typical caller is the FastAPI ``POST /api/query`` handler
(Phase 2 work).

D4 (``plan.md`` §11) is enforced here, not in the agent: the agent emits a
``QueryAnswer`` and the orchestrator persists it ONLY to
``wiki/queries/{topic}/{date}-{slug}.md`` + ``state/conversation-log.jsonl``.
We deliberately do NOT call ``write_index``, ``WikiLog.append``, or any
``papers/`` / ``concepts/`` writer.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from xreadagent.agents.query import QueryAgent, QueryResult
from xreadagent.agents.query_schema import QueryAnswer
from xreadagent.schemas.wiki_pages import QueryFrontmatter
from xreadagent.wiki.log import WikiConversationLog
from xreadagent.wiki.pages import write_query_page
from xreadagent.wiki.paths import kebab_slug
from xreadagent.wiki.workspace import Workspace

_DEFAULT_TOPIC = "general"
_MAX_SLUG_WORDS = 8
_MAX_SLUG_LEN = 60


def _today_utc_isoformat() -> str:
    # YYYY-MM-DD is enough — the slug carries any finer-grained disambiguation.
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _derive_topic(question: str) -> str:
    """Heuristic topic derivation when the caller doesn't supply one.

    Take the first two-or-three meaningful tokens of the question, kebab-cased.
    The orchestrator only uses this as a folder name; the agent / caller can
    override it explicitly via the ``topic`` arg.
    """
    words = [w for w in question.split() if w.strip()][:3]
    if not words:
        return _DEFAULT_TOPIC
    candidate = kebab_slug(" ".join(words))
    return candidate or _DEFAULT_TOPIC


def _derive_short_slug(question: str) -> str:
    """Build the per-question slug from the first ~8 words.

    Used as the filename body in ``queries/{topic}/{date}-{slug}.md``.
    """
    words = [w for w in question.split() if w.strip()][:_MAX_SLUG_WORDS]
    if not words:
        return "question"
    candidate = kebab_slug(" ".join(words))
    if not candidate:
        return "question"
    if len(candidate) > _MAX_SLUG_LEN:
        candidate = candidate[:_MAX_SLUG_LEN].rstrip("-") or "question"
    return candidate


def _build_query_frontmatter(answer: QueryAnswer, date: str) -> QueryFrontmatter:
    return QueryFrontmatter(
        question=answer.question or "(no question)",
        date=date,
        layers_used=list(answer.layers_used),
        sources_cited=list(answer.sources_cited),
    )


def _render_question_section(answer: QueryAnswer) -> str:
    return answer.question.strip() or "_(no question recorded)_"


def _render_answer_section(answer: QueryAnswer) -> str:
    body = answer.answer_markdown.strip()
    if not body:
        body = "_(no answer recorded)_"
    if answer.open_questions_raised:
        lines = [body, "", "### Open questions raised"]
        lines.extend(f"- {q.strip()}" for q in answer.open_questions_raised if q.strip())
        body = "\n".join(lines)
    if answer.notes:
        lines = [body, "", "### Notes"]
        lines.extend(f"- {n.strip()}" for n in answer.notes if n.strip())
        body = "\n".join(lines)
    return body


def _render_sources_section(answer: QueryAnswer) -> str:
    if not answer.evidence:
        cited = answer.sources_cited
        if not cited:
            return "_(no sources cited)_"
        return "\n".join(f"- [[{path}]]" for path in cited)
    lines: list[str] = []
    for piece in answer.evidence:
        path = piece.source_wiki_path.strip() or "(unknown)"
        quote = piece.quote.strip()
        confidence = piece.confidence
        if quote:
            lines.append(f"- [[{path}]] — _{confidence}_: {quote}")
        else:
            lines.append(f"- [[{path}]] — _{confidence}_")
    return "\n".join(lines)


async def answer_query(
    workspace: Workspace,
    question: str,
    *,
    agent: QueryAgent,
    topic: str | None = None,
) -> QueryResult:
    """Run ``agent.answer`` and archive the result under ``wiki/queries/...``.

    NEVER writes to ``wiki/papers/`` / ``wiki/concepts/`` / ``wiki/index.md`` /
    ``wiki/log.md`` — that promotion lives in ``/crystallize``.
    """
    start = time.monotonic()
    workspace.ensure_layout()

    outcome = await agent.answer(question, topic=topic)
    answer = outcome.answer

    resolved_topic = (topic or "").strip() or _derive_topic(question)
    topic_slug = kebab_slug(resolved_topic) or _DEFAULT_TOPIC
    date = _today_utc_isoformat()
    short_slug = _derive_short_slug(question)

    frontmatter = _build_query_frontmatter(answer, date)
    sections = {
        "Question": _render_question_section(answer),
        "Answer": _render_answer_section(answer),
        "Sources": _render_sources_section(answer),
    }
    page_path = write_query_page(
        workspace,
        topic_slug,
        date,
        short_slug,
        frontmatter,
        sections,
    )

    try:
        rel_path = page_path.relative_to(workspace.root).as_posix()
    except ValueError:
        rel_path = page_path.as_posix()

    # Conversation log is the audit substrate for queries. ``wiki/log.md``
    # stays untouched — that ledger is reserved for synthesis ops (ingest,
    # crystallize, lint).
    WikiConversationLog(workspace).append(
        {
            "event": "query",
            "question": answer.question,
            "topic": topic_slug,
            "archive_path": rel_path,
            "sources_cited": list(answer.sources_cited),
            "layers_used": list(answer.layers_used),
            "confidence": answer.confidence,
            "tokens_used": dict(outcome.tokens_used),
        }
    )

    return QueryResult(
        answer=answer,
        query_page_path=page_path,
        files_touched=[rel_path],
        tokens_used=dict(outcome.tokens_used),
        duration_s=time.monotonic() - start,
    )


__all__ = ["answer_query"]
