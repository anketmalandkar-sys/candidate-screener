"""Tests for the synthetic dataset (`app.seed.dataset`) and the loader (`app.seed.loader`).

The `build_dataset` tests need no database and are marked `no_db`. The loader
tests use the shared `_schema` / `clean_database` fixtures from conftest.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.seed.dataset import SEED_ROLE_TITLES, build_dataset

# --------------------------------------------------------------------------- #
# Pure dataset                                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.no_db
def test_build_dataset_is_deterministic():
    first = build_dataset()
    second = build_dataset()

    assert [role.title for role, _ in first] == [role.title for role, _ in second]

    names_first = [c.name for _, cands in first for c in cands]
    names_second = [c.name for _, cands in second for c in cands]
    assert names_first == names_second

    texts_first = [c.resume_text for _, cands in first for c in cands]
    texts_second = [c.resume_text for _, cands in second for c in cands]
    assert texts_first == texts_second


@pytest.mark.no_db
def test_dataset_is_large_and_well_shaped():
    data = build_dataset()

    assert len(data) >= 6
    assert {role.title for role, _ in data} == set(SEED_ROLE_TITLES)

    total_candidates = sum(len(cands) for _, cands in data)
    assert total_candidates >= 100

    all_names = [c.name for _, cands in data for c in cands]
    assert len(all_names) == len(set(all_names))  # no duplicate people

    for role, cands in data:
        assert 5 <= len(role.requirements) <= 7
        assert any(r.weight == "must" for r in role.requirements)
        assert 15 <= len(cands) <= 25
        for c in cands:
            assert c.resume_text.strip()
            assert c.source in ("paste", "upload")
            assert (c.original_filename is None) == (c.source == "paste")


# --------------------------------------------------------------------------- #
# Loader                                                                       #
# --------------------------------------------------------------------------- #


@pytest.fixture
def db(_schema):
    from app.repositories.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_user(db, email: str):
    from app.auth.security import hash_password
    from app.models import User

    user = User(email=email, name="Owner", password_hash=hash_password("Passw0rd!"))
    db.add(user)
    db.commit()
    return user


def _roles_for(db, user_id):
    from app.models import Role

    return {r.title for r in db.scalars(select(Role).where(Role.user_id == user_id))}


def test_seed_user_creates_the_dataset(db):
    from app.models import Candidate
    from app.seed import seed_user

    user = _make_user(db, "owner@example.com")
    created = seed_user(db, user)
    db.commit()

    assert created >= 100
    assert _roles_for(db, user.id) == set(SEED_ROLE_TITLES)
    assert (
        db.scalar(
            select(func.count())
            .select_from(Candidate)
            .where(Candidate.user_id == user.id)
        )
        == created
    )


def test_seed_user_is_idempotent(db):
    from app.models import Candidate, Role
    from app.seed import seed_user

    user = _make_user(db, "owner@example.com")
    seed_user(db, user)
    db.commit()

    roles_before = db.scalar(select(func.count()).select_from(Role))
    cands_before = db.scalar(select(func.count()).select_from(Candidate))

    assert seed_user(db, user) == 0
    db.commit()

    assert db.scalar(select(func.count()).select_from(Role)) == roles_before
    assert db.scalar(select(func.count()).select_from(Candidate)) == cands_before


def test_seed_user_reset_rebuilds_without_duplication(db):
    from app.models import Candidate, Role
    from app.seed import seed_user

    user = _make_user(db, "owner@example.com")
    seed_user(db, user)
    db.commit()
    roles_before = db.scalar(select(func.count()).select_from(Role))
    cands_before = db.scalar(select(func.count()).select_from(Candidate))

    seed_user(db, user, reset=True)
    db.commit()

    assert db.scalar(select(func.count()).select_from(Role)) == roles_before
    assert db.scalar(select(func.count()).select_from(Candidate)) == cands_before


def test_each_recruiter_gets_their_own_copy(db):
    from app.models import Role
    from app.seed import seed_users

    a = _make_user(db, "a@example.com")
    b = _make_user(db, "b@example.com")

    report = seed_users(db)

    assert set(report) == {"a@example.com", "b@example.com"}
    assert _roles_for(db, a.id) == set(SEED_ROLE_TITLES)
    assert _roles_for(db, b.id) == set(SEED_ROLE_TITLES)
    assert db.scalar(select(func.count()).select_from(Role)) == 2 * len(
        SEED_ROLE_TITLES
    )


def test_seed_users_can_target_one_email(db):
    from app.seed import seed_users

    a = _make_user(db, "a@example.com")
    b = _make_user(db, "b@example.com")

    seed_users(db, email="a@example.com")

    assert _roles_for(db, a.id) == set(SEED_ROLE_TITLES)
    assert _roles_for(db, b.id) == set()


def test_registration_seeds_when_enabled(client, register_user, monkeypatch):
    """The end-to-end path: SEED_DEMO_DATA=true → a fresh account has the pool."""
    from app.utilities.config import get_settings

    monkeypatch.setenv("SEED_DEMO_DATA", "true")
    get_settings.cache_clear()
    try:
        register_user()
        roles = client.get("/api/roles?limit=100").json()
        assert {r["title"] for r in roles["items"]} == set(SEED_ROLE_TITLES)
        assert client.get("/api/candidates").json()["total"] >= 100
    finally:
        monkeypatch.setenv("SEED_DEMO_DATA", "false")
        get_settings.cache_clear()
