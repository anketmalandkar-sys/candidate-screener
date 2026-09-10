"""Pydantic request/response models (DTOs), one module per resource."""

from app.schemas.common import NonBlankStr, WeightLabel

__all__ = ["NonBlankStr", "WeightLabel"]
