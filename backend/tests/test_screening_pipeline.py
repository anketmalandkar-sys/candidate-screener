"""The screening pipeline below the HTTP / DB layer: the stub provider, the
verifier, deterministic assembly, and the coordinator's per-candidate function.

Pure logic — no database.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.schemas.screening import (
    EnrichedFinding,
    IntegrityAuditResult,
    IntegrityFlag,
)
from app.screening.assembly import disposition_for
from app.screening.coordinator import _screen_one
from app.screening.prescan import run_prescan
from app.screening.providers.stub import StubProvider
from app.screening.verifier import coverage_check, scan_for_canary, verify_audit

pytestmark = pytest.mark.no_db

FIXTURES = Path(__file__).resolve().parent / "screening_fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def _run(name: str, *, provider=None):
    provider = provider or StubProvider()
    return asyncio.run(
        _screen_one(
            provider,
            {"title": "Backend Engineer", "requirements": []},
            run_id=1,
            candidate_id=42,
            candidate_name="Test",
            text=_read(name),
            resume_sha256="deadbeef",
        )
    )


# --- happy path per fixture ------------------------------------------------------


def test_stub_pipeline_produces_one_unified_audit_per_candidate() -> None:
    unified, calls, error = _run("11-victor-almeida.txt")
    assert error is None
    assert unified is not None
    assert unified.status == "screened"
    assert unified.candidate_id == "42"
    # one detect call per sub-agent + one synthesizer call
    names = sorted(c.agent_name for c in calls)
    assert names == [
        "inflation_auditor",
        "manipulation_guard",
        "synthesizer",
        "timeline_auditor",
    ]


def test_injection_fixture_is_compromised_and_not_clear() -> None:
    unified, _calls, error = _run("09-derek-coleman.txt")
    assert error is None
    assert unified.is_compromised is True
    assert unified.overall_disposition in ("review", "high_concern")
    assert any(f.category == "PROMPT_INJECTION" for f in unified.findings)


def test_no_canary_token_in_any_stub_output() -> None:
    _unified, calls, _error = _run("09-derek-coleman.txt")
    assert scan_for_canary([c.raw_response for c in calls]) == []


def test_clean_fixture_13_disposition_clear() -> None:
    unified, _calls, error = _run("13-oskar-lindqvist.txt")
    assert error is None
    assert unified.is_compromised is False
    assert unified.overall_disposition == "clear"
    assert unified.findings == []


# --- disposition rule ---------------------------------------------------------


@pytest.mark.parametrize(
    "severities, expected",
    [
        ([], "clear"),
        (["info"], "clear"),
        (["low", "info"], "clear"),
        (["medium", "low"], "review"),
        (["high", "medium"], "high_concern"),
    ],
)
def test_disposition_for(severities, expected) -> None:
    findings = [
        EnrichedFinding(
            category="TIMELINE_OVERLAP",
            evidence="x",
            reason="y",
            source="timeline_auditor",
            severity=s,
        )
        for s in severities
    ]
    assert disposition_for(findings) == expected


# --- verifier ----------------------------------------------------------------


def test_verifier_drops_a_fabricated_quote() -> None:
    audit = IntegrityAuditResult(
        agent_name="timeline_auditor",
        candidate_id="1",
        is_compromised=True,
        flags=[
            IntegrityFlag(
                category="TIMELINE_OVERLAP",
                evidence="Chief Astronaut, NASA (1999 – 2010)",
                reason="fabricated",
            )
        ],
    )
    cleaned, notes = verify_audit(audit, "a short resume about backend work")
    assert cleaned.flags == []
    assert notes and "evidence not found" in notes[0]


def test_verifier_keeps_a_real_quote() -> None:
    text = "Senior Engineer, Auric Systems (Jan 2019 – Mar 2023)\nBuilt things."
    audit = IntegrityAuditResult(
        agent_name="timeline_auditor",
        candidate_id="1",
        is_compromised=True,
        flags=[
            IntegrityFlag(
                category="TIMELINE_OVERLAP",
                evidence="Senior Engineer, Auric Systems (Jan 2019 – Mar 2023)",
                reason="real",
            )
        ],
    )
    cleaned, notes = verify_audit(audit, text)
    assert len(cleaned.flags) == 1
    assert notes == []


def test_coverage_check_synthesises_a_missed_injection() -> None:
    prescan = run_prescan(_read("09-derek-coleman.txt"))
    # A manipulation_guard result that saw nothing — simulate the LLM missing it.
    silent = IntegrityAuditResult(
        agent_name="manipulation_guard",
        candidate_id="1",
        is_compromised=False,
        flags=[],
    )
    audits, notes = coverage_check(prescan, [silent])
    manip = next(a for a in audits if a.agent_name == "manipulation_guard")
    assert manip.is_compromised is True
    assert manip.flags  # synthesised back in
    assert any("LLM_MISSED_INJECTION" in n for n in notes)


# --- never silently drop / never crash ------------------------------------------


class _RaisingProvider(StubProvider):
    async def detect(self, **kwargs):
        raise RuntimeError("model exploded")


def test_a_provider_failure_is_recorded_not_raised() -> None:
    unified, calls, error = _run("11-victor-almeida.txt", provider=_RaisingProvider())
    assert unified is None
    assert error is not None and "screening did not complete" in error


class _CanaryProvider(StubProvider):
    async def synthesize(self, **kwargs):
        unified, call = await super().synthesize(**kwargs)
        call.raw_response = call.raw_response + " ⟬CANARY-7Q2⟭"
        return unified, call


def test_canary_in_output_forces_compromised_and_a_high_finding() -> None:
    unified, _calls, error = _run(
        "01-priya-nair.txt".replace("01-priya-nair.txt", "13-oskar-lindqvist.txt"),
        provider=_CanaryProvider(),
    )
    assert error is None
    assert unified.is_compromised is True
    assert any(
        f.severity == "high" and f.category == "PROMPT_INJECTION"
        for f in unified.findings
    )
    assert unified.overall_disposition == "high_concern"
