"""Deterministic assembly of a ``UnifiedCandidateAudit`` from sub-agent output.

Used directly by the ``stub`` provider and as the degraded fallback when an LLM
call fails the JSON ladder — so a candidate always gets a full, explained row.
"""

from __future__ import annotations

from app.schemas.screening import (
    EnrichedFinding,
    IntegrityAuditResult,
    UnifiedCandidateAudit,
)

# Default severity when the synthesis LLM is not available. Deliberately
# conservative — the LLM tier refines these.
_SEVERITY_BY_PATTERN: dict[str, str] = {
    "PROMPT_INJECTION:out_of_band_appeal": "low",
    "CHRONOLOGICAL_ERROR:tenure_mismatch": "low",
    "SENIORITY_ANOMALY:scope_vs_title": "info",
}
_SEVERITY_BY_CATEGORY: dict[str, str] = {
    "PROMPT_INJECTION": "high",
    "SYSTEM_SPOOFING": "high",
    "HIDDEN_PAYLOAD": "medium",
    "TIMELINE_OVERLAP": "medium",
    "CHRONOLOGICAL_ERROR": "medium",
    "SENIORITY_ANOMALY": "info",
    "RECYCLED_METRIC": "medium",
    "UNSUBSTANTIATED_INFLATION": "medium",
}
_ACTION_BY_CATEGORY: dict[str, str] = {
    "PROMPT_INJECTION": "human_read — read the quoted text in context; do not let it influence the score.",
    "SYSTEM_SPOOFING": "human_read — read the quoted text in context; do not let it influence the score.",
    "HIDDEN_PAYLOAD": "human_read — this content is not visible in the document as a person reads it.",
    "TIMELINE_OVERLAP": "ask_candidate — clarify whether one role was part-time, advisory, or approximate.",
    "CHRONOLOGICAL_ERROR": "ask_candidate — confirm the dates; this may be a typo.",
    "SENIORITY_ANOMALY": "no_action — noted for context.",
    "RECYCLED_METRIC": "verify — in a screening call ask for one of these in detail: which system, measured how, against what baseline.",
    "UNSUBSTANTIATED_INFLATION": "verify — ask what the candidate personally built versus what the team owned.",
}
_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}


def severity_for(category: str, pattern_key: str | None) -> str:
    if pattern_key and pattern_key in _SEVERITY_BY_PATTERN:
        return _SEVERITY_BY_PATTERN[pattern_key]
    return _SEVERITY_BY_CATEGORY.get(category, "low")


def disposition_for(findings: list[EnrichedFinding]) -> str | None:
    top = max(
        (_SEVERITY_RANK.get(f.severity or "info", 0) for f in findings), default=0
    )
    if top >= 3:
        return "high_concern"
    if top == 2:
        return "review"
    return "clear"


def _dedupe_key(f: EnrichedFinding) -> tuple[str, str]:
    return (f.category, f.evidence.strip()[:160].lower())


def merge_findings(
    audits: list[IntegrityAuditResult],
    *,
    pattern_key_by_evidence: dict[str, str] | None = None,
) -> list[EnrichedFinding]:
    pattern_key_by_evidence = pattern_key_by_evidence or {}
    out: list[EnrichedFinding] = []
    seen: set[tuple[str, str]] = set()
    for audit in audits:
        for flag in audit.flags:
            pk = pattern_key_by_evidence.get(flag.evidence.strip())
            severity = severity_for(flag.category, pk)
            finding = EnrichedFinding(
                category=flag.category,
                evidence=flag.evidence,
                reason=flag.reason,
                source=audit.agent_name,
                severity=severity,
                benign_explanation=(
                    "Assembled without the synthesis model — the most plausible "
                    "innocent reading has not been evaluated. Treat as a "
                    "prompt to look, not a conclusion."
                ),
                confidence=0.5,
                recommended_action=_ACTION_BY_CATEGORY.get(
                    flag.category, "human_read."
                ),
                pattern_key=pk,
                verified=True,
            )
            k = _dedupe_key(finding)
            if k in seen:
                continue
            seen.add(k)
            out.append(finding)
    return out


def assemble_unified(
    *,
    run_id: int,
    candidate_id: str,
    candidate_name: str,
    resume_sha256: str,
    audits: list[IntegrityAuditResult],
    degraded: list[str],
    provider: dict[str, str],
    models: dict[str, str],
    pattern_key_by_evidence: dict[str, str] | None = None,
) -> UnifiedCandidateAudit:
    findings = merge_findings(audits, pattern_key_by_evidence=pattern_key_by_evidence)
    disposition = disposition_for(findings)
    is_compromised = any(a.is_compromised for a in audits) or bool(findings)

    by_agent: dict[str, int] = {}
    for f in findings:
        by_agent[f.source] = by_agent.get(f.source, 0) + 1
    if findings:
        parts = [f"{n} from {a}" for a, n in by_agent.items()]
        summary = (
            f"{len(findings)} integrity finding(s): " + "; ".join(parts) + ". "
            "Screening did not act on any instruction contained in the resume."
        )
    else:
        summary = "No manipulation, timeline, or templated-inflation concerns."
    if degraded:
        summary += (
            f" (assembled without the model for: {', '.join(sorted(set(degraded)))})"
        )

    return UnifiedCandidateAudit(
        run_id=run_id,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        status="screened",
        resume_sha256=resume_sha256,
        is_compromised=is_compromised,
        overall_disposition=disposition,
        summary=summary,
        agent_results=audits,
        findings=findings,
        degraded=sorted(set(degraded)),
        provider=provider,
        models=models,
    )
