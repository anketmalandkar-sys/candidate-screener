"""Shared helpers for turning an LLM into a validated schema object.

* ``strict_schema`` — a Pydantic model → a JSON Schema OpenAI Structured Outputs
  will accept (``additionalProperties: false`` everywhere, every property
  ``required``, no unsupported keywords).
* ``parse_json`` — tolerant extraction of the first JSON object from model text.
* ``run_ladder`` — call → validate → one repair call → give up (the caller then
  falls back to deterministic assembly). Never raises for a model failure.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_UNSUPPORTED_KEYS = {
    "title",
    "default",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "pattern",
    "format",
    "$comment",
}


def _strip(node):
    if isinstance(node, dict):
        node = {k: v for k, v in node.items() if k not in _UNSUPPORTED_KEYS}
        for k, v in list(node.items()):
            node[k] = _strip(v)
        if node.get("type") == "object" or "properties" in node:
            node["additionalProperties"] = False
            props = node.get("properties")
            if isinstance(props, dict):
                node["required"] = list(props.keys())
        return node
    if isinstance(node, list):
        return [_strip(v) for v in node]
    return node


def strict_schema(model_cls: type[BaseModel]) -> dict:
    """Kept as a utility for callers that want OpenAI Structured Outputs; the
    live synthesis path uses JSON mode instead, so today the only caller is
    ``tests/test_screening_live_providers.py`` (schema-compat check)."""
    return _strip(model_cls.model_json_schema())


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_json(raw: str) -> dict | None:
    if not raw:
        return None
    fenced = _FENCE_RE.search(raw)
    candidate = fenced.group(1) if fenced else raw
    # First balanced {...} span.
    start = candidate.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(candidate)):
        c = candidate[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(candidate[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


async def run_ladder(
    call: Callable[[str | None], Awaitable[str]],
    model_cls: type[T],
    *,
    max_repairs: int = 1,
) -> tuple[T | None, str, int]:
    """Returns (parsed_or_None, last_raw_text, repair_attempts)."""
    raw = await call(None)
    attempts = 0
    while True:
        data = parse_json(raw)
        if data is not None:
            try:
                return model_cls.model_validate(data), raw, attempts
            except ValidationError as exc:
                err = str(exc)[:800]
        else:
            err = "the response was not valid JSON matching the required schema"
        if attempts >= max_repairs:
            return None, raw, attempts
        attempts += 1
        raw = await call(
            "Your previous response could not be used: "
            f"{err}\nReturn ONLY a single JSON object that exactly matches the "
            "schema, with no commentary."
        )
