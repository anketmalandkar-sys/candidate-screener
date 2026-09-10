"""The candidate pool: résumé intake and retrieval."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_owned_candidate
from app.models import Candidate, User
from app.repositories import candidates as candidate_repo
from app.repositories.database import get_db
from app.schemas.candidate import (
    CandidateCreate,
    CandidatePoolDetail,
    CandidatePoolItem,
)
from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page
from app.services import candidates as candidate_service
from app.utilities.extract import MAX_UPLOAD_BYTES, ExtractionError, extract_text

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


@router.post(
    "",
    response_model=CandidatePoolItem,
    status_code=status.HTTP_201_CREATED,
)
def create_candidate(
    payload: CandidateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Add a résumé to the pool."""
    return candidate_service.create_candidate(
        db,
        user.id,
        name=payload.name,
        resume_text=payload.resume_text,
        email=payload.email,
    )


@router.post(
    "/upload",
    response_model=CandidatePoolItem,
    status_code=status.HTTP_201_CREATED,
)
async def upload_candidate(
    name: str = Form(...),
    email: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Candidate name must not be empty or only whitespace.",
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"That file is larger than the {limit_mb} MB limit.",
        )

    try:
        resume_text = extract_text(file.filename or "", data)
    except ExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return candidate_service.create_candidate(
        db,
        user.id,
        name=name,
        resume_text=resume_text,
        email=(email or "").strip() or None,
        source="upload",
        original_filename=file.filename,
    )


@router.get("", response_model=Page[CandidatePoolItem])
def list_candidates(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> dict:
    """The recruiter's pool, newest first, one page at a time."""
    items = [
        candidate_service.pool_item(c)
        for c in candidate_repo.list_pool(db, user.id, limit=limit, offset=offset)
    ]
    return {
        "items": items,
        "total": candidate_repo.count_pool(db, user.id),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{candidate_id}", response_model=CandidatePoolDetail)
def get_candidate(
    candidate: Candidate = Depends(get_owned_candidate),
) -> dict:
    return candidate_service.pool_detail(candidate)


@router.delete(
    "/{candidate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_candidate(
    candidate: Candidate = Depends(get_owned_candidate),
    db: Session = Depends(get_db),
) -> None:
    candidate_service.delete_candidate(db, candidate)
