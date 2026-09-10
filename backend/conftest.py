"""Test configuration.

Environment is set before any application module is imported, so
`app.utilities.config.get_settings()` sees a real secret key rather than tripping its own
boot check. Application imports happen lazily inside fixtures so that tests
marked `no_db` still run with no database and no third-party dependencies:

    python3 -m pytest -m no_db

## Database isolation

The suite TRUNCATEs every table between test cases, so it must never point at a
database anyone cares about. `DATABASE_URL` is rewritten below — unconditionally
— to a sibling database whose name ends in `_test`, which is created on demand.
`clean_database` refuses to run against anything else. Override with
`TEST_DATABASE_URL` for CI.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

os.environ.setdefault("APP_SECRET_KEY", "test-only-secret-key-not-used-in-any-real-env")
# The suite registers many users; auto-seeding each with ~120 candidates would
# wreck both runtime and every count assertion. Force it off regardless of .env.
os.environ["SEED_DEMO_DATA"] = "false"

# The suite never makes model calls — force stub screening regardless of what
# the container env says. The one exception is the live smoke: run it with
# RUN_LIVE_SMOKE=1 (plus SCREENING_PROVIDER=live and real keys) and this leaves
# the ambient config alone.
if not os.environ.get("RUN_LIVE_SMOKE"):
    os.environ["SCREENING_PROVIDER"] = "stub"


def _isolated_test_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit

    dev = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://screener:screener@db:5432/candidate_screener",
    )
    parts = urlsplit(dev)
    name = parts.path.lstrip("/") or "candidate_screener"
    if not name.endswith("_test"):
        name = f"{name}_test"
    return urlunsplit(parts._replace(path=f"/{name}"))


# Unconditional on purpose: DATABASE_URL is normally already set (docker-compose
# points it at the dev database), and a `setdefault` here would leave the whole
# suite — TRUNCATE and all — aimed at it.
os.environ["DATABASE_URL"] = _isolated_test_url()

import pytest  # noqa: E402


def _ensure_test_database() -> None:
    """Create the isolated test database if it does not exist yet."""
    from sqlalchemy import create_engine, text

    parts = urlsplit(os.environ["DATABASE_URL"])
    target = parts.path.lstrip("/")
    admin_engine = create_engine(
        urlunsplit(parts._replace(path="/postgres")), isolation_level="AUTOCOMMIT"
    )
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target}
            ).scalar()
            if not exists:
                try:
                    conn.execute(text(f'CREATE DATABASE "{target}"'))
                except Exception:
                    # A parallel worker may have won the race — fine if it now exists.
                    still_missing = not conn.execute(
                        text("SELECT 1 FROM pg_database WHERE datname = :n"),
                        {"n": target},
                    ).scalar()
                    if still_missing:
                        raise
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def _schema():
    """Create the test database and its schema. Safe to run repeatedly."""
    _ensure_test_database()

    from app import models  # noqa: F401  — registers every feature's mappers
    from app.models.base import Base
    from app.repositories.database import engine

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(autouse=True)
def clean_database(request):
    """Truncate between tests.

    Deliberately not the join-an-outer-transaction trick: the routes under test
    call commit() themselves, and a savepoint-based fixture quietly changes
    what commit() means. Truncation tests the code as it actually runs.

    `_schema` is resolved lazily rather than taken as a parameter: requesting it
    up front would open a connection even for `no_db` tests, which would break
    running the pure scoring suite with no database available.
    """
    if "no_db" in request.keywords:
        yield
        return

    request.getfixturevalue("_schema")

    from sqlalchemy import text

    from app.models.base import Base
    from app.repositories.database import engine

    # Belt and braces: never TRUNCATE anything but an explicit *_test database,
    # whatever DATABASE_URL happens to say.
    if not (engine.url.database or "").endswith("_test"):
        raise RuntimeError(
            f"Refusing to truncate {engine.url.database!r}: the suite only runs "
            "against a database whose name ends with '_test'. Check DATABASE_URL "
            "/ TEST_DATABASE_URL."
        )

    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """The limiter is a process-wide singleton; stop tests leaking into each other."""
    try:
        from app.auth.security import login_limiter
    except Exception:
        yield
        return
    login_limiter._failures.clear()
    yield
    login_limiter._failures.clear()


@pytest.fixture
def client(_schema):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def register_user(client):
    """Register an account and return (credentials, user payload).

    Each call uses a fresh address so tests never collide on the unique index.
    """
    counter = {"n": 0}

    def _register(password: str = "Passw0rd!"):
        counter["n"] += 1
        creds = {
            "email": f"recruiter{counter['n']}@example.com",
            "name": f"Recruiter {counter['n']}",
            "password": password,
        }
        response = client.post("/api/auth/register", json=creds)
        assert response.status_code == 201, response.text
        return creds, response.json()

    return _register
