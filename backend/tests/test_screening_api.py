"""End-to-end screening API in `stub` mode (the default).

Needs the database. The background task that does the screening runs
synchronously after the POST response under `TestClient`, so by the time
`client.post("/api/screening/runs", ...)` returns the run is already complete.
"""

from __future__ import annotations

import pytest

FIXTURES = __import__("pathlib").Path(__file__).resolve().parent / "screening_fixtures"

CLEAN = "Backend engineer. Six years of Python and PostgreSQL. Ships with Docker."
INJECTION = (FIXTURES / "09-derek-coleman.txt").read_text()
OVERLAP = (FIXTURES / "11-victor-almeida.txt").read_text()


@pytest.fixture
def auth(client, register_user):
    register_user()
    return client


def _role(client) -> int:
    r = client.post(
        "/api/roles",
        json={
            "title": "Backend Engineer",
            "description": "Owns payments.",
            "requirements": [{"label": "Python", "weight": "must"}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _candidate(client, name: str, resume: str) -> int:
    r = client.post("/api/candidates", json={"name": name, "resume_text": resume})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _run(client, role_id: int, candidate_ids: list[int]):
    r = client.post(
        "/api/screening/runs",
        json={"role_id": role_id, "candidate_ids": candidate_ids},
    )
    return r


# --- happy path -----------------------------------------------------------------


def test_run_produces_one_result_per_candidate(auth):
    role = _role(auth)
    ids = [
        _candidate(auth, "Clean", CLEAN),
        _candidate(auth, "Derek", INJECTION),
        _candidate(auth, "Victor", OVERLAP),
    ]
    resp = _run(auth, role, ids)
    assert resp.status_code == 201, resp.text
    run = resp.json()
    assert run["counts"]["total"] == 3
    assert len(run["results"]) == 3

    detail = auth.get(f"/api/screening/runs/{run['id']}").json()
    assert detail["status"] == "complete"
    assert detail["counts"]["screened"] == 3
    assert detail["counts"]["errored"] == 0
    assert {r["candidate_id"] for r in detail["results"]} == {str(i) for i in ids}
    assert all(r["status"] == "screened" for r in detail["results"])


def test_injection_candidate_is_compromised_and_flagged(auth):
    role = _role(auth)
    cid = _candidate(auth, "Derek", INJECTION)
    run = _run(auth, role, [cid]).json()

    audit = auth.get(f"/api/screening/runs/{run['id']}/results/{cid}").json()
    assert audit["is_compromised"] is True
    assert audit["overall_disposition"] in ("review", "high_concern")
    cats = {f["category"] for f in audit["findings"]}
    assert "PROMPT_INJECTION" in cats
    assert audit["summary"]
    # the audit trail exists
    assert audit["agent_results"]


def test_clean_candidate_is_clear(auth):
    role = _role(auth)
    cid = _candidate(auth, "Clean", CLEAN)
    run = _run(auth, role, [cid]).json()
    audit = auth.get(f"/api/screening/runs/{run['id']}/results/{cid}").json()
    assert audit["is_compromised"] is False
    assert audit["overall_disposition"] == "clear"
    assert audit["findings"] == []


# --- never silently drop --------------------------------------------------------


def test_unknown_candidate_id_rejects_the_whole_request(auth):
    role = _role(auth)
    good = _candidate(auth, "Clean", CLEAN)
    before = auth.get("/api/screening/runs").json()["total"]

    resp = _run(auth, role, [good, 999_999])
    assert resp.status_code == 422
    assert "999999" in resp.text

    after = auth.get("/api/screening/runs").json()["total"]
    assert after == before  # nothing was created


def test_a_worker_failure_still_yields_a_row_per_candidate(auth, monkeypatch):
    """Force the provider to raise for every candidate; the run must finish
    `partial` with an `error` row for each — never a missing row."""
    from app.screening.providers.stub import StubProvider

    class _Boom(StubProvider):
        async def detect(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.screening.coordinator.get_provider", lambda settings: _Boom()
    )

    role = _role(auth)
    ids = [_candidate(auth, f"C{i}", CLEAN) for i in range(3)]
    run = _run(auth, role, ids).json()

    detail = auth.get(f"/api/screening/runs/{run['id']}").json()
    assert detail["status"] == "partial"
    assert len(detail["results"]) == 3
    assert all(r["status"] == "error" for r in detail["results"])
    for cid in ids:
        audit = auth.get(f"/api/screening/runs/{run['id']}/results/{cid}").json()
        assert audit["status"] == "error"
        assert audit["error"]


# --- determinism -------------------------------------------------------------


def test_stub_runs_are_deterministic(auth):
    role = _role(auth)
    cid = _candidate(auth, "Victor", OVERLAP)
    a = _run(auth, role, [cid]).json()
    b = _run(auth, role, [cid]).json()

    def _findings(run_id):
        j = auth.get(f"/api/screening/runs/{run_id}/results/{cid}").json()
        return sorted((f["category"], f["evidence"]) for f in j["findings"])

    assert _findings(a["id"]) == _findings(b["id"])


# --- agent activity --------------------------------------------------------


def test_agent_runs_are_recorded_per_run_and_per_candidate(auth):
    role = _role(auth)
    ids = [_candidate(auth, f"C{i}", OVERLAP) for i in range(3)]
    run = _run(auth, role, ids).json()

    run_wide = auth.get(f"/api/screening/runs/{run['id']}/agent-runs").json()
    # 3 candidates × (3 detectors + 1 synthesizer)
    assert len(run_wide) == 12
    assert {r["agent_name"] for r in run_wide} == {
        "manipulation_guard",
        "timeline_auditor",
        "inflation_auditor",
        "synthesizer",
    }
    assert all(r["candidate_name"] and r["candidate_id"] for r in run_wide)
    # the run-wide feed is metadata only — no big text
    assert all("prompt_text" not in r for r in run_wide)

    per_cand = auth.get(
        f"/api/screening/runs/{run['id']}/results/{ids[0]}/agent-runs"
    ).json()
    assert len(per_cand) == 4
    assert all(r["prompt_text"] and r["raw_response"] for r in per_cand)


def test_run_counts_reflect_the_result_rows(auth):
    role = _role(auth)
    ids = [_candidate(auth, "Clean", CLEAN), _candidate(auth, "Victor", OVERLAP)]
    run = _run(auth, role, ids).json()
    detail = auth.get(f"/api/screening/runs/{run['id']}").json()
    assert detail["counts"]["screened"] == 2
    assert detail["counts"]["errored"] == 0
    assert detail["counts"]["compromised"] == 1  # Victor's timeline overlap


# --- tenant isolation --------------------------------------------------------


def test_other_users_run_is_404(client, register_user):
    register_user()
    role = _role(client)
    cid = _candidate(client, "Clean", CLEAN)
    run = _run(client, role, [cid]).json()
    client.post("/api/auth/logout")

    register_user()  # a second recruiter
    assert client.get(f"/api/screening/runs/{run['id']}").status_code == 404
    assert (
        client.get(f"/api/screening/runs/{run['id']}/results/{cid}").status_code == 404
    )
    assert client.get(f"/api/screening/runs/{run['id']}/agent-runs").status_code == 404
