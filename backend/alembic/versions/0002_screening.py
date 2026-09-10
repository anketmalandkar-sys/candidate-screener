"""Screening: runs, results, findings, agent-run audit trail, and pairwise
comparisons.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


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
    "injection_classifier",
    "manipulation_guard",
    "timeline_auditor",
    "inflation_auditor",
    "synthesizer",
    "comparative_reasoner",
)
AGENT_TIERS = ("hf", "openai", "stub")


def _in(column: str, values) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "screening_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("provider", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("models", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("screened", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("compromised", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errored", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_in("status", RUN_STATUSES), name="ck_screening_run_status"),
    )
    op.create_index("ix_screening_runs_user_id", "screening_runs", ["user_id"])
    op.create_index("ix_screening_runs_role_id", "screening_runs", ["role_id"])

    op.create_table(
        "screening_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("screening_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.Integer(),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("candidate_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("resume_sha256", sa.String(64), nullable=False),
        sa.Column(
            "is_compromised", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("overall_disposition", sa.String(16), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "agent_results", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column("degraded", sa.Text(), nullable=True),
        sa.Column("models", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id", "candidate_id", name="uq_screening_result_run_cand"
        ),
        sa.CheckConstraint(
            _in("status", RESULT_STATUSES), name="ck_screening_result_status"
        ),
        sa.CheckConstraint(
            "overall_disposition IS NULL OR "
            + _in("overall_disposition", DISPOSITIONS),
            name="ck_screening_result_disposition",
        ),
    )
    op.create_index("ix_screening_results_run_id", "screening_results", ["run_id"])
    op.create_index("ix_screening_results_user_id", "screening_results", ["user_id"])

    op.create_table(
        "screening_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "result_id",
            sa.Integer(),
            sa.ForeignKey("screening_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(8), nullable=True),
        sa.Column("benign_explanation", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("pattern_key", sa.String(64), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            _in("category", FINDING_CATEGORIES),
            name="ck_screening_finding_category",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR " + _in("severity", SEVERITIES),
            name="ck_screening_finding_severity",
        ),
    )
    op.create_index(
        "ix_screening_findings_result_id", "screening_findings", ["result_id"]
    )

    op.create_table(
        "screening_agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("screening_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.Integer(),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "result_id",
            sa.Integer(),
            sa.ForeignKey("screening_results.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("agent_name", sa.String(32), nullable=False),
        sa.Column("tier", sa.String(8), nullable=False),
        sa.Column("model", sa.String(120), nullable=False, server_default=""),
        sa.Column("prompt_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("prompt_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_response", sa.Text(), nullable=False, server_default=""),
        sa.Column("parsed_result", postgresql.JSONB(), nullable=True),
        sa.Column(
            "tool_calls", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column("parsed_ok", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("repair_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            _in("agent_name", AGENT_NAMES), name="ck_screening_agent_run_name"
        ),
        sa.CheckConstraint(
            _in("tier", AGENT_TIERS), name="ck_screening_agent_run_tier"
        ),
    )
    op.create_index(
        "ix_screening_agent_runs_run_id", "screening_agent_runs", ["run_id"]
    )

    op.create_table(
        "comparisons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_a_id",
            sa.Integer(),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_b_id",
            sa.Integer(),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "findings_surfaced",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("model", sa.String(120), nullable=False, server_default=""),
        sa.Column("prompt_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_response", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_comparisons_user_id", "comparisons", ["user_id"])


def downgrade() -> None:
    op.drop_table("comparisons")
    op.drop_table("screening_agent_runs")
    op.drop_table("screening_findings")
    op.drop_table("screening_results")
    op.drop_table("screening_runs")
