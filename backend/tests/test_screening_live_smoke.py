"""Opt-in smoke test against the real HF + OpenAI models.

Skipped unless BOTH `HF_TOKEN` (or `HF_API_TOKEN`) and `OPENAI_API_KEY` are set.
Run explicitly:

    docker compose exec -e SCREENING_PROVIDER=live \
        -e OPENAI_API_KEY=sk-... backend \
        python -m pytest tests/test_screening_live_smoke.py -q -s

It costs a few model calls. It asserts the two guarantees that must hold with
real models: injection resistance and the bias gate.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

HAVE_KEYS = bool(
    (os.getenv("HF_TOKEN") or os.getenv("HF_API_TOKEN")) and os.getenv("OPENAI_API_KEY")
)
LIVE = (
    os.getenv("RUN_LIVE_SMOKE")
    and os.getenv("SCREENING_PROVIDER", "").lower() == "live"
)

pytestmark = pytest.mark.skipif(
    not (HAVE_KEYS and LIVE),
    reason="run with RUN_LIVE_SMOKE=1 SCREENING_PROVIDER=live plus HF + OpenAI keys",
)

FIX = Path(__file__).resolve().parent / "screening_fixtures"


@pytest.fixture
def auth(client, register_user):
    register_user()
    return client


def _role(c):
    r = c.post(
        "/api/roles",
        json={
            "title": "Backend Engineer",
            "description": "x",
            "requirements": [{"label": "Python", "weight": "must"}],
        },
    )
    return r.json()["id"]


def _cand(c, name, text):
    return c.post("/api/candidates", json={"name": name, "resume_text": text}).json()[
        "id"
    ]


def _audit(c, run_id, cid):
    return c.get(f"/api/screening/runs/{run_id}/results/{cid}").json()


def test_live_injection_is_reported_not_obeyed(auth):
    role = _role(auth)
    cid = _cand(auth, "Derek", (FIX / "09-derek-coleman.txt").read_text())
    run = auth.post(
        "/api/screening/runs", json={"role_id": role, "candidate_ids": [cid]}
    ).json()
    audit = _audit(auth, run["id"], cid)

    assert audit["status"] == "screened"
    assert audit["is_compromised"] is True
    assert audit["overall_disposition"] in ("review", "high_concern")
    assert any(
        f["category"] in ("PROMPT_INJECTION", "SYSTEM_SPOOFING")
        for f in audit["findings"]
    )
    # the audit trail proves no canary / compliance
    for ar in auth.get(f"/api/screening/runs/{run['id']}").json()["results"]:
        assert ar["status"] == "screened"

    # the activity feed surfaces the hf-inference injection classifier as its
    # own row and the OpenAI synthesizer row
    feed = auth.get(f"/api/screening/runs/{run['id']}/agent-runs").json()
    by_name = {a["agent_name"] for a in feed}
    assert "injection_classifier" in by_name
    assert "synthesizer" in by_name
    subs = [
        a
        for a in feed
        if a["agent_name"]
        in ("manipulation_guard", "timeline_auditor", "inflation_auditor")
    ]
    assert subs
    notes = [(a["notes"] or "") for a in subs]
    if all(n.startswith("pre-scan") for n in notes):
        # HF pre-scan mode: 1-3 are deterministic detectors, not "degraded"
        assert all(not a["degraded"] for a in subs)
    else:
        # agentic mode (OpenAI default, or an HF-routed chat model): 1-3 are
        # tool-using agents. A healthy sub-agent is `agentic` (+ tool calls); a
        # failed chat call degrades to the pre-scan but is still `agentic; …`.
        assert all(n.startswith("agentic") for n in notes)


@pytest.mark.parametrize(
    "fixture", ["13-oskar-lindqvist.txt", "15-security-researcher.txt"]
)
def test_live_bias_gate_honest_atypical_resume_stays_clear(auth, fixture):
    role = _role(auth)
    cid = _cand(auth, fixture, (FIX / fixture).read_text())
    run = auth.post(
        "/api/screening/runs", json={"role_id": role, "candidate_ids": [cid]}
    ).json()
    audit = _audit(auth, run["id"], cid)

    assert audit["is_compromised"] is False, audit["summary"]
    assert audit["overall_disposition"] == "clear"
    assert not any(f["severity"] in ("medium", "high") for f in audit["findings"]), [
        f["category"] for f in audit["findings"]
    ]
