"""Registration and password verification."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import (
    burn_timing,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.models import User
from app.repositories import users as user_repo
from app.schemas.auth import RegisterRequest
from app.utilities.config import get_settings


class EmailTakenError(Exception):
    """Raised when the email is already registered."""


def register(db: Session, payload: RegisterRequest) -> User:
    """Create an account; seed it with the demo dataset when that is enabled.

    Raises `EmailTakenError` on a duplicate address (the unique index is the
    authority — checking first would still race concurrent signups).
    """
    user = User(
        email=payload.email.strip().lower(),
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailTakenError from exc

    db.refresh(user)

    if get_settings().seed_demo_data:
        from app.seed import seed_user

        seed_user(db, user)
        db.commit()
        db.refresh(user)

    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the user on a correct password, else None. Upgrades a stale hash
    transparently on success; spends a hash-verify's worth of time on the
    no-such-account path so the response duration does not leak whether an
    address is registered."""
    user = user_repo.get_by_email(db, email.strip().lower())
    if user is None:
        burn_timing()
        return None
    if not verify_password(password, user.password_hash):
        return None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    return user
