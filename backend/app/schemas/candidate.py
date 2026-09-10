"""Candidate-pool request/response models.

A candidate is a pool entry owned by the recruiter. It carries one resume and
nothing else — candidates are not attached to roles.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import NonBlankStr


class CandidateCreate(BaseModel):
    name: Annotated[NonBlankStr, Field(min_length=1, max_length=200)]
    email: EmailStr | None = None
    resume_text: Annotated[str, Field(min_length=1, max_length=100_000)]


class CandidatePoolItem(BaseModel):
    """One row of the candidate pool list."""

    id: int
    name: str
    email: str | None
    source: str
    original_filename: str | None
    created_at: datetime


class CandidatePoolDetail(BaseModel):
    id: int
    name: str
    email: str | None
    source: str
    original_filename: str | None
    created_at: datetime
    resume_text: str
