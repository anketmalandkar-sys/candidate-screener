"""`CompositeProvider` backend dispatch — the name->builder registry, the
no-key fallback for `openai_agentic`, and graceful degradation on an unknown
backend name. No network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.screening.providers.composite import CompositeProvider
from app.screening.providers.hf_inference import HFDetectionProvider

pytestmark = pytest.mark.no_db


def _settings(**over):
    base = dict(
        screening_detection_backend="stub",
        screening_synthesis_backend="stub",
        screening_is_live=True,
        openai_api_key="",
        openai_base_url="",
        openai_subagent_model="gpt-4.1-mini",
        openai_synthesis_model="gpt-4.1",
        screening_detection_base_url="",
        screening_detection_api_key="",
        screening_synthesis_base_url="",
        screening_synthesis_api_key="",
        hf_token="",
        hf_bill_to="",
        hf_injection_model="m-inj",
        hf_subagent_chat_model="",
        hf_subagent_chat_provider="",
        screening_log_prompts=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _composite(**over):
    # stub/stub keeps __init__ side-effect free; builders are exercised directly.
    return CompositeProvider(_settings(**over))


def test_registry_covers_the_documented_backends() -> None:
    assert set(CompositeProvider._DETECTION_BUILDERS) == {
        "openai_agentic",
        "hf_inference",
        "hf_local",
        "stub",
    }
    assert set(CompositeProvider._SYNTHESIS_BUILDERS) == {"openai", "stub"}


def test_openai_agentic_without_a_key_falls_back_to_hf() -> None:
    c = _composite()
    provider = c._det_openai_agentic(_settings(openai_api_key=""))
    assert isinstance(provider, HFDetectionProvider)


def test_openai_agentic_with_a_key_builds_the_openai_provider(monkeypatch) -> None:
    import openai

    captured: dict = {}

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)

    from app.screening.providers.openai_detection import (
        OpenAIAgenticDetectionProvider,
    )

    c = _composite()
    provider = c._det_openai_agentic(
        _settings(
            screening_detection_base_url="http://ollama:11434/v1",
            screening_detection_api_key="ollama",
        )
    )
    assert isinstance(provider, OpenAIAgenticDetectionProvider)
    assert captured["base_url"] == "http://ollama:11434/v1"
    assert captured["api_key"] == "ollama"


def test_unknown_detection_backend_degrades_to_stub(caplog) -> None:
    c = _composite()
    with caplog.at_level("WARNING"):
        provider = c._build_detection(_settings(screening_detection_backend="bogus"))
    assert provider is c._stub
    assert "bogus" in caplog.text


def test_describe_picks_one_key_per_tier() -> None:
    c = _composite()  # stub detection + stub synthesis
    assert c.describe() == {"detection": "stub", "synthesis": "stub"}
