"""Candidate-pool business logic: intake and the API shapes."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Candidate


def pool_item(candidate: Candidate) -> dict:
    """Shape a candidate for the pool list."""
    return {
        "id": candidate.id,
        "name": candidate.name,
        "email": candidate.email,
        "source": candidate.source,
        "original_filename": candidate.original_filename,
        "created_at": candidate.created_at,
    }


def pool_detail(candidate: Candidate) -> dict:
    """As `pool_item`, plus the resume text — everything the detail view needs."""
    return {**pool_item(candidate), "resume_text": candidate.resume_text}


def create_candidate(
    db: Session,
    user_id: int,
    *,
    name: str,
    resume_text: str,
    email: str | None = None,
    source: str = "paste",
    original_filename: str | None = None,
) -> dict:
    candidate = Candidate(
        user_id=user_id,
        name=name.strip(),
        email=email,
        resume_text=resume_text,
        source=source,
        original_filename=original_filename,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return pool_item(candidate)


def delete_candidate(db: Session, candidate: Candidate) -> None:
    db.delete(candidate)
    db.commit()
