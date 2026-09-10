"""Role and requirement business logic."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Requirement, Role
from app.repositories import roles as role_repo
from app.schemas.role import RequirementIn, RoleCreate, RoleUpdate
from app.utilities.common import WEIGHT_LABELS, WEIGHT_VALUES


def serialise(role: Role) -> dict:
    return {
        "id": role.id,
        "title": role.title,
        "description": role.description,
        "is_active": role.is_active,
        "created_at": role.created_at,
        "requirements": [
            {
                "id": req.id,
                "label": req.label,
                "weight": WEIGHT_LABELS[req.weight],
                "aliases": list(req.aliases or []),
                "position": req.position,
            }
            for req in role.requirements
        ],
    }


def _replace_requirements(
    db: Session, role: Role, incoming: list[RequirementIn]
) -> None:
    """Swap the role's requirement list for a new one.

    Replaced wholesale rather than diffed: the list is small and always edited
    as a whole.
    """
    for existing in list(role.requirements):
        db.delete(existing)
    db.flush()

    role.requirements = [
        Requirement(
            role_id=role.id,
            label=req.label.strip(),
            weight=WEIGHT_VALUES[req.weight],
            aliases=req.aliases,
            position=index,
        )
        for index, req in enumerate(incoming)
    ]
    db.flush()


def list_roles(
    db: Session,
    user_id: int,
    *,
    active: bool | None = None,
    limit: int,
    offset: int,
) -> dict:
    rows = role_repo.list_with_requirement_counts(
        db, user_id, active=active, limit=limit, offset=offset
    )
    return {
        "items": [
            {
                "id": role.id,
                "title": role.title,
                "description": role.description,
                "is_active": role.is_active,
                "created_at": role.created_at,
                "requirement_count": req_count,
            }
            for role, req_count in rows
        ],
        "total": role_repo.count_roles(db, user_id, active=active),
        "limit": limit,
        "offset": offset,
    }


def create_role(db: Session, user_id: int, payload: RoleCreate) -> dict:
    role = Role(
        user_id=user_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
    )
    db.add(role)
    db.flush()
    _replace_requirements(db, role, payload.requirements)
    db.commit()
    db.refresh(role)
    return serialise(role)


def update_role(db: Session, role: Role, payload: RoleUpdate) -> dict:
    if payload.title is not None:
        role.title = payload.title.strip()
    if payload.description is not None:
        role.description = payload.description.strip()
    if payload.is_active is not None:
        role.is_active = payload.is_active

    if payload.requirements is not None:
        _replace_requirements(db, role, payload.requirements)

    db.commit()
    db.refresh(role)
    return serialise(role)


def delete_role(db: Session, role: Role) -> None:
    db.delete(role)
    db.commit()
