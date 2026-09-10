"""Guard rails over agent output.

* **evidence-quote check** — every ``evidence`` string must be a
  whitespace-tolerant substring of the original candidate text (joined spans,
  split on ``||``, are checked part by part). A quote that cannot be located is
  dropped and recorded — the anti-hallucination guard.
* **canary check** — no agent output may contain the canary token or otherwise
  show it followed an instruction from the resume.
* **coverage check** — a deterministic manipulation hit (injection / delimiter
  escape / system marker) with no corresponding flag from ``manipulation_guard``
  is synthesised back in, so an injection the LLM missed never vanishes.
"""

from __future__ import annotations

import re

from app.schemas.screening import IntegrityAuditResult, IntegrityFlag
from app.screening import CANARY
from app.screening.types import PrescanResult

_WS_RE = re.compile(r"\s+")


def _norm_ws(s: str) -> str:
    return _WS_RE.sub(" ", s).strip().lower()


def quote_is_grounded(evidence: str, haystack: str) -> bool:
    hay = _norm_ws(haystack)
    for part in re.split(r"\s*\|\|\s*", evidence):
        part = part.strip()
        # Strip a trailing parenthetical the pre-scan adds for context.
        part = re.sub(
            r"\s*\((?:repeated across|earliest listed role)[^)]*\)\s*$", "", part
        )
        part = re.sub(r"^\[.*\]$", "", part).strip()
        if not part:
            continue
        if _norm_ws(part) not in hay:
            return False
    return True


def verify_audit(
    audit: IntegrityAuditResult, original_text: str
) -> tuple[IntegrityAuditResult, list[str]]:
    notes: list[str] = []
    kept: list[IntegrityFlag] = []
    for flag in audit.flags:
        # Hidden-payload evidence is a synthetic descriptor, not a quote.
        if flag.category == "HIDDEN_PAYLOAD" or quote_is_grounded(
            flag.evidence, original_text
        ):
            kept.append(flag)
        else:
            notes.append(
                f"dropped {flag.category} flag from {audit.agent_name}: "
                "evidence not found verbatim in the candidate text"
            )
    cleaned = audit.model_copy(update={"flags": kept})
    return cleaned, notes


def scan_for_canary(raw_responses: list[str]) -> list[str]:
    return [
        f"canary token present in agent output #{i}"
        for i, raw in enumerate(raw_responses)
        if CANARY in raw
    ]


def coverage_check(
    prescan: PrescanResult, audits: list[IntegrityAuditResult]
) -> tuple[list[IntegrityAuditResult], list[str]]:
    """Ensure every deterministic manipulation hit is represented in the
    manipulation_guard result. Returns possibly-augmented audits + notes."""
    notes: list[str] = []
    manip = next((a for a in audits if a.agent_name == "manipulation_guard"), None)
    if manip is None:
        return audits, notes

    covered = {_norm_ws(f.evidence) for f in manip.flags}
    synthesised: list[IntegrityFlag] = []
    for hit in prescan.hits_for("manipulation_guard"):
        if hit.category not in ("PROMPT_INJECTION", "SYSTEM_SPOOFING"):
            continue
        if _norm_ws(hit.evidence) in covered:
            continue
        synthesised.append(
            IntegrityFlag(
                category=hit.category,
                evidence=hit.evidence,
                reason=hit.reason + " (added by the deterministic coverage check — "
                "the detection model did not report it).",
            )
        )
        notes.append(f"LLM_MISSED_INJECTION: {hit.pattern_key}")

    if not synthesised:
        return audits, notes

    updated = manip.model_copy(
        update={
            "flags": [*manip.flags, *synthesised],
            "is_compromised": True,
        }
    )
    return [updated if a is manip else a for a in audits], notes
