"""Screening: multi-agent resume integrity audits.

A ``ScreeningRun`` covers one role and a chosen set of candidates. Each selected
candidate gets exactly one ``ScreeningResult`` (enforced by a unique constraint
and a post-run assertion in the coordinator) — the "never silently drop a
candidate" rule made structural. ``ScreeningFinding`` rows are the merged flags;
``ScreeningAgentRun`` rows are the per-LLM-call audit trail that makes "never
silently execute an injection" provable after the fact.

Enum-like columns use ``CHECK`` constraints rather than Postgres enum types, to
match ``requirements.weight``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utilities.common import utcnow

# --- vocabulary -------------------------------------------------------------

RUN_STATUSES = ("queued", "running", "partial", "complete", "failed")
RESULT_STATUSES = ("pending", "screened", "error", "skipped")
DISPOSITIONS = ("clear", "review", "high_concern")

FINDING_CATEGORIES = (
    "PROMPT_INJECTION",
    "SYSTEM_SPOOFING",
    "HIDDEN_PAYLOAD",
    "TIMELINE_OVERLAP",
    "CHRONOLOGICAL_ERROR",
    "SENIORITY_ANOMALY",
    "RECYCLED_METRIC",
    "UNSUBSTANTIATED_INFLATION",
)
SEVERITIES = ("info", "low", "medium", "high")

AGENT_NAMES = (
    # The prompt-injection classifier on hf-inference — one row per candidate,
    # folded into the sub-agents' feature bundle but surfaced on its own so the
    # activity feed shows the HF model that actually runs.
    "injection_classifier",
    "manipulation_guard",
    "timeline_auditor",
    "inflation_auditor",
    "synthesizer",
    "comparative_reasoner",
)
AGENT_TIERS = ("hf", "openai", "stub")


def _in(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


# --- entities ------------------------------------------------------------------


class ScreeningRun(Base):
    __tablename__ = "screening_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    # {"detection": "...", "synthesis": "..."}
    provider: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    models: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    screened: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    compromised: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errored: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    results: Mapped[list["ScreeningResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(_in("status", RUN_STATUSES), name="ck_screening_run_status"),
    )


class ScreeningResult(Base):
    __tablename__ = "screening_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("screening_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalised so tenant filtering is a single column on this table too.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    resume_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_compromised: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    overall_disposition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # The three raw IntegrityAuditResult objects, untouched.
    agent_results: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # Comma-joined agent_names whose contribution was assembled deterministically.
    degraded: Mapped[str | None] = mapped_column(Text, nullable=True)
    models: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    run: Mapped["ScreeningRun"] = relationship(back_populates="results")
    findings: Mapped[list["ScreeningFinding"]] = relationship(
        back_populates="result", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list["ScreeningAgentRun"]] = relationship(
        back_populates="result"
    )

    __table_args__ = (
        UniqueConstraint("run_id", "candidate_id", name="uq_screening_result_run_cand"),
        CheckConstraint(
            _in("status", RESULT_STATUSES), name="ck_screening_result_status"
        ),
        CheckConstraint(
            "overall_disposition IS NULL OR "
            + _in("overall_disposition", DISPOSITIONS),
            name="ck_screening_result_disposition",
        ),
    )


class ScreeningFinding(Base):
    __tablename__ = "screening_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(
        ForeignKey("screening_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # The agent_name that raised it.
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    # Enrichment added by the synthesis engine (Agent 4). Nullable so a
    # pre-scan-only degraded path can still write a flag.
    severity: Mapped[str | None] = mapped_column(String(8), nullable=True)
    benign_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    pattern_key: Mapped[str | None] = mapped_column(String(64), nullable=True)

    verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    result: Mapped["ScreeningResult"] = relationship(back_populates="findings")

    __table_args__ = (
        CheckConstraint(
            _in("category", FINDING_CATEGORIES), name="ck_screening_finding_category"
        ),
        CheckConstraint(
            "severity IS NULL OR " + _in("severity", SEVERITIES),
            name="ck_screening_finding_severity",
        ),
    )


class ScreeningAgentRun(Base):
    """One row per LLM agent invocation — the audit trail."""

    __tablename__ = "screening_agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("screening_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable: agent runs happen before the result row is finalised.
    result_id: Mapped[int | None] = mapped_column(
        ForeignKey("screening_results.id", ondelete="CASCADE"), nullable=True
    )
    agent_name: Mapped[str] = mapped_column(String(32), nullable=False)
    tier: Mapped[str] = mapped_column(String(8), nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # The full request sent to the model (system + user), kept for inspection.
    prompt_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_response: Mapped[str] = mapped_column(Text, default="", nullable=False)
    parsed_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # For an agentic sub-agent: one entry per tool the model called —
    # {name, arguments, result_summary, latency_ms}.
    tool_calls: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    parsed_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    repair_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Free-text markers: LLM_MISSED_INJECTION, LEGIT_TERMINOLOGY_CLEARED, ...
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_chars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    result: Mapped["ScreeningResult | None"] = relationship(back_populates="agent_runs")

    __table_args__ = (
        CheckConstraint(
            _in("agent_name", AGENT_NAMES), name="ck_screening_agent_run_name"
        ),
        CheckConstraint(_in("tier", AGENT_TIERS), name="ck_screening_agent_run_tier"),
    )


class Comparison(Base):
    __tablename__ = "comparisons"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    candidate_a_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    candidate_b_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    # The ComparativeAnalysisResult.
    result: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    findings_surfaced: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # The Agent 5 request + reply, verbatim.
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_response: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
