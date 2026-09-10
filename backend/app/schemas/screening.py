"""Screening request/response models.

Two layers:

* **Verbatim contract** — ``IntegrityAuditResult`` (what each detection
  sub-agent outputs) and ``ComparativeAnalysisResult`` (Agent 5). Field names
  and enum values are fixed; ``candidate_id`` and the ranked ids are *strings*
  (``str(candidate.id)``) even though the database keeps ``int`` primary keys.
* **Additive** — ``UnifiedCandidateAudit`` (Agent 4's merged output, persisted
  and returned by the report endpoint) plus the run DTOs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.schemas.common import Page

# --- vocabulary --------------------------------------------------------------

FindingCategory = Literal[
    "PROMPT_INJECTION",
    "SYSTEM_SPOOFING",
    "HIDDEN_PAYLOAD",
    "TIMELINE_OVERLAP",
    "CHRONOLOGICAL_ERROR",
    "SENIORITY_ANOMALY",
    "RECYCLED_METRIC",
    "UNSUBSTANTIATED_INFLATION",
]
AgentName = Literal["manipulation_guard", "timeline_auditor", "inflation_auditor"]
Severity = Literal["info", "low", "medium", "high"]
Disposition = Literal["clear", "review", "high_concern"]
Dimension = Literal[
    "TECHNICAL_DEPTH", "PROVEN_IMPACT", "ROLE_RELEVANCE", "RISK_PROFILE"
]

# --- verbatim contract -----------------------------------------------------------


class IntegrityFlag(BaseModel):
    category: FindingCategory
    evidence: str  # exact quoted string(s) from the candidate text
    reason: str


class IntegrityAuditResult(BaseModel):
    agent_name: AgentName
    candidate_id: str
    is_compromised: bool
    flags: list[IntegrityFlag] = Field(default_factory=list)


class ComparisonDimension(BaseModel):
    dimension: Dimension
    candidate_a_evidence: str
    candidate_b_evidence: str
    tradeoff_analysis: str


class ComparativeAnalysisResult(BaseModel):
    higher_ranked_id: str
    lower_ranked_id: str
    decision_summary: str
    comparisons: list[ComparisonDimension] = Field(default_factory=list)


# --- additive ----------------------------------------------------------------


class EnrichedFinding(BaseModel):
    category: FindingCategory
    evidence: str
    reason: str
    source: AgentName
    severity: Severity | None = None
    benign_explanation: str | None = None
    confidence: float | None = None
    recommended_action: str | None = None
    pattern_key: str | None = None
    verified: bool = True
    id: int | None = None


class UnifiedCandidateAudit(BaseModel):
    run_id: int
    result_id: int | None = None
    candidate_id: str
    candidate_name: str
    status: Literal["pending", "screened", "error", "skipped"]
    resume_sha256: str
    is_compromised: bool
    overall_disposition: Disposition | None
    summary: str
    agent_results: list[IntegrityAuditResult] = Field(default_factory=list)
    findings: list[EnrichedFinding] = Field(default_factory=list)
    degraded: list[str] = Field(default_factory=list)
    provider: dict[str, str] = Field(default_factory=dict)
    models: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime | None = None


class RunResultSummary(BaseModel):
    candidate_id: str
    candidate_name: str
    status: str
    is_compromised: bool
    overall_disposition: Disposition | None
    finding_count: int


class RunSummary(BaseModel):
    id: int
    role_id: int
    status: str
    provider: dict[str, str]
    models: dict[str, str]
    counts: dict[str, int]
    created_at: datetime
    completed_at: datetime | None


class RunDetail(RunSummary):
    results: list[RunResultSummary] = Field(default_factory=list)


# --- requests --------------------------------------------------------------


class RunCreate(BaseModel):
    role_id: int
    candidate_ids: Annotated[list[int], Field(min_length=1)]


class RerunRequest(BaseModel):
    scope: Literal["all", "errored", "changed"] = "all"


class ComparisonCreate(BaseModel):
    role_id: int
    candidate_a_id: int
    candidate_b_id: int


class ComparisonDetail(ComparativeAnalysisResult):
    """A stored pairwise comparison plus the Agent 5 request + reply, verbatim."""

    id: int
    role_id: int
    candidate_a_id: int
    candidate_b_id: int
    findings_surfaced: list = Field(default_factory=list)
    model: str = ""
    prompt_text: str = ""
    raw_response: str = ""
    created_at: datetime | None = None


class AgentRunSummary(BaseModel):
    """One model invocation, metadata only — the run-wide "what are the agents
    doing" feed. The big request/response text is on `AgentRunOut`."""

    id: int
    candidate_id: str
    candidate_name: str | None
    agent_name: str
    tier: str
    model: str
    parsed_ok: bool
    repair_attempts: int
    degraded: bool
    notes: str | None
    tool_call_count: int = 0
    latency_ms: int
    input_chars: int
    created_at: datetime


class AgentRunOut(AgentRunSummary):
    """`AgentRunSummary` plus the request that went out and the reply that came
    back, verbatim. The audit-trail 'info' for one screening result."""

    prompt_text: str
    raw_response: str
    # For an agentic sub-agent: {name, arguments, result_summary, latency_ms}.
    tool_calls: list[dict] = Field(default_factory=list)


__all__ = [
    "IntegrityFlag",
    "IntegrityAuditResult",
    "ComparisonDimension",
    "ComparativeAnalysisResult",
    "EnrichedFinding",
    "UnifiedCandidateAudit",
    "RunResultSummary",
    "RunSummary",
    "RunDetail",
    "RunCreate",
    "RerunRequest",
    "ComparisonCreate",
    "ComparisonDetail",
    "AgentRunSummary",
    "AgentRunOut",
    "Page",
]
