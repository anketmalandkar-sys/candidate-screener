"""Registration, login, logout, and the current-session endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import SESSION_COOKIE_NAME, get_current_user
from app.auth.security import create_access_token, login_limiter
from app.models import User
from app.repositories.database import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut
from app.services.auth import EmailTakenError, authenticate
from app.services.auth import register as register_user
from app.utilities.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# One message for every failure mode. Saying "no such account" would turn the
# login form into a free membership oracle for any email list.
GENERIC_LOGIN_ERROR = "Invalid email or password"


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate limiting.

    X-Forwarded-For is trusted only as far as TRUSTED_PROXY_COUNT says it should
    be. Blindly reading the leftmost entry would let a caller spoof the header
    and reset their own throttle on every request.
    """
    settings = get_settings()
    if settings.trusted_proxy_count > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if len(hops) >= settings.trusted_proxy_count:
            return hops[-settings.trusted_proxy_count]
    return request.client.host if request.client else "unknown"


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        # Unreadable from JavaScript, so an XSS cannot exfiltrate the session.
        httponly=True,
        # Lax still sends the cookie on top-level navigation but not on
        # cross-site subrequests, which is what blocks form-based CSRF here.
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.access_token_expire_hours * 3600,
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, response: Response, db: Session = Depends(get_db)
) -> User:
    try:
        user = register_user(db, payload)
    except EmailTakenError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        ) from None
    _set_session_cookie(response, create_access_token(user.id))
    return user


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    email = payload.email.strip().lower()
    ip_key = f"ip:{_client_ip(request)}"
    email_key = f"email:{email}"

    if login_limiter.is_blocked(ip_key, email_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again in a few minutes.",
        )

    user = authenticate(db, email, payload.password)
    if user is None:
        login_limiter.record_failure(ip_key, email_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR
        )

    login_limiter.reset(ip_key, email_key)
    _set_session_cookie(response, create_access_token(user.id))
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
