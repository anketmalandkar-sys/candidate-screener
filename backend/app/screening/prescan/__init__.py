"""The deterministic pre-scan: cheap, high-precision signals + a feature bundle.

``run_prescan(text)`` is pure and dependency-free (``no_db`` safe). The sub-agents
receive its ``features`` as evidence to weigh; the verifier's coverage check
treats an un-explained manipulation hit as proof the LLM missed an injection.
"""

from __future__ import annotations

from app.screening.prescan import inflation, manipulation, timeline
from app.screening.prescan.normalize import normalize
from app.screening.types import FeatureBundle, PrescanResult


def run_prescan(text: str) -> PrescanResult:
    norm = normalize(text)

    manip_hits = manipulation.scan(text, norm)
    tl_hits, timeline_table = timeline.scan(norm.clean_text)
    infl_hits, dup_clusters = inflation.scan(norm.clean_text)

    hits = [*manip_hits, *tl_hits, *infl_hits]

    features = FeatureBundle(
        timeline_table=timeline_table,
        dup_clusters=dup_clusters,
        injection_hits=[
            h.evidence for h in manip_hits if h.category == "PROMPT_INJECTION"
        ],
        delimiter_escapes=[
            h.evidence
            for h in manip_hits
            if h.pattern_key == "PROMPT_INJECTION:delimiter_escape"
        ],
        system_markers=[
            h.evidence for h in manip_hits if h.category == "SYSTEM_SPOOFING"
        ],
        hidden_text_inventory=norm.hidden_runs,
    )

    return PrescanResult(clean_text=norm.clean_text, hits=hits, features=features)
