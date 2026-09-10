"""Auth tests.

The brief says the login will be inspected, so these assert the properties that
inspection would look for: real hashing, no credential literals, no account
enumeration, expiry and signature actually enforced, and hard tenant isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.utilities.config import get_settings

# 9 chars, and one of each required class: uppercase, lowercase, digit, special.
GOOD_PASSWORD = "Passw0rd!"


# --------------------------------------------------------------------------
# Hashing
# --------------------------------------------------------------------------


@pytest.mark.no_db
def test_password_hash_is_argon2id_and_not_the_password():
    digest = hash_password(GOOD_PASSWORD)
    assert digest.startswith("$argon2id$")
    assert GOOD_PASSWORD not in digest


@pytest.mark.no_db
def test_hash_is_salted_so_equal_passwords_differ():
    assert hash_password(GOOD_PASSWORD) != hash_password(GOOD_PASSWORD)


@pytest.mark.no_db
def test_verify_accepts_correct_and_rejects_wrong_password():
    digest = hash_password(GOOD_PASSWORD)
    assert verify_password(GOOD_PASSWORD, digest)
    assert not verify_password("something else entirely", digest)


@pytest.mark.no_db
def test_verify_on_a_garbage_hash_returns_false_rather_than_raising():
    assert not verify_password(GOOD_PASSWORD, "not-a-hash")


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------


@pytest.mark.no_db
def test_token_round_trips():
    assert decode_access_token(create_access_token(42)) == 42


@pytest.mark.no_db
def test_expired_token_is_rejected():
    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": "42",
            "iat": datetime.now(UTC) - timedelta(hours=10),
            "exp": datetime.now(UTC) - timedelta(hours=2),
        },
        settings.app_secret_key,
        algorithm="HS256",
    )
    assert decode_access_token(expired) is None


@pytest.mark.no_db
def test_token_signed_with_another_key_is_rejected():
    forged = jwt.encode(
        {
            "sub": "42",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        "an-attacker-supplied-signing-key",
        algorithm="HS256",
    )
    assert decode_access_token(forged) is None


@pytest.mark.no_db
def test_unsigned_alg_none_token_is_rejected():
    """The classic JWT downgrade. `algorithms` is pinned, so this must fail."""
    unsigned = jwt.encode({"sub": "42"}, key="", algorithm="none")
    assert decode_access_token(unsigned) is None


@pytest.mark.no_db
def test_tampered_token_is_rejected():
    token = create_access_token(42)
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    assert decode_access_token(tampered) is None


@pytest.mark.no_db
def test_malformed_token_is_rejected():
    assert decode_access_token("nonsense") is None
    assert decode_access_token("") is None


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------


def test_register_logs_the_user_in_and_sets_a_hardened_cookie(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "name": "New", "password": GOOD_PASSWORD},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "new@example.com"
    # The password must never come back out of the API.
    assert "password" not in response.text.lower()

    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header


def _register(client, password: str, email: str):
    return client.post(
        "/api/auth/register",
        json={"email": email, "name": "Person", "password": password},
    )


def test_registration_rejects_a_short_password(client):
    # 7 chars, below the 8 minimum, even though it has every character class.
    assert _register(client, "Aa1!aaa", "short@example.com").status_code == 422


def test_registration_rejects_a_password_over_ten_characters(client):
    # 11 chars, every class present — only the length cap is violated.
    assert _register(client, "Passw0rd!xy", "long-pw@example.com").status_code == 422


def test_registration_rejects_a_password_missing_a_digit(client):
    assert _register(client, "Password!", "nodigit@example.com").status_code == 422


def test_registration_rejects_a_password_missing_a_special_character(client):
    assert _register(client, "Password12", "nospecial@example.com").status_code == 422


def test_registration_rejects_a_password_missing_an_uppercase_letter(client):
    assert _register(client, "passw0rd!", "noupper@example.com").status_code == 422


def test_registration_rejects_a_password_missing_a_lowercase_letter(client):
    assert _register(client, "PASSW0RD!", "nolower@example.com").status_code == 422


def test_registration_accepts_an_eight_character_password_with_every_class(client):
    assert _register(client, "Passw0r!", "min-ok@example.com").status_code == 201


def test_registration_accepts_a_ten_character_password_with_every_class(client):
    assert _register(client, "Passw0rd!x", "max-ok@example.com").status_code == 201


def test_registration_rejects_a_malformed_email(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "name": "Nope", "password": GOOD_PASSWORD},
    )
    assert response.status_code == 422


def test_registration_rejects_a_whitespace_only_name(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "blank@example.com", "name": "   ", "password": GOOD_PASSWORD},
    )
    assert response.status_code == 422


def test_registration_rejects_an_overlong_name(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "long@example.com",
            "name": "n" * 121,
            "password": GOOD_PASSWORD,
        },
    )
    assert response.status_code == 422


def test_registration_rejects_an_all_whitespace_password(client):
    # Eight spaces: within the length window, but carries no character class.
    assert _register(client, "        ", "ws@example.com").status_code == 422


def test_duplicate_email_is_rejected(client, register_user):
    creds, _ = register_user()
    response = client.post("/api/auth/register", json=creds)
    assert response.status_code == 409


def test_email_uniqueness_is_case_insensitive(client):
    payload = {"email": "Mixed@Example.com", "name": "Mixed", "password": GOOD_PASSWORD}
    assert client.post("/api/auth/register", json=payload).status_code == 201

    payload["email"] = "mixed@example.com"
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_stored_hash_is_argon2_not_the_password(client, register_user):
    """Read the row back out of the database and look at it directly."""
    from sqlalchemy import select

    from app.models import User
    from app.repositories.database import SessionLocal

    creds, _ = register_user()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == creds["email"]))

    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert creds["password"] not in user.password_hash


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------


def test_login_then_me_round_trip(client, register_user):
    creds, _ = register_user()
    client.post("/api/auth/logout")

    response = client.post(
        "/api/auth/login", json={"email": creds["email"], "password": creds["password"]}
    )
    assert response.status_code == 200

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == creds["email"]


def test_login_is_case_insensitive_on_email(client, register_user):
    creds, _ = register_user()
    response = client.post(
        "/api/auth/login",
        json={"email": creds["email"].upper(), "password": creds["password"]},
    )
    assert response.status_code == 200


def test_unknown_email_and_wrong_password_are_indistinguishable(client, register_user):
    """No account enumeration: identical status and identical body."""
    creds, _ = register_user()

    wrong_password = client.post(
        "/api/auth/login",
        json={"email": creds["email"], "password": "wrong-password-here"},
    )
    unknown_email = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password-here"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_logout_clears_the_session(client, register_user):
    register_user()
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_logout_without_a_session_is_a_no_op(client):
    assert client.post("/api/auth/logout").status_code == 204


def test_x_forwarded_for_does_not_partition_the_login_throttle(client, register_user):
    """With no trusted proxy configured the header is ignored for rate-limit
    keying, so an attacker cannot rotate it to buy fresh attempts."""
    creds, _ = register_user()
    settings = get_settings()

    statuses = []
    for i in range(settings.login_max_attempts + 2):
        statuses.append(
            client.post(
                "/api/auth/login",
                json={"email": creds["email"], "password": "wrong-guess"},
                headers={"X-Forwarded-For": f"10.0.0.{i}"},
            ).status_code
        )

    assert statuses[-1] == 429


def test_me_requires_authentication(client):
    assert client.get("/api/auth/me").status_code == 401


def test_a_forged_session_cookie_is_refused(client):
    client.cookies.set("session", create_access_token(999_999))
    # Signature is valid but no such user exists.
    assert client.get("/api/auth/me").status_code == 401


def test_rate_limiter_blocks_after_repeated_failures(client, register_user):
    creds, _ = register_user()
    settings = get_settings()

    statuses = [
        client.post(
            "/api/auth/login", json={"email": creds["email"], "password": "wrong-guess"}
        ).status_code
        for _ in range(settings.login_max_attempts + 2)
    ]

    assert statuses[0] == 401
    assert statuses[-1] == 429


def test_rate_limit_blocks_even_a_correct_password(client, register_user):
    """Otherwise the throttle is trivially bypassed once a guess lands."""
    creds, _ = register_user()
    settings = get_settings()

    for _ in range(settings.login_max_attempts):
        client.post(
            "/api/auth/login", json={"email": creds["email"], "password": "wrong-guess"}
        )

    response = client.post(
        "/api/auth/login", json={"email": creds["email"], "password": creds["password"]}
    )
    assert response.status_code == 429


def test_successful_login_resets_the_failure_count(client, register_user):
    creds, _ = register_user()

    for _ in range(3):
        client.post(
            "/api/auth/login", json={"email": creds["email"], "password": "typo"}
        )

    assert (
        client.post(
            "/api/auth/login",
            json={"email": creds["email"], "password": creds["password"]},
        ).status_code
        == 200
    )

    from app.auth.security import login_limiter

    assert not login_limiter.is_blocked(f"email:{creds['email']}")


# --------------------------------------------------------------------------
# Tenant isolation
# --------------------------------------------------------------------------


def test_protected_routes_require_authentication(client):
    for method, path in [
        ("get", "/api/roles"),
        ("post", "/api/roles"),
        ("get", "/api/roles/1"),
        ("get", "/api/candidates"),
        ("get", "/api/candidates/1"),
    ]:
        response = getattr(client, method)(
            path, **({"json": {}} if method == "post" else {})
        )
        assert response.status_code == 401, f"{method.upper()} {path}"


def test_one_recruiter_cannot_see_anothers_role(client, register_user):
    """404, not 403 — a 403 would confirm the id exists."""
    register_user()
    role_id = client.post(
        "/api/roles", json={"title": "Private Role", "requirements": []}
    ).json()["id"]

    creds_b, _ = register_user()  # registering also switches the session cookie

    assert client.get(f"/api/roles/{role_id}").status_code == 404
    assert (
        client.patch(f"/api/roles/{role_id}", json={"title": "Hijacked"}).status_code
        == 404
    )
    assert client.delete(f"/api/roles/{role_id}").status_code == 404


def test_one_recruiter_cannot_see_anothers_candidate(client, register_user):
    register_user()
    candidate_id = client.post(
        "/api/candidates",
        json={"name": "Priya", "resume_text": "Python engineer"},
    ).json()["id"]

    register_user()

    assert client.get(f"/api/candidates/{candidate_id}").status_code == 404
    assert client.delete(f"/api/candidates/{candidate_id}").status_code == 404


def test_role_list_is_scoped_to_the_current_recruiter(client, register_user):
    register_user()
    client.post("/api/roles", json={"title": "Role A", "requirements": []})
    assert len(client.get("/api/roles").json()["items"]) == 1

    register_user()
    assert client.get("/api/roles").json()["items"] == []
