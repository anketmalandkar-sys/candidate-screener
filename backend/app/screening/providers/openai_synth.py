"""Synthesis tier on OpenAI: Agent 4 (aggregation) and Agent 5 (comparison).

Structured Outputs guarantee schema shape; the JSON ladder is kept for provider
variance and for a local OpenAI-compatible server. On exhaustion, Agent 4 falls
back to deterministic assembly (``degraded``) — the candidate is never dropped.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time

from app.schemas.screening import (
    ComparativeAnalysisResult,
    IntegrityAuditResult,
    UnifiedCandidateAudit,
)
from app.screening.agents import synthesizer
from app.screening.agents.prompts import comparison_user_message, synthesis_user_message
from app.screening.assembly import assemble_unified
from app.screening.jsonio import parse_json, run_ladder
from app.screening.providers._endpoint import resolve_endpoint
from app.screening.types import AgentCall, PrescanResult

logger = logging.getLogger(__name__)

_TIER = "openai"
_NUM_SCORE_RE = re.compile(
    r"\b(?:score|rating|rank)\D{0,12}\b\d{1,3}(?:\.\d+)?\b", re.I
)


class OpenAISynthesisProvider:
    def __init__(self, settings, client=None, describe_fn=None) -> None:
        self._settings = settings
        ep = resolve_endpoint(settings, "synthesis")
        if client is not None:
            self._client = client
        else:
            from openai import AsyncOpenAI

            # Pass base_url explicitly (always absolute) so a stray empty
            # OPENAI_BASE_URL env var — which the SDK would otherwise read and
            # choke on — can't win. api_key is None (not "") when unset.
            self._client = AsyncOpenAI(
                api_key=ep.api_key,
                base_url=ep.base_url,
                timeout=90,
            )
        self._model = ep.model
        # Set by CompositeProvider so the persisted record names the tiers that
        # actually ran; falls back to the configured backend names.
        self._describe_fn = describe_fn

    async def aclose(self) -> None:
        try:
            await self._client.close()
        except Exception:
            pass

    def describe(self) -> dict[str, str]:
        return {"synthesis": "openai"}

    async def _chat(self, system: str, user: str, extra: str | None) -> str:
        # JSON mode, not strict json_schema: our output models carry open maps
        # (provider/models dicts) and nullable enums that OpenAI's strict schema
        # rejects. gpt-4.1 follows the schema described in the system prompt
        # reliably in JSON mode, and the JSON ladder + normalisers coerce the
        # rest — falling back to deterministic assembly if all else fails.
        messages = [
            {
                "role": "system",
                "content": system + "\nRespond with a single JSON object.",
            },
            {"role": "user", "content": user},
        ]
        if extra:
            messages.append({"role": "user", "content": extra})
        if getattr(self._settings, "screening_log_prompts", False):
            logger.info(
                "OpenAI request [%s]:\n%s",
                self._model,
                "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages),
            )
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        if getattr(self._settings, "screening_log_prompts", False):
            logger.info(
                "OpenAI response [%s]:\n%s", getattr(resp, "model", self._model), raw
            )
        else:
            logger.info(
                "OpenAI call [%s] ok, %d chars in / %d out",
                getattr(resp, "model", self._model),
                sum(len(m["content"]) for m in messages),
                len(raw),
            )
        return raw

    # -- Agent 4 --------------------------------------------------------------

    async def synthesize(
        self,
        *,
        run_id: int,
        candidate_id: str,
        candidate_name: str,
        resume_sha256: str,
        text: str,
        audits: list[IntegrityAuditResult],
        prescan: PrescanResult,
    ) -> tuple[UnifiedCandidateAudit, AgentCall]:
        user = synthesis_user_message(
            candidate_id=candidate_id,
            candidate_name=candidate_name,
            text=text,
            audit_results=[a.model_dump() for a in audits],
            pattern_keys=[h.pattern_key for h in prescan.hits],
            role_context={},
        )
        started = time.monotonic()

        async def _call(extra: str | None) -> str:
            return await self._chat(synthesizer.SYNTHESIS_SYSTEM, user, extra)

        try:
            parsed, raw, attempts = await run_ladder(
                _call, synthesizer.SynthesisModelOutput
            )
        except Exception as exc:
            logger.warning("openai synthesis failed: %s", exc)
            parsed, raw, attempts = None, f"error: {exc}", 0

        provider = (
            self._describe_fn()
            if self._describe_fn
            else {
                "detection": getattr(
                    self._settings, "screening_detection_backend", "openai_agentic"
                ),
                "synthesis": getattr(
                    self._settings, "screening_synthesis_backend", "openai"
                ),
            }
        )
        models = {"synthesizer": self._model}

        if parsed is not None:
            unified = synthesizer.normalise_unified(
                parsed.model_dump(),
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                resume_sha256=resume_sha256,
                audits=audits,
                provider=provider,
                models=models,
            )
            degraded = False
            note = None
        else:
            pk = {h.evidence.strip(): h.pattern_key for h in prescan.hits}
            unified = assemble_unified(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                resume_sha256=resume_sha256,
                audits=audits,
                degraded=["synthesizer"],
                provider=provider,
                models=models,
                pattern_key_by_evidence=pk,
            )
            degraded = True
            note = "json_ladder_exhausted"

        prompt_text = synthesizer.SYNTHESIS_SYSTEM + "\n\n---\n\n" + user
        call = AgentCall(
            agent_name="synthesizer",
            tier=_TIER,
            model=self._model,
            prompt_sha256=hashlib.sha256(prompt_text.encode()).hexdigest(),
            prompt_text=prompt_text,
            raw_response=raw,
            parsed_result=unified.model_dump(mode="json"),
            parsed_ok=parsed is not None,
            repair_attempts=attempts,
            degraded=degraded,
            notes=note,
            latency_ms=int((time.monotonic() - started) * 1000),
            input_chars=len(text),
        )
        return unified, call

    # -- Agent 5 --------------------------------------------------------------

    async def compare(
        self,
        *,
        role_context: dict,
        resume_a: str,
        resume_b: str,
        audit_a: dict | None,
        audit_b: dict | None,
        candidate_a_id: str,
        candidate_b_id: str,
    ) -> tuple[ComparativeAnalysisResult, AgentCall]:
        user = comparison_user_message(
            role_context=role_context,
            a_id=candidate_a_id,
            b_id=candidate_b_id,
            resume_a=resume_a,
            resume_b=resume_b,
            audit_a=audit_a,
            audit_b=audit_b,
        )
        started = time.monotonic()

        async def _call(extra: str | None) -> str:
            return await self._chat(synthesizer.COMPARISON_SYSTEM, user, extra)

        attempts = 0
        raw = await _call(None)
        # No-numeric-score rule: one targeted retry if a score slipped in.
        if _NUM_SCORE_RE.search(raw):
            attempts += 1
            raw = await _call(
                "Remove every numeric score, rating or rank number. Explain the "
                "ordering in words only."
            )

        data = parse_json(raw)
        # Retry once if we could not read a dimensions list out of it.
        if data is None or not synthesizer._coerce_dimensions(data):
            attempts += 1
            raw = await _call(
                "Return ONLY the JSON object with the exact keys given, and make "
                "`comparisons` a JSON array of dimension objects."
            )
            data = parse_json(raw)

        if data is not None:
            result = synthesizer.normalise_comparison(
                data, candidate_a_id, candidate_b_id
            )
            parsed_ok = bool(result.comparisons)
        else:
            result = ComparativeAnalysisResult(
                higher_ranked_id=candidate_a_id,
                lower_ranked_id=candidate_b_id,
                decision_summary=(
                    "The comparison model did not return a usable result; review "
                    "both candidates' audits directly."
                ),
                comparisons=[],
            )
            parsed_ok = False

        call = AgentCall(
            agent_name="comparative_reasoner",
            tier=_TIER,
            model=self._model,
            prompt_text=synthesizer.COMPARISON_SYSTEM + "\n\n---\n\n" + user,
            raw_response=raw,
            parsed_result=result.model_dump(),
            parsed_ok=parsed_ok,
            repair_attempts=attempts,
            latency_ms=int((time.monotonic() - started) * 1000),
            input_chars=len(resume_a) + len(resume_b),
        )
        return result, call
