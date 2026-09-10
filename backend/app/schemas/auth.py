"""Auth request/response models and the password policy."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.common import NonBlankStr

# Password policy: 8 to 10 characters, and at least one of each character class
# (lowercase, uppercase, digit, special).
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 10

# (name, predicate) for each class a password must contain at least one of. A
# "special" character is anything that is neither alphanumeric nor whitespace,
# which also means an all-whitespace password fails every class.
_PASSWORD_CHARACTER_CLASSES: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("a lowercase letter", str.islower),
    ("an uppercase letter", str.isupper),
    ("a digit", str.isdigit),
    ("a special character", lambda c: not c.isalnum() and not c.isspace()),
)


class RegisterRequest(BaseModel):
    email: EmailStr
    name: Annotated[NonBlankStr, Field(min_length=1, max_length=120)]
    password: Annotated[
        str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    ]

    @field_validator("password")
    @classmethod
    def password_has_every_character_class(cls, value: str) -> str:
        missing = [
            name
            for name, has_class in _PASSWORD_CHARACTER_CLASSES
            if not any(has_class(ch) for ch in value)
        ]
        if missing:
            raise ValueError("Password must contain " + ", ".join(missing))
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
