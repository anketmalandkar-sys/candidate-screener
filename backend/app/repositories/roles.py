"""Role data access."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Requirement, Role


def get_owned(db: Session, role_id: int, user_id: int) -> Role | None:
    return db.scalar(
        select(Role)
        .where(Role.id == role_id, Role.user_id == user_id)
        .options(selectinload(Role.requirements))
    )


def count_roles(db: Session, user_id: int, *, active: bool | None = None) -> int:
    query = select(func.count()).select_from(Role).where(Role.user_id == user_id)
    if active is not None:
        query = query.where(Role.is_active.is_(active))
    return db.scalar(query) or 0


def list_with_requirement_counts(
    db: Session,
    user_id: int,
    *,
    active: bool | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[tuple[Role, int]]:
    """Roles owned by a user, newest first, each with its requirement count."""
    requirement_counts = (
        select(Requirement.role_id, func.count().label("n"))
        .group_by(Requirement.role_id)
        .subquery()
    )

    query = (
        select(Role, func.coalesce(requirement_counts.c.n, 0))
        .outerjoin(requirement_counts, requirement_counts.c.role_id == Role.id)
        .where(Role.user_id == user_id)
        .order_by(Role.created_at.desc(), Role.id.desc())
    )
    if active is not None:
        query = query.where(Role.is_active.is_(active))
    if limit is not None:
        query = query.limit(limit).offset(offset)

    return [(role, req_n) for role, req_n in db.execute(query).all()]
