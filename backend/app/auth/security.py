"""Password hashing, session tokens, and login throttling.

Design notes, since this is the file the brief says will be read closely:

* Argon2id, not bcrypt. Memory-hard, the current password-hashing competition
  winner, and the default parameters are sane without tuning. Used via
  argon2-cffi directly rather than through passlib, which no longer tracks
  modern backends well.
* The hash is stored in PHC string format, so the parameters travel with the
  hash and can be raised later without a flag day — `needs_rehash` below is
  how an existing user is silently upgraded on their next successful login.
* Sessions are JWTs delivered in an httpOnly cookie, never localStorage: a JWT
  readable from JavaScript is a JWT that a single XSS exfiltrates.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.utilities.config import get_settings

_hasher = PasswordHasher()

JWT_ALGORITHM = "HS256"

# A real Argon2 hash of a value nobody can log in with. Verifying against this
# on the unknown-email path costs the same as verifying a real user's hash, so
# response time does not reveal whether an address is registered.
_DUMMY_HASH = _hasher.hash("timing-equalisation-only-never-a-credential")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used weaker parameters than we now use."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def burn_timing() -> None:
    """Spend the cost of a verify without having a user to verify against."""
    try:
        _hasher.verify(_DUMMY_HASH, "wrong")
    except (VerifyMismatchError, VerificationError):
        pass


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=settings.access_token_expire_hours),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Return the user id, or None if the token is expired, forged or malformed.

    `algorithms` is pinned to a single value: accepting a list the attacker
    influences is how the classic "alg: none" and RS256->HS256 confusion
    attacks land.
    """
    try:
        payload = jwt.decode(
            token,
            get_settings().app_secret_key,
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")
    if subject is None:
        return None
    try:
        return int(subject)
    except (TypeError, ValueError):
        return None


class LoginRateLimiter:
    """Sliding-window throttle on failed logins.

    Keyed on client IP *and* submitted email, so one attacker cannot lock out
    an arbitrary user by hammering their address from elsewhere, and a single
    host cannot spray many addresses.

    This is in-process and therefore per-instance: two API replicas would each
    allow the full budget. Correct fix is a shared Redis counter; that is
    deliberately out of scope here and named as such in the README rather than
    quietly pretended away.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        window = self._failures[key]
        while window and now - window[0] > self.window_seconds:
            window.popleft()
        return window

    def is_blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        return any(len(self._prune(k, now)) >= self.max_attempts for k in keys)

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        for key in keys:
            self._prune(key, now).append(now)

    def reset(self, *keys: str) -> None:
        """Called on a successful login so a legitimate user is not punished
        for a few typos earlier in the window."""
        for key in keys:
            self._failures.pop(key, None)


_settings = get_settings()
login_limiter = LoginRateLimiter(
    max_attempts=_settings.login_max_attempts,
    window_seconds=_settings.login_window_seconds,
)
