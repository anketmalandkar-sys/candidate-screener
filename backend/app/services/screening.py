"""Screening orchestration: create a run + its pending result rows, and shape
runs / results for the API. The heavy lifting runs in
``app.screening.coordinator`` as a background task.
"""

from __future__ import annotations

import asyncio
import hashlib

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    Candidate,
    Comparison,
    Role,
    ScreeningResult,
    ScreeningRun,
)
from app.repositories import screening as repo
from app.schemas.screening import RunCreate
from app.screening.providers import describe_configured, get_provider
from app.utilities.config import get_settings


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def start_run(db: Session, user_id: int, role, payload: RunCreate) -> ScreeningRun:
    """`role` is the owned Role (resolved by the router dependency)."""
    settings = get_settings()

    ids = list(dict.fromkeys(payload.candidate_ids))  # de-dup, keep order
    if len(ids) > settings.screening_max_batch:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"A screening run is limited to {settings.screening_max_batch} "
                f"candidates; you selected {len(ids)}."
            ),
        )

    found = repo.owned_candidates_by_id(db, user_id, ids)
    missing = [cid for cid in ids if cid not in found]
    if missing:
        # Reject the whole request — never quietly screen the subset we know.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "These candidate ids are not in your pool: "
                + ", ".join(str(m) for m in missing)
            ),
        )

    run = ScreeningRun(
        user_id=user_id,
        role_id=role.id,
        status="queued",
        provider=describe_configured(settings),
        models={},
        total=len(ids),
    )
    db.add(run)
    db.flush()

    for cid in ids:
        cand: Candidate = found[cid]
        db.add(
            ScreeningResult(
                run_id=run.id,
                candidate_id=cand.id,
                user_id=user_id,
                candidate_name=cand.name,
                status="pending",
                resume_sha256=_sha256(cand.resume_text),
            )
        )

    db.commit()
    db.refresh(run)
    return run


def rerun(db: Session, user_id: int, source: ScreeningRun, scope: str) -> ScreeningRun:
    rows = source.results
    if scope == "errored":
        ids = [r.candidate_id for r in rows if r.status == "error"]
    elif scope == "changed":
        current = {
            c.id: _sha256(c.resume_text)
            for c in repo.owned_candidates_by_id(
                db, user_id, [r.candidate_id for r in rows]
            ).values()
        }
        ids = [
            r.candidate_id
            for r in rows
            if current.get(r.candidate_id) != r.resume_sha256
        ]
    else:
        ids = [r.candidate_id for r in rows]

    if not ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Nothing to re-screen for scope '{scope}'.",
        )

    role = db.get(Role, source.role_id)
    return start_run(
        db, user_id, role, RunCreate(role_id=source.role_id, candidate_ids=ids)
    )


# --- serialisation ---------------------------------------------------------


def _counts(run: ScreeningRun) -> dict:
    # Prefer live row state (the coordinator persists each candidate as it
    # finishes) so the progress bar moves during a run; fall back to the stored
    # snapshot when the results collection is not loaded.
    rows = run.results if "results" in run.__dict__ else None
    if rows is not None:
        return {
            "total": run.total,
            "screened": sum(1 for r in rows if r.status == "screened"),
            "compromised": sum(1 for r in rows if r.is_compromised),
            "errored": sum(1 for r in rows if r.status == "error"),
        }
    return {
        "total": run.total,
        "screened": run.screened,
        "compromised": run.compromised,
        "errored": run.errored,
    }


def run_summary(run: ScreeningRun) -> dict:
    return {
        "id": run.id,
        "role_id": run.role_id,
        "status": run.status,
        "provider": run.provider or {},
        "models": run.models or {},
        "counts": _counts(run),
        "created_at": run.created_at,
        "completed_at": run.completed_at,
    }


def result_summary(result: ScreeningResult) -> dict:
    return {
        "candidate_id": str(result.candidate_id),
        "candidate_name": result.candidate_name,
        "status": result.status,
        "is_compromised": result.is_compromised,
        "overall_disposition": result.overall_disposition,
        "finding_count": len(result.findings),
    }


def run_detail(run: ScreeningRun) -> dict:
    return {
        **run_summary(run),
        "results": [
            result_summary(r) for r in sorted(run.results, key=lambda r: r.candidate_id)
        ],
    }


_SEV_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}


def _audit_dict(result: ScreeningResult | None) -> dict | None:
    if result is None:
        return None
    return {
        "candidate_id": str(result.candidate_id),
        "is_compromised": result.is_compromised,
        "overall_disposition": result.overall_disposition,
        "summary": result.summary,
        "findings": [
            {
                "category": f.category,
                "evidence": f.evidence,
                "reason": f.reason,
                "severity": f.severity,
            }
            for f in result.findings
        ],
    }


def create_comparison(
    db: Session, user_id: int, role: Role, a: Candidate, b: Candidate
) -> dict:
    if a.id == b.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Pick two different candidates.",
        )
    provider = get_provider(get_settings())
    audit_a = _audit_dict(repo.latest_screened_result(db, user_id, a.id))
    audit_b = _audit_dict(repo.latest_screened_result(db, user_id, b.id))

    async def _go():
        try:
            return await provider.compare(
                role_context={
                    "title": role.title,
                    "requirements": [r.label for r in role.requirements],
                },
                resume_a=a.resume_text,
                resume_b=b.resume_text,
                audit_a=audit_a,
                audit_b=audit_b,
                candidate_a_id=str(a.id),
                candidate_b_id=str(b.id),
            )
        finally:
            aclose = getattr(provider, "aclose", None)
            if aclose is not None:
                await aclose()

    result, call = asyncio.run(_go())

    surfaced = [
        f
        for audit in (audit_a, audit_b)
        if audit
        for f in audit["findings"]
        if _SEV_RANK.get(f.get("severity") or "info", 0) >= 2
    ]
    row = Comparison(
        user_id=user_id,
        role_id=role.id,
        candidate_a_id=a.id,
        candidate_b_id=b.id,
        result=result.model_dump(),
        findings_surfaced=surfaced,
        model=call.model,
        prompt_text=call.prompt_text,
        raw_response=call.raw_response,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return comparison_detail(row)


def comparison_detail(row: Comparison) -> dict:
    return {
        **(row.result or {}),
        "id": row.id,
        "role_id": row.role_id,
        "candidate_a_id": row.candidate_a_id,
        "candidate_b_id": row.candidate_b_id,
        "findings_surfaced": row.findings_surfaced or [],
        "model": row.model,
        "prompt_text": row.prompt_text,
        "raw_response": row.raw_response,
        "created_at": row.created_at,
    }


def list_comparisons(db: Session, user_id: int) -> list[dict]:
    return [comparison_detail(r) for r in repo.list_comparisons(db, user_id)]


def _agent_run_base(ar, candidate_name: str | None) -> dict:
    return {
        "id": ar.id,
        "candidate_id": str(ar.candidate_id),
        "candidate_name": candidate_name,
        "agent_name": ar.agent_name,
        "tier": ar.tier,
        "model": ar.model,
        "parsed_ok": ar.parsed_ok,
        "repair_attempts": ar.repair_attempts,
        "degraded": ar.degraded,
        "notes": ar.notes,
        "tool_call_count": len(ar.tool_calls or []),
        "latency_ms": ar.latency_ms,
        "input_chars": ar.input_chars,
        "created_at": ar.created_at,
    }


def agent_runs(
    db: Session, run_id: int, candidate_id: int, candidate_name: str | None
) -> list[dict]:
    """Per-candidate: metadata + the verbatim request and response."""
    return [
        {
            **_agent_run_base(ar, candidate_name),
            "prompt_text": ar.prompt_text,
            "raw_response": ar.raw_response,
            "tool_calls": ar.tool_calls or [],
        }
        for ar in repo.list_agent_runs(db, run_id, candidate_id)
    ]


def run_agent_runs(db: Session, run_id: int) -> list[dict]:
    """Run-wide: metadata only (the live activity feed)."""
    return [
        _agent_run_base(ar, name)
        for ar, name in repo.list_agent_runs_for_run(db, run_id)
    ]


def unified_audit(run: ScreeningRun, result: ScreeningResult) -> dict:
    return {
        "run_id": run.id,
        "result_id": result.id,
        "candidate_id": str(result.candidate_id),
        "candidate_name": result.candidate_name,
        "status": result.status,
        "resume_sha256": result.resume_sha256,
        "is_compromised": result.is_compromised,
        "overall_disposition": result.overall_disposition,
        "summary": result.summary,
        "agent_results": result.agent_results or [],
        "findings": [
            {
                "id": f.id,
                "category": f.category,
                "evidence": f.evidence,
                "reason": f.reason,
                "source": f.source,
                "severity": f.severity,
                "benign_explanation": f.benign_explanation,
                "confidence": f.confidence,
                "recommended_action": f.recommended_action,
                "pattern_key": f.pattern_key,
                "verified": f.verified,
            }
            for f in result.findings
        ],
        "degraded": (result.degraded.split(",") if result.degraded else []),
        "provider": run.provider or {},
        "models": result.models or {},
        "error": result.error,
        "created_at": result.created_at,
    }
