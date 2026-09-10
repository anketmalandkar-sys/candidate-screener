"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth import router as auth_router
from app.routers.candidates import router as candidates_router
from app.routers.roles import router as roles_router
from app.routers.screening import router as screening_router
from app.utilities.config import get_settings


def _configure_logging() -> None:
    """Root stays quiet; our own package logs at INFO so screening's per-call
    request/response lines (SCREENING_LOG_PROMPTS, on by default) reach stdout."""
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("app").setLevel(logging.INFO)


_configure_logging()
settings = get_settings()

app = FastAPI(
    title="Candidate Screener",
    version="1.0.0",
    description=(
        "Rank applicants against an open role using deterministic, "
        "evidence-backed requirement matching."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Required for the session cookie to be sent on cross-origin XHR during
    # local development. Note that credentialed CORS forbids a "*" origin, so
    # the list above is explicit by necessity as well as by choice.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(roles_router)
app.include_router(candidates_router)
app.include_router(screening_router)


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
