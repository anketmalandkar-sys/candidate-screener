"""Deterministic pre-scan rules, driven by the fixture resumes.

Pure logic — no database. Run standalone with `python3 -m pytest -m no_db`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.screening.prescan import run_prescan

pytestmark = pytest.mark.no_db

FIXTURES = Path(__file__).resolve().parent / "screening_fixtures"
SAMPLES = Path(__file__).resolve().parent / "screening_fixtures" / "_samples"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def _cats(text: str) -> set[str]:
    return {h.category for h in run_prescan(text).hits}


def _pattern_keys(text: str) -> set[str]:
    return {h.pattern_key for h in run_prescan(text).hits}


# --- clean inputs must stay clean -------------------------------------------


@pytest.mark.parametrize(
    "name",
    [p.name for p in sorted(SAMPLES.glob("*.txt"))],
)
def test_original_samples_have_no_prescan_hits(name: str) -> None:
    assert run_prescan((SAMPLES / name).read_text()).hits == []


@pytest.mark.parametrize(
    "name", ["13-oskar-lindqvist.txt", "15-security-researcher.txt"]
)
def test_honest_atypical_resumes_are_clean_at_prescan_level(name: str) -> None:
    """The honest contractor / career-changer (13) and the AI-safety researcher
    who legitimately writes about prompt injection (15) must not trip a single
    rule — the bias-guard baseline (spec §11.3)."""
    assert run_prescan(_read(name)).hits == []


def test_15_security_terminology_is_not_flagged_but_09_still_is() -> None:
    fifteen = run_prescan(_read("15-security-researcher.txt")).hits_for(
        "manipulation_guard"
    )
    assert fifteen == []
    nine = {h.pattern_key for h in run_prescan(_read("09-derek-coleman.txt")).hits}
    assert "PROMPT_INJECTION:imperative_to_ai" in nine
    assert "SYSTEM_SPOOFING:role_prefix" in nine


# --- manipulation ----------------------------------------------------------


def test_09_flags_injection_spoofing_and_hidden_payload() -> None:
    keys = _pattern_keys(_read("09-derek-coleman.txt"))
    cats = _cats(_read("09-derek-coleman.txt"))
    assert "PROMPT_INJECTION" in cats
    assert "SYSTEM_SPOOFING" in cats
    assert "HIDDEN_PAYLOAD" in cats
    assert "PROMPT_INJECTION:delimiter_escape" in keys
    assert any(k.startswith("HIDDEN_PAYLOAD:") for k in keys)


def test_09_removing_all_planted_artifacts_leaves_it_clean() -> None:
    text = _read("09-derek-coleman.txt")
    cleaned_lines = [
        ln
        for ln in text.splitlines()
        if "SYSTEM:" not in ln
        and "</candidate_text>" not in ln
        and "​" not in ln
        and "‌" not in ln
    ]
    assert run_prescan("\n".join(cleaned_lines)).hits_for("manipulation_guard") == []


def test_10_soft_out_of_band_appeal_is_injection() -> None:
    keys = _pattern_keys(_read("10-nadia-halvorsen.txt"))
    assert "PROMPT_INJECTION:out_of_band_appeal" in keys


# --- timeline ------------------------------------------------------------------


def test_11_overlap_tenure_and_scope() -> None:
    hits = run_prescan(_read("11-victor-almeida.txt")).hits_for("timeline_auditor")
    cats = {h.category for h in hits}
    assert cats == {"TIMELINE_OVERLAP", "CHRONOLOGICAL_ERROR", "SENIORITY_ANOMALY"}
    overlap = next(h for h in hits if h.category == "TIMELINE_OVERLAP")
    assert "||" in overlap.evidence  # both conflicting spans are quoted


def test_14_study_work_overlap() -> None:
    hits = run_prescan(_read("14-grace-otieno.txt")).hits_for("timeline_auditor")
    assert [h.category for h in hits] == ["TIMELINE_OVERLAP"]
    assert "||" in hits[0].evidence


def test_16_chronological_inversions() -> None:
    keys = _pattern_keys(_read("16-arne-solberg.txt"))
    assert "CHRONOLOGICAL_ERROR:end_before_start" in keys
    assert "CHRONOLOGICAL_ERROR:title_before_degree" in keys


# --- inflation ---------------------------------------------------------------


def test_12_recycled_metrics_across_roles() -> None:
    hits = run_prescan(_read("12-priyanka-rao.txt")).hits_for("inflation_auditor")
    cats = {h.category for h in hits}
    assert "RECYCLED_METRIC" in cats
    assert "UNSUBSTANTIATED_INFLATION" in cats
    dup = next(h for h in hits if h.category == "RECYCLED_METRIC")
    assert "repeated across" in dup.evidence


def test_17_junior_enterprise_claim() -> None:
    keys = _pattern_keys(_read("17-kevin-mensah.txt"))
    assert "UNSUBSTANTIATED_INFLATION:junior_enterprise_claim" in keys


# --- feature bundle --------------------------------------------------------


def test_feature_bundle_populated_for_09() -> None:
    features = run_prescan(_read("09-derek-coleman.txt")).features
    assert features.injection_hits
    assert features.delimiter_escapes
    assert features.system_markers
    assert features.hidden_text_inventory
