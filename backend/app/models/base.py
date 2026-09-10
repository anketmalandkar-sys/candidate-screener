"""The SQLAlchemy declarative base every entity extends.

Kept in its own module so the entity files depend on nothing but this, and so
Alembic / the test schema fixture can reach ``Base.metadata`` without importing
the engine.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
