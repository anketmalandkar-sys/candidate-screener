"""Screening: start a run, watch it, read the per-candidate audit."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_owned_screening_run
from app.models import ScreeningRun, User
from app.repositories import candidates as candidate_repo
from app.repositories import roles as role_repo
from app.repositories import screening as repo
from app.repositories.database import get_db
from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page
from app.schemas.screening import (
    AgentRunOut,
    AgentRunSummary,
    ComparisonCreate,
    ComparisonDetail,
    RerunRequest,
    RunCreate,
    RunDetail,
    RunSummary,
    UnifiedCandidateAudit,
)
from app.screening.coordinator import run_screening
from app.services import screening as service

router = APIRouter(prefix="/api/screening", tags=["screening"])


@router.post("/runs", response_model=RunDetail, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: RunCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    role = role_repo.get_owned(db, payload.role_id, user.id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )
    run = service.start_run(db, user.id, role, payload)
    background.add_task(run_screening, run.id)
    db.refresh(run)
    return service.run_detail(run)


@router.get("/runs", response_model=Page[RunSummary])
def list_runs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> dict:
    runs = repo.list_runs(db, user.id, limit=limit, offset=offset)
    return {
        "items": [service.run_summary(r) for r in runs],
        "total": repo.count_runs(db, user.id),
        "limit": limit,
        "offset": offset,
    }


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run: ScreeningRun = Depends(get_owned_screening_run)) -> dict:
    return service.run_detail(run)


@router.post(
    "/runs/{run_id}/rerun",
    response_model=RunDetail,
    status_code=status.HTTP_201_CREATED,
)
def rerun_run(
    payload: RerunRequest,
    background: BackgroundTasks,
    run: ScreeningRun = Depends(get_owned_screening_run),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    new_run = service.rerun(db, user.id, run, payload.scope)
    background.add_task(run_screening, new_run.id)
    db.refresh(new_run)
    return service.run_detail(new_run)


@router.post(
    "/comparisons",
    response_model=ComparisonDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_comparison(
    payload: ComparisonCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    role = role_repo.get_owned(db, payload.role_id, user.id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )
    a = candidate_repo.get_owned(db, payload.candidate_a_id, user.id)
    b = candidate_repo.get_owned(db, payload.candidate_b_id, user.id)
    if a is None or b is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found"
        )
    return service.create_comparison(db, user.id, role, a, b)


@router.get("/comparisons", response_model=list[ComparisonDetail])
def list_comparisons(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    return service.list_comparisons(db, user.id)


@router.get("/comparisons/{comparison_id}", response_model=ComparisonDetail)
def get_comparison(
    comparison_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    row = repo.get_owned_comparison(db, comparison_id, user.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found"
        )
    return service.comparison_detail(row)


@router.get(
    "/runs/{run_id}/results/{candidate_id}", response_model=UnifiedCandidateAudit
)
def get_result(
    candidate_id: int,
    run: ScreeningRun = Depends(get_owned_screening_run),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    result = repo.get_result_for_candidate(db, run.id, candidate_id, user.id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No screening result for that candidate in this run",
        )
    return service.unified_audit(run, result)


@router.get("/runs/{run_id}/agent-runs", response_model=list[AgentRunSummary])
def get_run_agent_runs(
    run: ScreeningRun = Depends(get_owned_screening_run),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Every agent call for the run (metadata only) — the live "what are the
    agents doing" feed. Poll this while the run is still running."""
    return service.run_agent_runs(db, run.id)


@router.get(
    "/runs/{run_id}/results/{candidate_id}/agent-runs",
    response_model=list[AgentRunOut],
)
def get_agent_runs(
    candidate_id: int,
    run: ScreeningRun = Depends(get_owned_screening_run),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """The raw model request + response for each agent call on this candidate —
    kept as the audit-trail info behind the result."""
    result = repo.get_result_for_candidate(db, run.id, candidate_id, user.id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Result not found"
        )
    return service.agent_runs(db, run.id, candidate_id, result.candidate_name)
