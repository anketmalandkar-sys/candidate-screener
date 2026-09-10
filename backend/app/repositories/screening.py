"""Screening data access."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Candidate,
    Comparison,
    ScreeningAgentRun,
    ScreeningResult,
    ScreeningRun,
)

# --- runs ------------------------------------------------------------------


def get_owned_run_with_results(
    db: Session, run_id: int, user_id: int
) -> ScreeningRun | None:
    return db.scalar(
        select(ScreeningRun)
        .where(ScreeningRun.id == run_id, ScreeningRun.user_id == user_id)
        .options(selectinload(ScreeningRun.results))
    )


def count_runs(db: Session, user_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(ScreeningRun)
            .where(ScreeningRun.user_id == user_id)
        )
        or 0
    )


def list_runs(
    db: Session, user_id: int, *, limit: int, offset: int
) -> list[ScreeningRun]:
    return list(
        db.scalars(
            select(ScreeningRun)
            .where(ScreeningRun.user_id == user_id)
            .order_by(ScreeningRun.created_at.desc(), ScreeningRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


# --- candidates for a run ------------------------------------------------------


def owned_candidates_by_id(
    db: Session, user_id: int, candidate_ids: list[int]
) -> dict[int, Candidate]:
    rows = db.scalars(
        select(Candidate).where(
            Candidate.user_id == user_id, Candidate.id.in_(candidate_ids)
        )
    )
    return {c.id: c for c in rows}


# --- results ----------------------------------------------------------------


def get_result_for_candidate(
    db: Session, run_id: int, candidate_id: int, user_id: int
) -> ScreeningResult | None:
    return db.scalar(
        select(ScreeningResult)
        .where(
            ScreeningResult.run_id == run_id,
            ScreeningResult.candidate_id == candidate_id,
            ScreeningResult.user_id == user_id,
        )
        .options(selectinload(ScreeningResult.findings))
    )


def list_comparisons(db: Session, user_id: int) -> list[Comparison]:
    return list(
        db.scalars(
            select(Comparison)
            .where(Comparison.user_id == user_id)
            .order_by(Comparison.created_at.desc(), Comparison.id.desc())
        )
    )


def get_owned_comparison(
    db: Session, comparison_id: int, user_id: int
) -> Comparison | None:
    return db.scalar(
        select(Comparison).where(
            Comparison.id == comparison_id, Comparison.user_id == user_id
        )
    )


def list_agent_runs(
    db: Session, run_id: int, candidate_id: int
) -> list[ScreeningAgentRun]:
    return list(
        db.scalars(
            select(ScreeningAgentRun)
            .where(
                ScreeningAgentRun.run_id == run_id,
                ScreeningAgentRun.candidate_id == candidate_id,
            )
            .order_by(ScreeningAgentRun.id)
        )
    )


def list_agent_runs_for_run(
    db: Session, run_id: int
) -> list[tuple[ScreeningAgentRun, str | None]]:
    """Every agent call for the run, oldest first, with the candidate-name
    snapshot from its result row (survives candidate deletion)."""
    rows = db.execute(
        select(ScreeningAgentRun, ScreeningResult.candidate_name)
        .join(
            ScreeningResult,
            ScreeningAgentRun.result_id == ScreeningResult.id,
            isouter=True,
        )
        .where(ScreeningAgentRun.run_id == run_id)
        .order_by(ScreeningAgentRun.id)
    ).all()
    return [(ar, name) for ar, name in rows]


def latest_screened_result(
    db: Session, user_id: int, candidate_id: int
) -> ScreeningResult | None:
    return db.scalar(
        select(ScreeningResult)
        .where(
            ScreeningResult.user_id == user_id,
            ScreeningResult.candidate_id == candidate_id,
            ScreeningResult.status == "screened",
        )
        .order_by(ScreeningResult.created_at.desc(), ScreeningResult.id.desc())
        .options(selectinload(ScreeningResult.findings))
        .limit(1)
    )
