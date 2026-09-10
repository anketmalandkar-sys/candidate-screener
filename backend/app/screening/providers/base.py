"""The provider interface the coordinator drives.

A provider owns the model calls for one or both tiers. It returns plain schema
objects plus ``AgentCall`` records (which the coordinator persists to
``screening_agent_runs``) — it never touches the database.
"""

from __future__ import annotations

from typing import Protocol

from app.schemas.screening import (
    ComparativeAnalysisResult,
    IntegrityAuditResult,
    UnifiedCandidateAudit,
)
from app.screening.types import AgentCall, PrescanResult


class Provider(Protocol):
    async def detect(
        self,
        *,
        candidate_id: str,
        text: str,
        prescan: PrescanResult,
        role_context: dict,
    ) -> tuple[list[IntegrityAuditResult], list[AgentCall]]:
        """Run Agents 1/2/3 (isolated) → three IntegrityAuditResults + call records."""
        ...

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
        """Run Agent 4 → the merged, enriched UnifiedCandidateAudit + call record."""
        ...

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
        """Run Agent 5 → a ComparativeAnalysisResult + call record."""
        ...

    def describe(self) -> dict[str, str]:
        """{'detection': ..., 'synthesis': ...} for the run record."""
        ...
