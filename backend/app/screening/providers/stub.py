"""The ``stub`` provider: deterministic pre-scan only, no network.

Selected by ``SCREENING_PROVIDER=stub`` (the test default). ``detect`` turns the
pre-scan hits into one ``IntegrityAuditResult`` per sub-agent; ``synthesize``
runs the deterministic assembly; ``compare`` returns a fixed shape.
"""

from __future__ import annotations

from app.schemas.screening import (
    ComparativeAnalysisResult,
    ComparisonDimension,
    IntegrityAuditResult,
    IntegrityFlag,
    UnifiedCandidateAudit,
)
from app.screening.assembly import assemble_unified
from app.screening.types import AgentCall, PrescanResult

_AGENTS = ("manipulation_guard", "timeline_auditor", "inflation_auditor")


class StubProvider:
    def describe(self) -> dict[str, str]:
        return {"detection": "stub", "synthesis": "stub"}

    async def detect(
        self,
        *,
        candidate_id: str,
        text: str,
        prescan: PrescanResult,
        role_context: dict,
    ) -> tuple[list[IntegrityAuditResult], list[AgentCall]]:
        results: list[IntegrityAuditResult] = []
        calls: list[AgentCall] = []
        for agent in _AGENTS:
            hits = prescan.hits_for(agent)
            flags = [
                IntegrityFlag(category=h.category, evidence=h.evidence, reason=h.reason)
                for h in hits
            ]
            result = IntegrityAuditResult(
                agent_name=agent,
                candidate_id=candidate_id,
                is_compromised=bool(flags),
                flags=flags,
            )
            results.append(result)
            calls.append(
                AgentCall(
                    agent_name=agent,
                    tier="stub",
                    model="stub",
                    prompt_text="stub provider — deterministic pre-scan, no model request",
                    raw_response=result.model_dump_json(),
                    parsed_result=result.model_dump(),
                    parsed_ok=True,
                    input_chars=len(text),
                )
            )
        return results, calls

    async def synthesize(
        self,
        *,
        run_id: int,
        candidate_id: str,
        candidate_name: str,
        resume_sha256: str,
        text: str,
        audits: list[IntegrityAuditResult],
        prescan: PrescanResult,
    ) -> tuple[UnifiedCandidateAudit, AgentCall]:
        pk_by_evidence = {h.evidence.strip(): h.pattern_key for h in prescan.hits}
        unified = assemble_unified(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_name=candidate_name,
            resume_sha256=resume_sha256,
            audits=audits,
            degraded=[],
            provider=self.describe(),
            models={"synthesizer": "stub"},
            pattern_key_by_evidence=pk_by_evidence,
        )
        call = AgentCall(
            agent_name="synthesizer",
            tier="stub",
            model="stub",
            prompt_text="stub provider — deterministic, no model request",
            raw_response=unified.model_dump_json(),
            parsed_result=unified.model_dump(mode="json"),
            parsed_ok=True,
            input_chars=len(text),
        )
        return unified, call

    async def compare(
        self,
        *,
        role_context: dict,
        resume_a: str,
        resume_b: str,
        audit_a: dict | None,
        audit_b: dict | None,
        candidate_a_id: str,
        candidate_b_id: str,
    ) -> tuple[ComparativeAnalysisResult, AgentCall]:
        # Deterministic: the candidate with fewer open findings ranks higher.
        n_a = len((audit_a or {}).get("findings", []))
        n_b = len((audit_b or {}).get("findings", []))
        if n_a <= n_b:
            higher, lower = candidate_a_id, candidate_b_id
        else:
            higher, lower = candidate_b_id, candidate_a_id
        result = ComparativeAnalysisResult(
            higher_ranked_id=higher,
            lower_ranked_id=lower,
            decision_summary=(
                "Stub comparison: ranked by fewer open integrity findings "
                f"({candidate_a_id}: {n_a}, {candidate_b_id}: {n_b})."
            ),
            comparisons=[
                ComparisonDimension(
                    dimension="RISK_PROFILE",
                    candidate_a_evidence=f"{n_a} open finding(s).",
                    candidate_b_evidence=f"{n_b} open finding(s).",
                    tradeoff_analysis=(
                        "Integrity findings penalise rank regardless of nominal "
                        "years of experience."
                    ),
                )
            ],
        )
        call = AgentCall(
            agent_name="comparative_reasoner",
            tier="stub",
            model="stub",
            prompt_text="stub provider — deterministic, no model request",
            raw_response=result.model_dump_json(),
            parsed_result=result.model_dump(),
            parsed_ok=True,
        )
        return result, call
