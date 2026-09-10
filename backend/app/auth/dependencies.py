"""FastAPI dependencies: the current session, and owned-resource lookups.

Every authenticated route resolves through `get_current_user`; every route that
touches a role or a candidate resolves through the matching owned-resource
helper. Fetching another recruiter's resource returns **404, not 403** — a 403
confirms the id exists, which lets an attacker enumerate other tenants.
"""

from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.models import Candidate, Role, ScreeningRun, User
from app.repositories import candidates as candidate_repo
from app.repositories import roles as role_repo
from app.repositories import screening as screening_repo
from app.repositories import users as user_repo
from app.repositories.database import get_db

SESSION_COOKIE_NAME = "session"


def get_current_user(
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    user_id = decode_access_token(session)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    user = user_repo.get(db, user_id)
    if user is None:
        # Token signature was valid but the account is gone — treat as logged out.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    return user


def get_owned_role(
    role_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Role:
    role = role_repo.get_owned(db, role_id, user.id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )
    return role


def get_owned_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Candidate:
    candidate = candidate_repo.get_owned(db, candidate_id, user.id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found"
        )
    return candidate


def get_owned_screening_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScreeningRun:
    run = screening_repo.get_owned_run_with_results(db, run_id, user.id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Screening run not found"
        )
    return run
