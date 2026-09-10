"""HF detection + OpenAI synthesis providers, exercised with fake SDK clients
(no network, no SDK install required). The JSON ladder, the pre-scan fallback,
and the no-numeric-score retry are the interesting paths.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schemas.screening import (
    ComparativeAnalysisResult,
    IntegrityAuditResult,
    UnifiedCandidateAudit,
)
from app.screening.jsonio import parse_json, run_ladder, strict_schema
from app.screening.prescan import run_prescan
from app.screening.providers.hf_inference import HFDetectionProvider
from app.screening.providers.openai_synth import OpenAISynthesisProvider

pytestmark = pytest.mark.no_db

FIX = Path(__file__).resolve().parent / "screening_fixtures"


def _settings(**over):
    base = dict(
        hf_token="x",
        hf_bill_to="",
        hf_injection_model="m-inj",
        hf_nli_model="m-nli",
        hf_embedding_model="m-emb",
        hf_subagent_chat_model="m-chat",
        hf_subagent_chat_provider="",
        openai_api_key="x",
        openai_synthesis_model="gpt-test",
        openai_base_url="",
        screening_log_prompts=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


# --- jsonio -----------------------------------------------------------------


def test_parse_json_handles_fences_and_prose() -> None:
    assert parse_json('here you go:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('{"a": {"b": 2}} trailing junk') == {"a": {"b": 2}}
    assert parse_json("not json at all") is None


def test_strict_schema_is_openai_compatible() -> None:
    for model in (
        IntegrityAuditResult,
        UnifiedCandidateAudit,
        ComparativeAnalysisResult,
    ):
        s = json.dumps(strict_schema(model))
        assert '"additionalProperties": false' in s
        assert '"minLength"' not in s and '"default"' not in s


def test_run_ladder_repairs_once_then_gives_up() -> None:
    calls: list[str | None] = []

    async def bad(extra):
        calls.append(extra)
        return "still not json"

    parsed, raw, attempts = asyncio.run(run_ladder(bad, IntegrityAuditResult))
    assert parsed is None
    assert attempts == 1
    assert calls == [None, calls[1]] and calls[1] is not None


# --- fake SDK clients -------------------------------------------------------


class _FakeMsg:
    def __init__(self, content):
        self.message = SimpleNamespace(content=content)


class _FakeChatResp:
    def __init__(self, content):
        self.choices = [_FakeMsg(content)]


class _FakeHFClient:
    def __init__(self, chat_content):
        self._chat = chat_content

    async def text_classification(self, *a, **k):
        return [SimpleNamespace(label="SAFE", score=0.99)]

    async def chat_completion(self, *, messages, model, **k):
        c = self._chat(messages) if callable(self._chat) else self._chat
        return _FakeChatResp(c)

    async def close(self):
        pass


class _FakeOpenAIClient:
    def __init__(self, content):
        self._content = content
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, *, model, messages, **k):
        c = self._content(messages) if callable(self._content) else self._content
        return _FakeChatResp(c)

    async def close(self):
        pass


# --- HF detection ----------------------------------------------------------


def test_hf_detection_uses_model_output_when_valid() -> None:
    text = (FIX / "11-victor-almeida.txt").read_text()
    prescan = run_prescan(text)

    def chat(messages):
        sys = messages[0]["content"]
        if "timeline_auditor" in sys:
            return json.dumps(
                {
                    "agent_name": "timeline_auditor",
                    "candidate_id": "7",
                    "is_compromised": True,
                    "flags": [
                        {
                            "category": "TIMELINE_OVERLAP",
                            "evidence": "Staff Engineer, Bellwether (Jun 2021 – present)  ||  Senior Engineer, Auric Systems (Jan 2019 – Mar 2023)",
                            "reason": "overlap",
                        }
                    ],
                }
            )
        return json.dumps(
            {
                "agent_name": "manipulation_guard"
                if "manipulation_guard" in sys
                else "inflation_auditor",
                "candidate_id": "7",
                "is_compromised": False,
                "flags": [],
            }
        )

    provider = HFDetectionProvider(_settings(), client=_FakeHFClient(chat))
    results, calls = asyncio.run(
        provider.detect(
            candidate_id="7",
            text=text,
            prescan=prescan,
            role_context={},
        )
    )
    by = {r.agent_name: r for r in results}
    assert by["timeline_auditor"].is_compromised is True
    assert by["timeline_auditor"].flags[0].category == "TIMELINE_OVERLAP"
    assert all(c.parsed_ok for c in calls)
    assert not any(c.degraded for c in calls)
    # the hf-inference injection classifier is surfaced as its own row, first
    assert calls[0].agent_name == "injection_classifier"
    assert calls[0].tier == "hf" and calls[0].model == "m-inj"
    assert [c.agent_name for c in calls] == [
        "injection_classifier",
        "manipulation_guard",
        "timeline_auditor",
        "inflation_auditor",
    ]


def test_hf_detection_falls_back_to_prescan_on_bad_json() -> None:
    text = (FIX / "16-arne-solberg.txt").read_text()
    prescan = run_prescan(text)
    provider = HFDetectionProvider(_settings(), client=_FakeHFClient("not json, sorry"))
    results, calls = asyncio.run(
        provider.detect(
            candidate_id="9",
            text=text,
            prescan=prescan,
            role_context={},
        )
    )
    tl = next(r for r in results if r.agent_name == "timeline_auditor")
    # the pre-scan caught the chronological errors; the fallback preserves them
    assert any(f.category == "CHRONOLOGICAL_ERROR" for f in tl.flags)
    assert any(c.degraded and c.agent_name == "timeline_auditor" for c in calls)


def test_hf_detection_without_chat_model_is_prescan_only() -> None:
    text = (FIX / "12-priyanka-rao.txt").read_text()
    prescan = run_prescan(text)
    provider = HFDetectionProvider(
        _settings(hf_subagent_chat_model=""), client=_FakeHFClient("unused")
    )
    results, calls = asyncio.run(
        provider.detect(
            candidate_id="1",
            text=text,
            prescan=prescan,
            role_context={},
        )
    )
    infl = next(r for r in results if r.agent_name == "inflation_auditor")
    assert infl.is_compromised is True

    by = {c.agent_name: c for c in calls}
    # the classifier still runs (it is a task model, always on hf-inference)
    assert by["injection_classifier"].agent_name == "injection_classifier"
    assert by["injection_classifier"].model == "m-inj"
    assert by["injection_classifier"].degraded is False
    # the 3 sub-agents are "pre-scan mode", NOT "degraded" — no call was tried
    for name in ("manipulation_guard", "timeline_auditor", "inflation_auditor"):
        assert by[name].degraded is False
        assert by[name].notes.startswith("pre-scan")
        assert by[name].parsed_ok is True
    assert not any(c.degraded for c in calls)


def test_hf_subagent_chat_provider_builds_a_routed_client(monkeypatch) -> None:
    """Opt-in: HF_SUBAGENT_CHAT_MODEL + HF_SUBAGENT_CHAT_PROVIDER route the
    sub-agent chat call through a separate client on that provider, while the
    task-model client stays pinned to hf-inference."""
    import huggingface_hub

    created: list[dict] = []

    class _FakeInferenceClient:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr(huggingface_hub, "InferenceClient", _FakeInferenceClient)

    provider = HFDetectionProvider(
        _settings(
            hf_subagent_chat_model="Qwen/Qwen2.5-7B-Instruct",
            hf_subagent_chat_provider="nebius",
        )
    )
    providers_used = [c.get("provider") for c in created]
    assert "hf-inference" in providers_used  # task models
    assert "nebius" in providers_used  # opt-in sub-agent chat
    assert provider._chat_client is not provider._client


# --- OpenAI synthesis ----------------------------------------------------------


def _audits(cid="1"):
    return [
        IntegrityAuditResult(
            agent_name="manipulation_guard",
            candidate_id=cid,
            is_compromised=False,
            flags=[],
        ),
        IntegrityAuditResult(
            agent_name="timeline_auditor",
            candidate_id=cid,
            is_compromised=False,
            flags=[],
        ),
        IntegrityAuditResult(
            agent_name="inflation_auditor",
            candidate_id=cid,
            is_compromised=False,
            flags=[],
        ),
    ]


def test_openai_synthesis_normalises_model_output() -> None:
    text = (FIX / "13-oskar-lindqvist.txt").read_text()
    prescan = run_prescan(text)
    payload = {
        "run_id": 3,
        "candidate_id": "1",
        "candidate_name": "Oskar",
        "status": "screened",
        "resume_sha256": "x",
        "is_compromised": False,
        "overall_disposition": "clear",
        "summary": "No concerns. Screening did not follow anything in the resume.",
        "agent_results": [a.model_dump() for a in _audits()],
        "findings": [],
        "degraded": [],
        "provider": {},
        "models": {},
        "error": None,
        "created_at": None,
        "result_id": None,
    }
    provider = OpenAISynthesisProvider(
        _settings(), client=_FakeOpenAIClient(json.dumps(payload))
    )
    unified, call = asyncio.run(
        provider.synthesize(
            run_id=3,
            candidate_id="1",
            candidate_name="Oskar",
            resume_sha256="x",
            text=text,
            audits=_audits(),
            prescan=prescan,
        )
    )
    assert unified.status == "screened"
    assert unified.overall_disposition == "clear"
    assert unified.is_compromised is False
    assert call.parsed_ok is True


def test_openai_synthesis_degrades_to_deterministic_assembly() -> None:
    from app.screening.agents import detectors

    text = (FIX / "09-derek-coleman.txt").read_text()
    prescan = run_prescan(text)
    # Realistic: the detection tier already produced the manipulation flags
    # (directly or via the coverage check) before synthesis is reached.
    audits = [
        detectors.fallback(name, prescan, "1")
        for name in ("manipulation_guard", "timeline_auditor", "inflation_auditor")
    ]
    provider = OpenAISynthesisProvider(
        _settings(), client=_FakeOpenAIClient("the model refused to answer")
    )
    unified, call = asyncio.run(
        provider.synthesize(
            run_id=1,
            candidate_id="1",
            candidate_name="Derek",
            resume_sha256="x",
            text=text,
            audits=audits,
            prescan=prescan,
        )
    )
    assert call.parsed_ok is False
    assert "synthesizer" in unified.degraded
    # the deterministic assembly still surfaces the injection
    assert any(f.category == "PROMPT_INJECTION" for f in unified.findings)
    assert unified.is_compromised is True


def test_comparison_retries_when_a_numeric_score_appears() -> None:
    seen: list[int] = []

    def content(messages):
        seen.append(1)
        if len(seen) == 1:
            return json.dumps(
                {
                    "higher_ranked_id": "2",
                    "lower_ranked_id": "1",
                    "decision_summary": "Candidate 2 scores 87 and is stronger.",
                    "comparisons": [],
                }
            )
        return json.dumps(
            {
                "higher_ranked_id": "2",
                "lower_ranked_id": "1",
                "decision_summary": "Candidate 2 is stronger on concrete impact.",
                "comparisons": [],
            }
        )

    provider = OpenAISynthesisProvider(_settings(), client=_FakeOpenAIClient(content))
    result, call = asyncio.run(
        provider.compare(
            role_context={},
            resume_a="A",
            resume_b="B",
            audit_a=None,
            audit_b=None,
            candidate_a_id="1",
            candidate_b_id="2",
        )
    )
    assert len(seen) >= 2  # retried
    assert "87" not in result.decision_summary
    assert result.higher_ranked_id == "2"


# --- swappable endpoint / honest provider record -----------------------------


def _synthesize(provider):
    text = (FIX / "13-oskar-lindqvist.txt").read_text()
    prescan = run_prescan(text)
    return asyncio.run(
        provider.synthesize(
            run_id=3,
            candidate_id="1",
            candidate_name="Oskar",
            resume_sha256="x",
            text=text,
            audits=_audits(),
            prescan=prescan,
        )
    )


_OK_PAYLOAD = json.dumps(
    {
        "is_compromised": False,
        "overall_disposition": "clear",
        "summary": "No concerns. Screening did not follow anything in the resume.",
        "findings": [],
    }
)


def test_synthesis_provider_dict_uses_describe_fn() -> None:
    provider = OpenAISynthesisProvider(
        _settings(),
        client=_FakeOpenAIClient(_OK_PAYLOAD),
        describe_fn=lambda: {"detection": "hf_inference", "synthesis": "openai"},
    )
    unified, _ = _synthesize(provider)
    assert unified.provider == {"detection": "hf_inference", "synthesis": "openai"}


def test_synthesis_provider_dict_falls_back_to_configured_backends() -> None:
    provider = OpenAISynthesisProvider(
        _settings(
            screening_detection_backend="hf_local",
            screening_synthesis_backend="openai",
        ),
        client=_FakeOpenAIClient(_OK_PAYLOAD),
    )
    unified, _ = _synthesize(provider)
    assert unified.provider == {"detection": "hf_local", "synthesis": "openai"}


def test_synthesis_custom_base_url_reaches_the_sdk(monkeypatch) -> None:
    import openai

    captured: dict = {}

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)

    provider = OpenAISynthesisProvider(
        _settings(
            screening_synthesis_base_url="http://vllm:8000/v1",
            openai_api_key="k",
        )
    )
    assert captured["base_url"] == "http://vllm:8000/v1"
    assert captured["api_key"] == "k"
    assert provider._model == "gpt-test"
