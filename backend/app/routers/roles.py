"""Role and requirement management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_owned_role
from app.models import Role, User
from app.repositories.database import get_db
from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page
from app.schemas.role import RoleCreate, RoleDetail, RoleSummary, RoleUpdate
from app.services import roles as role_service

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("", response_model=Page[RoleSummary])
def list_roles(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    active: bool | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> dict:
    return role_service.list_roles(
        db, user.id, active=active, limit=limit, offset=offset
    )


@router.post("", response_model=RoleDetail, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return role_service.create_role(db, user.id, payload)


@router.get("/{role_id}", response_model=RoleDetail)
def get_role(role: Role = Depends(get_owned_role)) -> dict:
    return role_service.serialise(role)


@router.patch("/{role_id}", response_model=RoleDetail)
def update_role(
    payload: RoleUpdate,
    role: Role = Depends(get_owned_role),
    db: Session = Depends(get_db),
) -> dict:
    return role_service.update_role(db, role, payload)


@router.delete(
    "/{role_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
def delete_role(
    role: Role = Depends(get_owned_role), db: Session = Depends(get_db)
) -> None:
    role_service.delete_role(db, role)
