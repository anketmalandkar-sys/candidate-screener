"""A single scored criterion attached to a role."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utilities.common import WEIGHT_MUST

if TYPE_CHECKING:
    from app.models.role import Role


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=WEIGHT_MUST, nullable=False)
    # Recruiter-editable synonyms. This is the escape hatch that keeps a
    # deterministic matcher honest: when the rules miss a phrasing, a human
    # fixes it here in seconds and the fix is visible to the next reader.
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    role: Mapped["Role"] = relationship(back_populates="requirements")

    __table_args__ = (
        CheckConstraint("weight BETWEEN 1 AND 3", name="ck_requirement_weight_range"),
    )
