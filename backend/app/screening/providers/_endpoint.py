"""Per-tier LLM endpoint resolution.

The chat tiers (detection sub-agents 1–3 and synthesis Agents 4/5) each talk to
an OpenAI-compatible ``/chat/completions`` endpoint. Which one — vendor OpenAI,
Azure OpenAI, Ollama, vLLM, LM Studio, Groq, OpenRouter, together.ai,
llama.cpp, … — is chosen purely from the environment:

- ``OPENAI_BASE_URL`` / ``OPENAI_API_KEY`` — the shared default for both tiers.
- ``SCREENING_DETECTION_BASE_URL`` / ``SCREENING_DETECTION_API_KEY`` and
  ``SCREENING_SYNTHESIS_BASE_URL`` / ``SCREENING_SYNTHESIS_API_KEY`` — optional
  per-tier overrides, each falling back to the shared value.
- Model ids stay where they already were: ``OPENAI_SUBAGENT_MODEL`` (detection)
  and ``OPENAI_SYNTHESIS_MODEL`` (synthesis).

An **empty** env var is treated as unset (docker-compose passes blank values
through, and a stray empty ``OPENAI_BASE_URL`` otherwise makes the OpenAI SDK
build a schemeless URL and fail).
"""

from __future__ import annotations

from dataclasses import dataclass

_OPENAI_DEFAULT = "https://api.openai.com/v1"

_TIERS = {
    "detection": (
        "screening_detection_base_url",
        "screening_detection_api_key",
        "openai_subagent_model",
        "gpt-4.1-mini",
    ),
    "synthesis": (
        "screening_synthesis_base_url",
        "screening_synthesis_api_key",
        "openai_synthesis_model",
        "gpt-4.1",
    ),
}


@dataclass(frozen=True)
class ResolvedEndpoint:
    base_url: str  # always absolute, never ""
    api_key: str | None  # None when unset — the SDK wants None, not ""
    model: str


def _first(*vals: str, default: str = "") -> str:
    for v in vals:
        if v and v.strip():
            return v.strip()
    return default


def resolve_endpoint(settings, tier: str) -> ResolvedEndpoint:
    """Resolve ``(base_url, api_key, model)`` for ``tier`` in
    ``{"detection", "synthesis"}``. Empty-string settings are treated as unset."""
    try:
        per_url, per_key, model_field, model_default = _TIERS[tier]
    except KeyError:
        raise ValueError(f"unknown tier {tier!r}") from None

    def g(name: str) -> str:
        return getattr(settings, name, "") or ""

    return ResolvedEndpoint(
        base_url=_first(g(per_url), g("openai_base_url"), default=_OPENAI_DEFAULT),
        api_key=_first(g(per_key), g("openai_api_key")) or None,
        model=_first(g(model_field), default=model_default),
    )
