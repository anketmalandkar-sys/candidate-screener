"""`OpenAIAgenticDetectionProvider` — detection sub-agents 1–3 on OpenAI
(gpt-4.1-mini), the default backend. The injection-classifier row stays an HF
task model. Exercised with fake clients (no network)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.screening.prescan import run_prescan
from app.screening.providers.openai_detection import OpenAIAgenticDetectionProvider

pytestmark = pytest.mark.no_db

FIX = Path(__file__).resolve().parent / "screening_fixtures"
_SUBAGENTS = ("manipulation_guard", "timeline_auditor", "inflation_auditor")
_TOOL_FOR = {
    "manipulation_guard": "scan_manipulation_patterns",
    "timeline_auditor": "check_timeline_consistency",
    "inflation_auditor": "find_recycled_or_inflated_claims",
}


def _settings(**over):
    base = dict(
        openai_api_key="x",
        openai_subagent_model="gpt-4.1-mini",
        openai_base_url="",
        hf_token="x",
        hf_bill_to="",
        hf_injection_model="m-inj",
        hf_subagent_max_tool_steps=4,
        screening_log_prompts=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _agent_of(messages) -> str:
    sys = messages[0]["content"]
    return next(n for n in _SUBAGENTS if n in sys)


class _FakeHFTask:
    def text_classification(self, segment, model):  # sync — provider wraps in to_thread
        return [SimpleNamespace(label="SAFE", score=0.99)]

    def close(self):
        pass


class _FakeOpenAI:
    """`.chat.completions.create` — one tool call, then the JSON answer."""

    def __init__(self, *, bad_final=False):
        self.bad_final = bad_final
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, *, model, messages, **k):
        self.calls.append({"model": model, "tools": k.get("tools")})
        agent = _agent_of(messages)
        if k.get("tools") and not any(m.get("role") == "tool" for m in messages):
            tc = SimpleNamespace(
                id="call_1",
                type="function",
                function=SimpleNamespace(name=_TOOL_FOR[agent], arguments="{}"),
            )
            msg = SimpleNamespace(content="", tool_calls=[tc])
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])
        content = (
            "not json"
            if self.bad_final
            else json.dumps(
                {
                    "agent_name": agent,
                    "candidate_id": "1",
                    "is_compromised": False,
                    "flags": [],
                }
            )
        )
        msg = SimpleNamespace(content=content, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    async def close(self):
        pass


def _detect(provider, fixture="11-victor-almeida.txt"):
    text = (FIX / fixture).read_text()
    prescan = run_prescan(text)
    return asyncio.run(
        provider.detect(
            candidate_id="1",
            text=text,
            prescan=prescan,
            role_context={},
        )
    )


def test_subagents_run_on_openai_and_call_tools() -> None:
    provider = OpenAIAgenticDetectionProvider(
        _settings(), client=_FakeOpenAI(), hf_client=_FakeHFTask()
    )
    results, calls = _detect(provider)

    subs = [c for c in calls if c.agent_name in _SUBAGENTS]
    assert len(subs) == 3
    assert {r.agent_name for r in results} == set(_SUBAGENTS)
    for c in subs:
        assert c.tier == "openai"
        assert c.model == "gpt-4.1-mini"
        assert c.parsed_ok and not c.degraded
        assert c.notes.startswith("agentic")
        assert c.tool_calls and c.tool_calls[0]["name"] == _TOOL_FOR[c.agent_name]

    # the injection classifier row is still an HF task model
    cls = calls[0]
    assert cls.agent_name == "injection_classifier"
    assert cls.tier == "hf" and cls.model == "m-inj"
    assert cls.parsed_ok is True


def test_bad_final_json_degrades_that_subagent_to_prescan() -> None:
    provider = OpenAIAgenticDetectionProvider(
        _settings(), client=_FakeOpenAI(bad_final=True), hf_client=_FakeHFTask()
    )
    results, calls = _detect(provider, fixture="16-arne-solberg.txt")
    subs = [c for c in calls if c.agent_name in _SUBAGENTS]
    assert all(c.degraded and "json_ladder_exhausted" in c.notes for c in subs)
    tl = next(r for r in results if r.agent_name == "timeline_auditor")
    assert any(f.category == "CHRONOLOGICAL_ERROR" for f in tl.flags)


def test_custom_base_url_and_key_reach_the_sdk(monkeypatch) -> None:
    """A per-tier override points the detection chat tier at any
    OpenAI-compatible endpoint; an unset key reaches the SDK as None, not ""."""
    import openai

    captured: dict = {}

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)

    provider = OpenAIAgenticDetectionProvider(
        _settings(
            openai_api_key="",
            screening_detection_base_url="http://ollama:11434/v1",
            screening_detection_api_key="",
        ),
        hf_client=_FakeHFTask(),
    )
    assert captured["base_url"] == "http://ollama:11434/v1"
    assert captured["api_key"] is None
    assert provider._chat_model == "gpt-4.1-mini"


def test_without_hf_token_only_the_classifier_row_degrades() -> None:
    provider = OpenAIAgenticDetectionProvider(
        _settings(hf_token=""), client=_FakeOpenAI(), hf_client=None
    )
    results, calls = _detect(provider)

    cls = calls[0]
    assert cls.agent_name == "injection_classifier"
    assert cls.degraded is True  # no HF token → classifier unavailable
    subs = [c for c in calls if c.agent_name in _SUBAGENTS]
    assert len(subs) == 3
    assert all(c.tier == "openai" and c.parsed_ok and not c.degraded for c in subs)
