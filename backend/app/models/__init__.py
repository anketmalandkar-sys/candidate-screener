"""ORM entities.

Importing this package imports every entity module, so a single
``import app.models`` registers all mappers on ``Base.metadata`` (Alembic and
the test schema fixture rely on that). Entity modules reference each other by
string only and never import one another.
"""

from app.models.candidate import Candidate
from app.models.requirement import Requirement
from app.models.role import Role
from app.models.screening import (
    Comparison,
    ScreeningAgentRun,
    ScreeningFinding,
    ScreeningResult,
    ScreeningRun,
)
from app.models.user import User

__all__ = [
    "User",
    "Role",
    "Requirement",
    "Candidate",
    "ScreeningRun",
    "ScreeningResult",
    "ScreeningFinding",
    "ScreeningAgentRun",
    "Comparison",
]
