"""The agentic detection loop in `HFDetectionProvider` — sub-agents 1–3 call the
deterministic checks as tools, then return the IntegrityAuditResult. Exercised
with fake HF clients (no network).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.screening.prescan import run_prescan
from app.screening.providers.hf_inference import HFDetectionProvider

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
        hf_token="x",
        hf_bill_to="",
        hf_injection_model="m-inj",
        hf_nli_model="m-nli",
        hf_embedding_model="m-emb",
        hf_subagent_chat_model="m-chat",
        hf_subagent_chat_provider="",
        hf_subagent_max_tool_steps=4,
        screening_log_prompts=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _resp(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _agent_of(messages) -> str:
    sys = messages[0]["content"]
    for name in _SUBAGENTS:
        if name in sys:
            return name
    raise AssertionError("no agent in system prompt")


class _ToolThenAnswer:
    """`chat_completion`: ask for one tool call, then (once a tool result is in
    the transcript) return the IntegrityAuditResult JSON."""

    def __init__(self, *, bad_final=False, always_tool=False):
        self.calls: list[dict] = []
        self.bad_final = bad_final
        self.always_tool = always_tool

    async def text_classification(self, *a, **k):
        return [SimpleNamespace(label="SAFE", score=0.98)]

    async def chat_completion(self, *, messages, model, **k):
        self.calls.append({"tools": k.get("tools"), "n_messages": len(messages)})
        agent = _agent_of(messages)
        tools_offered = bool(k.get("tools"))
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        if tools_offered and (self.always_tool or not has_tool_result):
            tc = SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(name=_TOOL_FOR[agent], arguments="{}"),
            )
            return _resp(SimpleNamespace(content="", tool_calls=[tc]))
        content = (
            "not json at all"
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
        return _resp(SimpleNamespace(content=content, tool_calls=None))

    async def close(self):
        pass


def _detect(fake, fixture="11-victor-almeida.txt", **settings_over):
    text = (FIX / fixture).read_text()
    prescan = run_prescan(text)
    provider = HFDetectionProvider(_settings(**settings_over), client=fake)
    return asyncio.run(
        provider.detect(
            candidate_id="1",
            text=text,
            prescan=prescan,
            role_context={},
        )
    )


def test_agentic_detection_calls_a_tool_then_answers() -> None:
    fake = _ToolThenAnswer()
    results, calls = _detect(fake)

    subs = [c for c in calls if c.agent_name in _SUBAGENTS]
    assert len(subs) == 3
    assert {r.agent_name for r in results} == set(_SUBAGENTS)
    for c in subs:
        assert c.tier == "hf" and c.model == "m-chat"
        assert c.parsed_ok and not c.degraded
        assert c.notes.startswith("agentic")
        assert c.tool_calls and c.tool_calls[0]["name"] == _TOOL_FOR[c.agent_name]
        assert "result_summary" in c.tool_calls[0]
        assert "--- tool calls ---" in c.prompt_text
    # the injection-classifier backstop row is still there, first
    assert calls[0].agent_name == "injection_classifier"


def test_agentic_detection_falls_back_to_prescan_on_bad_final_json() -> None:
    fake = _ToolThenAnswer(bad_final=True)
    results, calls = _detect(fake, fixture="16-arne-solberg.txt")

    subs = [c for c in calls if c.agent_name in _SUBAGENTS]
    assert len(subs) == 3
    for c in subs:
        assert c.degraded is True
        assert "json_ladder_exhausted" in c.notes
    # the candidate is never dropped — the timeline pre-scan still surfaces
    tl = next(r for r in results if r.agent_name == "timeline_auditor")
    assert any(f.category == "CHRONOLOGICAL_ERROR" for f in tl.flags)


def test_agentic_detection_respects_max_tool_steps() -> None:
    fake = _ToolThenAnswer(always_tool=True)
    results, calls = _detect(fake, hf_subagent_max_tool_steps=2)

    subs = [c for c in calls if c.agent_name in _SUBAGENTS]
    # 2 tool rounds per agent, then a forced answer with tools disabled
    for c in subs:
        assert len(c.tool_calls) == 2
        assert c.parsed_ok and not c.degraded
    assert any(cc["tools"] for cc in fake.calls)
    assert any(not cc["tools"] for cc in fake.calls)


def test_agentic_detection_retries_without_tools_when_provider_rejects_them() -> None:
    class _RejectsTools:
        async def text_classification(self, *a, **k):
            return [SimpleNamespace(label="SAFE", score=0.9)]

        async def chat_completion(self, *, messages, model, **k):
            if k.get("tools"):
                raise TypeError("unexpected keyword argument 'tools'")
            agent = _agent_of(messages)
            return _resp(
                SimpleNamespace(
                    content=json.dumps(
                        {
                            "agent_name": agent,
                            "candidate_id": "1",
                            "is_compromised": False,
                            "flags": [],
                        }
                    ),
                    tool_calls=None,
                )
            )

        async def close(self):
            pass

    results, calls = _detect(_RejectsTools())
    subs = [c for c in calls if c.agent_name in _SUBAGENTS]
    assert len(subs) == 3
    for c in subs:
        assert c.parsed_ok and not c.degraded
        assert "tools unsupported by provider" in (c.notes or "")
        assert c.tool_calls == []


def test_agentic_detection_degrades_to_prescan_when_chat_model_unavailable() -> None:
    """A wrong model/provider pair, auth failure, or depleted HF credits must
    NOT drop the candidate — each sub-agent falls back to the deterministic
    pre-scan, marked degraded, and Agent 4 still runs."""

    class _BadProviderPair:
        async def text_classification(self, *a, **k):
            return [SimpleNamespace(label="SAFE", score=0.9)]

        async def chat_completion(self, *, messages, model, **k):
            raise ValueError(
                "402 Client Error: You have depleted your monthly included credits."
            )

        async def close(self):
            pass

    results, calls = _detect(_BadProviderPair(), fixture="16-arne-solberg.txt")
    subs = [c for c in calls if c.agent_name in _SUBAGENTS]
    assert len(subs) == 3
    for c in subs:
        assert c.degraded is True
        assert "chat model unavailable" in (c.notes or "")
        assert c.tool_calls == []
    # candidate still fully screened — the timeline pre-scan still surfaces
    tl = next(r for r in results if r.agent_name == "timeline_auditor")
    assert any(f.category == "CHRONOLOGICAL_ERROR" for f in tl.flags)
