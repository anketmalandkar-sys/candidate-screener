"""The recruiter account — owner of every role and candidate."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utilities.common import utcnow

if TYPE_CHECKING:
    from app.models.candidate import Candidate
    from app.models.role import Role


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored lowercased so uniqueness is genuinely case-insensitive without
    # depending on the citext extension being installed.
    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    roles: Mapped[list["Role"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    # The recruiter's candidate pool. Owned directly (not via a role), so a
    # candidate can sit here linked to no role at all.
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
