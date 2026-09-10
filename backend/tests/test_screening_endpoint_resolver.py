"""`resolve_endpoint` — per-tier OpenAI-compatible endpoint resolution from
settings, with empty strings treated as unset and per-tier overrides winning
over the shared `openai_*` values."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.screening.providers._endpoint import resolve_endpoint

pytestmark = pytest.mark.no_db

_OPENAI_DEFAULT = "https://api.openai.com/v1"


def _settings(**over):
    base = dict(
        openai_api_key="",
        openai_base_url="",
        openai_subagent_model="gpt-4.1-mini",
        openai_synthesis_model="gpt-4.1",
        screening_detection_base_url="",
        screening_detection_api_key="",
        screening_synthesis_base_url="",
        screening_synthesis_api_key="",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_only_shared_key_set_uses_openai_defaults() -> None:
    ep = resolve_endpoint(_settings(openai_api_key="sk-shared"), "detection")
    assert ep.base_url == _OPENAI_DEFAULT
    assert ep.api_key == "sk-shared"
    assert ep.model == "gpt-4.1-mini"


def test_per_tier_base_url_beats_shared() -> None:
    ep = resolve_endpoint(
        _settings(
            openai_base_url="https://api.openai.com/v1",
            openai_api_key="sk-shared",
            screening_detection_base_url="http://ollama:11434/v1",
            screening_detection_api_key="ollama",
        ),
        "detection",
    )
    assert ep.base_url == "http://ollama:11434/v1"
    assert ep.api_key == "ollama"


def test_all_blank_or_whitespace_falls_back_to_openai_and_none_key() -> None:
    ep = resolve_endpoint(
        _settings(openai_api_key="   ", openai_base_url="  "), "synthesis"
    )
    assert ep.base_url == _OPENAI_DEFAULT
    assert ep.api_key is None


def test_synthesis_tier_picks_the_synthesis_model() -> None:
    ep = resolve_endpoint(_settings(openai_synthesis_model="llama3.1:8b"), "synthesis")
    assert ep.model == "llama3.1:8b"


def test_missing_settings_attrs_are_tolerated() -> None:
    # A bare namespace (what the provider unit tests pass) must not raise.
    ep = resolve_endpoint(SimpleNamespace(openai_api_key="k"), "detection")
    assert ep.base_url == _OPENAI_DEFAULT
    assert ep.api_key == "k"
    assert ep.model == "gpt-4.1-mini"


def test_unknown_tier_raises() -> None:
    with pytest.raises(ValueError):
        resolve_endpoint(_settings(), "translation")
