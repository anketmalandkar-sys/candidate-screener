"""A pooled candidate: one resume, owned directly by the recruiter.

The recruiter owns a flat pool of candidates. A candidate carries a single
resume and is not attached to any role.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utilities.common import utcnow

if TYPE_CHECKING:
    from app.models.user import User


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The pool is owned directly by the recruiter. Authorisation is a single
    # filter on this column.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    resume_text: Mapped[str] = mapped_column(Text, nullable=False)
    # "paste" or "upload" — kept so the UI can show provenance and so we can
    # tell extraction bugs apart from bad pastes when debugging.
    source: Mapped[str] = mapped_column(String(16), default="paste", nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="candidates")
