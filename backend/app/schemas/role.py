"""Role and requirement request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import NonBlankStr, WeightLabel


class RequirementIn(BaseModel):
    label: Annotated[str, Field(min_length=1, max_length=120)]
    weight: WeightLabel = "must"
    aliases: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list)

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, values: list[str]) -> list[str]:
        # Drop blanks and de-duplicate case-insensitively, preserving order.
        seen: set[str] = set()
        cleaned: list[str] = []
        for raw in values:
            alias = raw.strip()
            if alias and alias.lower() not in seen:
                seen.add(alias.lower())
                cleaned.append(alias)
        return cleaned


class RequirementOut(BaseModel):
    id: int
    label: str
    weight: WeightLabel
    aliases: list[str]
    position: int


# The description field holds a full job description, so it needs room for one.
JD_MAX_LENGTH = 20_000


class RoleCreate(BaseModel):
    title: Annotated[NonBlankStr, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=JD_MAX_LENGTH)] = ""
    requirements: list[RequirementIn] = Field(default_factory=list, max_length=40)


class RoleUpdate(BaseModel):
    title: Annotated[NonBlankStr, Field(min_length=1, max_length=200)] | None = None
    description: Annotated[str, Field(max_length=JD_MAX_LENGTH)] | None = None
    is_active: bool | None = None
    # When present, this REPLACES the role's requirement list wholesale.
    requirements: list[RequirementIn] | None = Field(default=None, max_length=40)


class RoleSummary(BaseModel):
    id: int
    title: str
    description: str
    is_active: bool
    created_at: datetime
    requirement_count: int


class RoleDetail(BaseModel):
    id: int
    title: str
    description: str
    is_active: bool
    created_at: datetime
    requirements: list[RequirementOut]
