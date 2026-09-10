"""User data access."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def get(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def list_all(db: Session, *, email: str | None = None) -> list[User]:
    query = select(User).order_by(User.id)
    if email is not None:
        query = query.where(User.email == email)
    return list(db.scalars(query))
