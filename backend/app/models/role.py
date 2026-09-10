"""An open role the recruiter is hiring for."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utilities.common import utcnow

if TYPE_CHECKING:
    from app.models.requirement import Requirement
    from app.models.user import User


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # A role starts active on creation; deactivating it hides it from the "active
    # roles" view without deleting anything, and it can be reactivated later.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="roles")
    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
        order_by="Requirement.position",
    )
