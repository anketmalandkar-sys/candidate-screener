"""Pydantic primitives shared by more than one resource."""

from __future__ import annotations

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel

WeightLabel = Literal["nice", "important", "must"]

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """One page of a listing plus the total number of rows available.

    `offset`/`limit` echo the request so the client can render "showing 21–40
    of 137" without tracking them itself.
    """

    items: list[T]
    total: int
    limit: int
    offset: int


def _reject_blank(value: str) -> str:
    """`min_length=1` counts spaces; this rejects a value that is empty once
    trimmed, so a name or title cannot be stored as "" after the route strips
    it."""
    if not value.strip():
        raise ValueError("must not be empty or only whitespace")
    return value


# A required free-text field that must carry at least one non-space character.
NonBlankStr = Annotated[str, AfterValidator(_reject_blank)]
