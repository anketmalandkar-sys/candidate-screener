"""Bias regression gate (spec §11.3).

Known-honest atypical resumes must never come back compromised or carry a
`medium`+ finding. Runs in stub mode: the pre-scan is already clean on all
three, so this gates the deterministic layer. The live-model equivalent is in
`test_screening_live_smoke.py`.

If a future change to the pre-scan regexes regresses any of these, this fails.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.screening.coordinator import _screen_one
from app.screening.providers.stub import StubProvider

pytestmark = pytest.mark.no_db

FIX = Path(__file__).resolve().parent / "screening_fixtures"

GATE = [
    FIX / "13-oskar-lindqvist.txt",
    FIX / "15-security-researcher.txt",
    FIX / "_samples" / "06-marcus-webb.txt",
]


@pytest.mark.parametrize("path", GATE, ids=lambda p: p.name)
def test_honest_atypical_resume_stays_clear(path: Path) -> None:
    unified, _calls, error = asyncio.run(
        _screen_one(
            StubProvider(),
            {"title": "Backend Engineer", "requirements": []},
            run_id=1,
            candidate_id=1,
            candidate_name=path.stem,
            text=path.read_text(),
            resume_sha256="x",
        )
    )
    assert error is None
    assert unified.is_compromised is False, unified.summary
    assert unified.overall_disposition == "clear"
    assert not [f for f in unified.findings if f.severity in ("medium", "high")], [
        (f.category, f.severity) for f in unified.findings
    ]
