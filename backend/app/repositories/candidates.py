"""Candidate-pool data access."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Candidate


def get_owned(db: Session, candidate_id: int, user_id: int) -> Candidate | None:
    return db.scalar(
        select(Candidate).where(
            Candidate.id == candidate_id, Candidate.user_id == user_id
        )
    )


def count_pool(db: Session, user_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Candidate)
            .where(Candidate.user_id == user_id)
        )
        or 0
    )


def list_pool(
    db: Session, user_id: int, *, limit: int | None = None, offset: int = 0
) -> list[Candidate]:
    """The recruiter's pool, newest first."""
    query = (
        select(Candidate)
        .where(Candidate.user_id == user_id)
        .order_by(Candidate.created_at.desc(), Candidate.id.desc())
    )
    if limit is not None:
        query = query.limit(limit).offset(offset)
    return list(db.scalars(query))
