"""Unit tests for the security primitives that the auth routes lean on.

These sit on the functions and the `LoginRateLimiter` class directly — the
route-level behaviour is covered in `test_auth.py`, this pins the pieces.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.security import (
    JWT_ALGORITHM,
    LoginRateLimiter,
    burn_timing,
    create_access_token,
    decode_access_token,
    hash_password,
    needs_rehash,
)
from app.utilities.config import get_settings

pytestmark = pytest.mark.no_db


# --------------------------------------------------------------------------
# needs_rehash — the transparent-upgrade hook
# --------------------------------------------------------------------------


def test_needs_rehash_is_false_for_a_current_hash():
    assert needs_rehash(hash_password("correct-horse-battery-staple")) is False


def test_needs_rehash_is_true_for_a_weaker_hash():
    """A hash written under cheaper Argon2 parameters must be flagged so the
    login route can silently re-hash it."""
    from argon2 import PasswordHasher

    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    assert needs_rehash(weak.hash("correct-horse-battery-staple")) is True


def test_needs_rehash_treats_an_unparseable_hash_as_needing_upgrade():
    assert needs_rehash("not-a-real-phc-string") is True


def test_burn_timing_returns_without_raising():
    burn_timing()  # must swallow the deliberate mismatch


# --------------------------------------------------------------------------
# decode_access_token — subject handling
# --------------------------------------------------------------------------


def _encode(payload: dict) -> str:
    return jwt.encode(payload, get_settings().app_secret_key, algorithm=JWT_ALGORITHM)


def test_token_with_a_non_numeric_subject_is_rejected():
    token = _encode(
        {"sub": "not-a-number", "exp": datetime.now(UTC) + timedelta(hours=1)}
    )
    assert decode_access_token(token) is None


def test_token_with_no_subject_is_rejected():
    token = _encode({"exp": datetime.now(UTC) + timedelta(hours=1)})
    assert decode_access_token(token) is None


def test_valid_token_returns_the_user_id_as_an_int():
    assert decode_access_token(create_access_token(7)) == 7


# --------------------------------------------------------------------------
# LoginRateLimiter — the sliding window
# --------------------------------------------------------------------------


def test_limiter_blocks_only_once_the_attempt_ceiling_is_reached():
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
    assert not limiter.is_blocked("k")

    limiter.record_failure("k")
    limiter.record_failure("k")
    assert not limiter.is_blocked("k")

    limiter.record_failure("k")
    assert limiter.is_blocked("k")


def test_limiter_blocks_if_any_supplied_key_is_over_the_ceiling():
    """The route checks the IP key and the email key together; either tipping
    over is enough to block."""
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60)
    limiter.record_failure("ip:1.2.3.4")
    limiter.record_failure("ip:1.2.3.4")

    assert limiter.is_blocked("ip:1.2.3.4", "email:someone@example.com")


def test_reset_clears_a_blocked_key():
    limiter = LoginRateLimiter(max_attempts=1, window_seconds=60)
    limiter.record_failure("k")
    assert limiter.is_blocked("k")

    limiter.reset("k")
    assert not limiter.is_blocked("k")


def test_failures_older_than_the_window_stop_counting(monkeypatch):
    """It is a sliding window, not a permanent lockout: an attacker spacing
    guesses further apart than the window is never blocked."""
    clock = {"now": 1_000.0}
    monkeypatch.setattr("app.auth.security.time.monotonic", lambda: clock["now"])

    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
    limiter.record_failure("k")
    limiter.record_failure("k")
    limiter.record_failure("k")
    assert limiter.is_blocked("k")

    clock["now"] += 61  # every recorded failure is now outside the window
    assert not limiter.is_blocked("k")
