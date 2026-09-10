"""Load the synthetic demo dataset — one private copy per recruiter.

Every recruiter gets their own ~6 roles and ~120 candidates, so the demo data
is visible to everyone without any shared-ownership special cases. New
registrations are seeded automatically when ``SEED_DEMO_DATA=true``; existing
accounts are seeded by hand:

    python -m app.seed                       # seed every account not yet seeded
    python -m app.seed --email you@example.com
    python -m app.seed --reset               # rebuild each account's seed data
"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Candidate, Requirement, Role, User
from app.repositories import users as user_repo
from app.repositories.database import SessionLocal
from app.seed.dataset import SEED_ROLE_TITLES, build_dataset
from app.utilities.common import WEIGHT_VALUES


def _has_seed_data(db: Session, user_id: int) -> bool:
    return (
        db.scalar(
            select(Role.id)
            .where(Role.user_id == user_id, Role.title.in_(SEED_ROLE_TITLES))
            .limit(1)
        )
        is not None
    )


def _wipe_seed_data(db: Session, user_id: int) -> None:
    roles = db.scalars(
        select(Role).where(Role.user_id == user_id, Role.title.in_(SEED_ROLE_TITLES))
    ).all()
    for role in roles:
        db.delete(role)
    # Candidates are a flat pool with no link back to the seed roles, so a
    # reset clears the whole pool and rebuilds it. A seeded demo account's
    # candidates are all seed data.
    for candidate in db.scalars(
        select(Candidate).where(Candidate.user_id == user_id)
    ).all():
        db.delete(candidate)
    db.flush()


def seed_user(db: Session, user: User, *, reset: bool = False) -> int:
    """Give one recruiter their own copy of the demo dataset. Idempotent.

    Returns the number of candidates created (0 when the account was already
    seeded and ``reset`` is False). Does not commit — the caller owns the
    transaction.
    """
    if _has_seed_data(db, user.id):
        if not reset:
            return 0
        _wipe_seed_data(db, user.id)

    created = 0
    for seed_role, seed_candidates in build_dataset():
        role = Role(
            user_id=user.id,
            title=seed_role.title,
            description=seed_role.description,
        )
        role.requirements = [
            Requirement(
                label=req.label,
                weight=WEIGHT_VALUES[req.weight],
                aliases=list(req.aliases),
                position=position,
            )
            for position, req in enumerate(seed_role.requirements)
        ]
        db.add(role)
        db.flush()

        for cand in seed_candidates:
            candidate = Candidate(
                user_id=user.id,
                name=cand.name,
                email=cand.email,
                resume_text=cand.resume_text,
                source=cand.source,
                original_filename=cand.original_filename,
            )
            db.add(candidate)
            created += 1
        db.flush()

    return created


def seed_users(
    db: Session, *, email: str | None = None, reset: bool = False
) -> dict[str, int]:
    """Seed every account (or just ``email``). Commits once at the end."""
    target = email.strip().lower() if email else None
    report: dict[str, int] = {}
    for user in user_repo.list_all(db, email=target):
        report[user.email] = seed_user(db, user, reset=reset)
    db.commit()
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.seed",
        description="Give every recruiter their own copy of the demo dataset.",
    )
    parser.add_argument("--email", help="seed only this account")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete each account's existing seed data and rebuild",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        report = seed_users(db, email=args.email, reset=args.reset)
    finally:
        db.close()

    if not report:
        print("No matching users to seed.")
        return
    for addr, n in report.items():
        print(f"{addr}: {f'seeded {n} candidates' if n else 'already seeded'}")
