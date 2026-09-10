"""Per-run orchestration.

Owns the two structural invariants:

* **one row per candidate** — the service pre-creates a ``pending``
  ``ScreeningResult`` for every selected candidate; this module only ever
  *updates* those rows (to ``screened`` or ``error``), and asserts the count at
  the end.
* **full audit trail** — every provider call returns ``AgentCall`` records that
  are written to ``screening_agent_runs`` whether the candidate succeeded or
  errored.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Candidate,
    Role,
    ScreeningAgentRun,
    ScreeningFinding,
    ScreeningResult,
    ScreeningRun,
)
from app.repositories.database import SessionLocal
from app.schemas.screening import EnrichedFinding, UnifiedCandidateAudit
from app.screening.assembly import disposition_for
from app.screening.prescan import run_prescan
from app.screening.providers import get_provider
from app.screening.types import AgentCall
from app.screening.verifier import coverage_check, scan_for_canary, verify_audit
from app.utilities.common import utcnow
from app.utilities.config import get_settings

logger = logging.getLogger(__name__)


def _role_context(role: Role) -> dict:
    return {
        "title": role.title,
        "description": role.description,
        "requirements": [r.label for r in role.requirements],
    }


def _persist_agent_runs(
    db: Session, run_id: int, candidate_id: int, result_id: int, calls: list[AgentCall]
) -> None:
    for c in calls:
        db.add(
            ScreeningAgentRun(
                run_id=run_id,
                candidate_id=candidate_id,
                result_id=result_id,
                agent_name=c.agent_name,
                tier=c.tier,
                model=c.model,
                prompt_sha256=c.prompt_sha256,
                prompt_text=c.prompt_text,
                raw_response=c.raw_response,
                parsed_result=c.parsed_result,
                tool_calls=c.tool_calls,
                parsed_ok=c.parsed_ok,
                repair_attempts=c.repair_attempts,
                degraded=c.degraded,
                notes=c.notes,
                latency_ms=c.latency_ms,
                input_chars=c.input_chars,
            )
        )


async def _screen_one(
    provider,
    role_context: dict,
    run_id: int,
    *,
    candidate_id: int,
    candidate_name: str,
    text: str,
    resume_sha256: str,
) -> tuple[UnifiedCandidateAudit | None, list[AgentCall], str | None]:
    """Pure: runs the pipeline for one candidate from plain data (no DB session
    touched, so this is safe to ``asyncio.gather``). Returns
    (unified, all_agent_calls, error). Never raises for an expected failure."""
    calls: list[AgentCall] = []
    cid = str(candidate_id)
    try:
        prescan = run_prescan(text)

        audits, detect_calls = await provider.detect(
            candidate_id=cid,
            text=text,
            prescan=prescan,
            role_context=role_context,
        )
        calls.extend(detect_calls)

        verified = []
        for audit in audits:
            cleaned, notes = verify_audit(audit, text)
            verified.append(cleaned)
            if notes:
                for c in calls:
                    if c.agent_name == audit.agent_name:
                        c.notes = "; ".join(filter(None, [c.notes, *notes]))
        audits = verified

        audits, coverage_notes = coverage_check(prescan, audits)

        canary_notes = scan_for_canary([c.raw_response for c in calls])

        unified, synth_call = await provider.synthesize(
            run_id=run_id,
            candidate_id=cid,
            candidate_name=candidate_name,
            resume_sha256=resume_sha256,
            text=text,
            audits=audits,
            prescan=prescan,
        )
        canary_notes += scan_for_canary([synth_call.raw_response])
        calls.append(synth_call)

        if canary_notes:
            # An agent's output tripped the canary check, so it was quarantined.
            # Record that as a high-severity finding and re-derive the disposition.
            synth_call.notes = "; ".join(
                filter(None, [synth_call.notes, *canary_notes])
            )
            quarantine_finding = EnrichedFinding(
                category="PROMPT_INJECTION",
                evidence="[screening model output]",
                reason=(
                    "The canary check tripped — an agent's output showed signs "
                    "of following an instruction from the resume. Its output was "
                    "quarantined; treat the audit with caution."
                ),
                source="manipulation_guard",
                severity="high",
                benign_explanation=(
                    "None — this is an internal integrity failure, not a "
                    "candidate signal."
                ),
                recommended_action="human_read — re-run this candidate.",
                verified=True,
            )
            findings = [*unified.findings, quarantine_finding]
            unified = unified.model_copy(
                update={
                    "is_compromised": True,
                    "findings": findings,
                    "overall_disposition": disposition_for(findings),
                }
            )

        if coverage_notes:
            # A synthesised injection flag may not have flowed through the
            # synthesis model — make sure the record reflects it.
            unified = unified.model_copy(update={"is_compromised": True})

        return unified, calls, None
    except Exception as exc:
        # not take down the run, and the failure must be recorded, not swallowed.
        logger.exception("screening failed for candidate %s", candidate_id)
        return None, calls, f"screening did not complete: {exc}"


def _write_result(
    db: Session,
    result: ScreeningResult,
    unified: UnifiedCandidateAudit | None,
    calls: list[AgentCall],
    error: str | None,
) -> None:
    _persist_agent_runs(db, result.run_id, result.candidate_id, result.id, calls)

    if error is not None or unified is None:
        result.status = "error"
        result.error = error or "screening did not complete"
        result.overall_disposition = None
        return

    result.status = "screened"
    result.is_compromised = unified.is_compromised
    result.overall_disposition = unified.overall_disposition
    result.summary = unified.summary
    result.agent_results = [a.model_dump() for a in unified.agent_results]
    result.degraded = ",".join(unified.degraded) or None
    result.models = unified.models
    for f in unified.findings:
        db.add(
            ScreeningFinding(
                result_id=result.id,
                category=f.category,
                evidence=f.evidence,
                reason=f.reason,
                source=f.source,
                severity=f.severity,
                benign_explanation=f.benign_explanation,
                confidence=f.confidence,
                recommended_action=f.recommended_action,
                pattern_key=f.pattern_key,
                verified=f.verified,
            )
        )


def _persist_one_sync(
    result_id: int,
    unified: UnifiedCandidateAudit | None,
    calls: list[AgentCall],
    error: str | None,
) -> None:
    """Write ONE candidate's outcome in its own short-lived session, called as
    soon as that candidate finishes — so the UI sees progress and per-agent
    activity mid-scan. Independent sessions are fine; a shared one is not."""
    db: Session = SessionLocal()
    try:
        result = db.get(ScreeningResult, result_id)
        if result is None:
            return
        _write_result(db, result, unified, calls, error)
        db.commit()
    except Exception:
        logger.exception("failed to persist result %s", result_id)
        db.rollback()
    finally:
        db.close()


async def _run(run_id: int) -> None:
    settings = get_settings()
    provider = get_provider(settings)

    db: Session = SessionLocal()
    try:
        run = db.get(ScreeningRun, run_id)
        if run is None:
            return
        run.status = "running"
        run.provider = provider.describe()
        db.commit()

        role = db.get(Role, run.role_id)
        role_context = _role_context(role) if role else {}

        result_rows = list(
            db.scalars(select(ScreeningResult).where(ScreeningResult.run_id == run_id))
        )
        candidates = {
            c.id: c
            for c in db.scalars(
                select(Candidate).where(
                    Candidate.id.in_([r.candidate_id for r in result_rows])
                )
            )
        }

        # Snapshot plain data so the concurrent coroutines touch no session.
        jobs = []
        for r in result_rows:
            cand = candidates.get(r.candidate_id)
            jobs.append(
                {
                    "result_id": r.id,
                    "candidate_id": r.candidate_id,
                    "candidate_name": cand.name if cand else r.candidate_name,
                    "text": cand.resume_text if cand else "",
                    "resume_sha256": r.resume_sha256,
                    "missing": cand is None,
                }
            )

        sem = asyncio.Semaphore(max(1, settings.screening_concurrency))

        async def _process(job: dict) -> None:
            async with sem:
                if job["missing"]:
                    unified, calls, error = None, [], "candidate no longer exists"
                else:
                    unified, calls, error = await _screen_one(
                        provider,
                        role_context,
                        run_id,
                        candidate_id=job["candidate_id"],
                        candidate_name=job["candidate_name"],
                        text=job["text"],
                        resume_sha256=job["resume_sha256"],
                    )
            # Persist THIS candidate immediately, in its own session, so the UI
            # sees the result row + its agent-run rows the moment it finishes.
            await asyncio.to_thread(
                _persist_one_sync, job["result_id"], unified, calls, error
            )

        await asyncio.gather(*(_process(j) for j in jobs))

        db.expire_all()  # the workers committed; re-read below

        # Invariant: one finalised row per selected candidate.
        rows = list(
            db.scalars(select(ScreeningResult).where(ScreeningResult.run_id == run_id))
        )
        for r in rows:
            if r.status == "pending":
                r.status = "error"
                r.error = "screening did not complete for this candidate"

        run.screened = sum(1 for r in rows if r.status == "screened")
        run.errored = sum(1 for r in rows if r.status == "error")
        run.compromised = sum(1 for r in rows if r.is_compromised)
        run.status = "partial" if run.errored else "complete"
        run.completed_at = utcnow()
        db.commit()
    except Exception:
        logger.exception("screening run %s failed", run_id)
        db.rollback()
        run = db.get(ScreeningRun, run_id)
        if run is not None:
            run.status = "failed"
            run.error = "the screening run could not be completed"
            run.completed_at = utcnow()
            db.commit()
    finally:
        db.close()
        aclose = getattr(provider, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:
                logger.debug("provider aclose failed", exc_info=True)


def run_screening(run_id: int) -> None:
    """Sync entrypoint for FastAPI ``BackgroundTasks``."""
    asyncio.run(_run(run_id))
