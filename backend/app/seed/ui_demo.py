"""Populate one dev account end to end, for clicking through the UI.

This goes further than ``python -m app.seed`` (which only fills the roles and the
candidate pool): it also loads the screening fixture résumés and runs a few
screenings in ``stub`` mode, so the **Screening** section already has
``clear`` / ``review`` / ``high_concern`` / compromised results to look at
without waiting on any model calls.

    docker compose exec backend python -m app.seed.ui_demo
    docker compose exec backend python -m app.seed.ui_demo --email me@example.com --password 'S3cret!!'
    docker compose exec backend python -m app.seed.ui_demo --reset      # rebuild from scratch

This creates a normal account with a password you choose (default
``ui-demo@example.com`` / ``UiDemo123!``) — the same thing registering through
the form does. It does not weaken the "no seeded credentials" stance: nothing
here runs unless you ask for it, and the account has no special powers.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# The fixtures + this script never call a model. Force the deterministic
# provider regardless of what the container env says, before anything reads it.
os.environ["SCREENING_PROVIDER"] = "stub"

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models import Candidate, Role, User
from app.repositories.database import SessionLocal
from app.schemas.screening import RunCreate
from app.screening.coordinator import run_screening
from app.seed.loader import seed_user
from app.services import screening as screening_service
from app.utilities.config import get_settings

DEFAULT_EMAIL = "ui-demo@example.com"
DEFAULT_PASSWORD = "UiDemo123!"

# The fixtures are written against this role (see samples/ROLE.md); app.seed
# already creates it with the right requirements, so we reuse it.
SCREENING_ROLE_TITLE = "Senior Backend Engineer"

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "screening_fixtures"
_FIXTURE_PREFIX = "[fixture]"


def _find_or_create_user(db: Session, email: str, password: str) -> tuple[User, bool]:
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        return user, False
    user = User(email=email, name="UI Demo", password_hash=hash_password(password))
    db.add(user)
    db.flush()
    return user, True


def _fixture_files() -> list[Path]:
    """The 09–17 integrity fixtures plus the 01–08 clean samples."""
    top = sorted(FIXTURE_DIR.glob("[0-9][0-9]-*.txt"))
    samples = sorted((FIXTURE_DIR / "_samples").glob("*.txt"))
    return top + samples


def _load_fixture_candidates(db: Session, user_id: int) -> list[Candidate]:
    existing = {
        c.name: c
        for c in db.scalars(
            select(Candidate).where(
                Candidate.user_id == user_id,
                Candidate.name.like(f"{_FIXTURE_PREFIX}%"),
            )
        )
    }
    out: list[Candidate] = []
    for path in _fixture_files():
        # "09-derek-coleman.txt" -> "[fixture] 09 derek coleman"
        stem = path.stem.replace("-", " ")
        name = f"{_FIXTURE_PREFIX} {stem}"
        cand = existing.get(name)
        if cand is None:
            cand = Candidate(
                user_id=user_id,
                name=name,
                email=None,
                resume_text=path.read_text(encoding="utf-8"),
                source="paste",
                original_filename=None,
            )
            db.add(cand)
        out.append(cand)
    db.flush()
    return out


def _screen(db: Session, user_id: int, role: Role, candidates: list[Candidate]) -> int:
    payload = RunCreate(role_id=role.id, candidate_ids=[c.id for c in candidates])
    run = screening_service.start_run(db, user_id, role, payload)
    run_screening(run.id)  # synchronous, deterministic in stub mode
    return run.id


def _fixture_number(candidate: Candidate) -> str:
    """ "[fixture] 09 derek coleman" -> "09"."""
    return candidate.name.split()[1]


def build(email: str, password: str, *, reset: bool) -> None:
    get_settings()  # fails fast if APP_SECRET_KEY is missing

    db = SessionLocal()
    try:
        user, created = _find_or_create_user(db, email, password)
        db.commit()
        print(f"account:  {user.email}  ({'created' if created else 'reused'})")

        n = seed_user(db, user, reset=reset)
        db.commit()
        print(
            f"pool:     {'rebuilt' if reset else 'seeded'} — {n} demo candidates added"
        )

        fixtures = _load_fixture_candidates(db, user.id)
        db.commit()
        print(f"fixtures: {len(fixtures)} screening résumés in the pool")

        role = db.scalar(
            select(Role).where(
                Role.user_id == user.id, Role.title == SCREENING_ROLE_TITLE
            )
        )
        if role is None:
            print(
                f"! role {SCREENING_ROLE_TITLE!r} not found — skipping screening runs"
            )
            return

        integrity = [c for c in fixtures if _fixture_number(c) >= "09"]
        clean = [c for c in fixtures if _fixture_number(c) < "09"]

        run_a = _screen(db, user.id, role, integrity)
        print(f"run #{run_a}:  screened {len(integrity)} integrity fixtures (09–17)")
        run_b = _screen(db, user.id, role, clean)
        print(f"run #{run_b}:  screened {len(clean)} clean samples (01–08)")
    finally:
        db.close()

    print()
    print("Done. Start the frontend and log in:")
    print("  cd frontend && npm install && npm run dev   # http://localhost:5173")
    print(f"  email:    {email}")
    print(f"  password: {password}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.seed.ui_demo",
        description="Seed one dev account with roles, a candidate pool, the "
        "screening fixtures, and a couple of finished screening runs.",
    )
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="wipe this account's pool and rebuild everything",
    )
    args = parser.parse_args(argv)
    build(args.email, args.password, reset=args.reset)


if __name__ == "__main__":
    main()
