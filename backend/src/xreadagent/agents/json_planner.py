# SPDX-License-Identifier: AGPL-3.0-or-later
"""JSON-mode fallback planner used when tool-calling structured-output breaks.

Background: some Anthropic-compatible proxies (GLM-5.1 via a translation
shim, certain OpenAI gateways) emit ``IngestPlan`` / ``QueryAnswer`` payloads
where a nested ``list[BaseModel]`` field comes back as a JSON-encoded string
instead of a real list. Pydantic strict mode (rightly) refuses to coerce.

Rather than relax our schemas, we route around the misbehaving provider:
re-issue the request asking explicitly for raw JSON, then attempt three
repair passes (fence-strip, brace-extract, nested-string-list expand)
before validating the dict against the same Pydantic schema we always use.

The repair logic is intentionally conservative — we only fix the documented
failure modes; anything else still raises a ``ValidationError`` so we don't
mask real model bugs.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Protocol, TypeVar, get_args, get_origin

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class _Chat(Protocol):
    """Minimal subset of the LangChain chat-model interface we depend on.

    Kept here as a Protocol so tests can pass a fake without dragging
    LangChain types into ``__init__`` signatures.
    """

    def invoke(self, prompt: str) -> Any: ...


JsonPlanCallable = Callable[..., Any]
"""The callable shape ``make_json_planner`` returns.

Untyped at the generic-T level on purpose: each agent (ingest / query /
crystallize) calls it with its own schema and casts the result back to its
concrete Pydantic type. Mypy is happy because the body of ``_plan`` uses a
proper ``TypeVar``.
"""


def make_json_planner(chat: _Chat) -> JsonPlanCallable:
    """Build a planner callable that asks for raw JSON and repairs the response.

    Returned callable signature is ``(prompt, *, schema) -> schema_instance``,
    matching the ``IngestPlanner`` / ``QueryPlanner`` / ``CrystallizePlanner``
    Protocols.
    """

    def _plan(prompt: str, *, schema: type[T]) -> T:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        wrapped = (
            f"{prompt}\n\n"
            "## Response format\n\n"
            "Return ONLY a JSON object matching this schema. No prose, no "
            "markdown code fences, no leading or trailing text:\n\n"
            f"{schema_json}\n"
        )
        raw = chat.invoke(wrapped)
        text = _extract_text(raw)
        return parse_and_repair(text, schema)

    return _plan


def parse_and_repair(text: str, schema: type[T]) -> T:
    """Parse ``text`` as JSON and validate it against ``schema``.

    Repair passes, in order:

    1. Strip leading / trailing markdown code fences (``` or ```json).
    2. If the message has prose around the JSON, extract the outer
       ``{ ... }`` balanced block.
    3. Walk top-level fields and try ``json.loads`` on any whose schema
       declares ``list[SomeModel]`` but the value is a string. This is the
       documented GLM-via-proxy bug.

    Raises ``ValueError`` for unparseable JSON and ``ValidationError`` for
    schema mismatches the repair passes can't fix.
    """
    cleaned = _strip_fences(text).strip()
    if not cleaned:
        raise ValueError("empty response from JSON-mode planner")
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        extracted = _extract_balanced_object(cleaned)
        if extracted is None:
            raise ValueError(
                "JSON-mode planner returned non-JSON text we could not parse"
            ) from None
        data = json.loads(extracted)
    if not isinstance(data, dict):
        raise ValueError(
            f"JSON-mode planner returned a {type(data).__name__}, expected object"
        )
    try:
        return schema.model_validate(data)
    except ValidationError:
        repaired = _repair_nested_list_strings(data, schema)
        return schema.model_validate(repaired)


def _extract_text(raw: Any) -> str:
    """Pull the textual body out of whatever the chat model returned.

    LangChain ``invoke`` typically returns an ``AIMessage`` with a ``content``
    attribute that may be a string OR a list of content blocks. We handle
    both shapes plus the plain-string case some fakes use in tests.
    """
    if isinstance(raw, str):
        return raw
    content = getattr(raw, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if isinstance(block, dict):
                text_field = block.get("text")
                if isinstance(text_field, str):
                    parts.append(text_field)
        return "".join(parts)
    return str(raw)


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL | re.IGNORECASE)


def _strip_fences(text: str) -> str:
    match = _FENCE_RE.match(text.strip())
    if match is None:
        return text
    return match.group(1)


def _extract_balanced_object(text: str) -> str | None:
    """Find the first balanced ``{...}`` block in ``text`` and return it.

    Naive bracket counting — good enough for "LLM prefixed JSON with prose"
    and "LLM appended an apology". Aware of string literals so braces inside
    strings don't confuse the counter.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _repair_nested_list_strings(data: dict[str, Any], schema: type[T]) -> dict[str, Any]:
    """For fields typed ``list[BaseModel]`` whose value is a string, ``json.loads`` it.

    GLM-5.1 routed through Anthropic-format proxies has been observed to
    encode nested structured-output arrays as a single JSON string instead
    of a real list. Detect and unwrap.
    """
    fixed = dict(data)
    fields = schema.model_fields
    for name, field_info in fields.items():
        if name not in fixed:
            continue
        value = fixed[name]
        if not isinstance(value, str):
            continue
        annotation = field_info.annotation
        if not _is_list_of_basemodel(annotation):
            continue
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, list):
            fixed[name] = decoded
    return fixed


def _is_list_of_basemodel(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is not list:
        return False
    args = get_args(annotation)
    if not args:
        return False
    inner = args[0]
    try:
        return isinstance(inner, type) and issubclass(inner, BaseModel)
    except TypeError:
        return False


def is_nested_list_string_error(exc: ValidationError) -> bool:
    """Return True if ``exc`` looks like the GLM-via-proxy nested-list-as-string bug.

    Pydantic surfaces it as ``list_type`` on at least one error — a string
    was passed where a list was expected. Used by the ``"auto"`` planner to
    decide whether retrying with the JSON planner has any chance.
    """
    for err in exc.errors():
        if err.get("type") == "list_type":
            return True
    return False


__all__ = [
    "is_nested_list_string_error",
    "make_json_planner",
    "parse_and_repair",
]
