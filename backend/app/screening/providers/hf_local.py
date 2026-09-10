"""Detection tier, fully local — no network.

Selected by ``SCREENING_DETECTION_BACKEND=hf_local``. Requires the optional
``hf-local`` dependencies (``pip install -r backend/requirements-hf-local.txt``);
if they are missing this module raises ``ImportError`` at construction and
``CompositeProvider`` falls back to pre-scan-only detection.

The classifier score is folded into the feature bundle; the sub-agents
themselves run the deterministic pre-scan (there is no local chat model by
default), so every ``IntegrityAuditResult`` here is ``degraded``.
"""

from __future__ import annotations

import logging
import threading

from app.schemas.screening import IntegrityAuditResult
from app.screening.agents import detectors
from app.screening.types import AgentCall, PrescanResult

logger = logging.getLogger(__name__)

_TIER = "hf"


class HFLocalDetectionProvider:
    def __init__(self, settings) -> None:
        # Import here so the base image (and stub-mode tests) never need torch.
        import transformers  # noqa: F401

        self._settings = settings
        self._lock = threading.Lock()
        self._injection = None

    def _injection_pipeline(self):
        if self._injection is None:
            with self._lock:
                if self._injection is None:
                    from transformers import pipeline

                    self._injection = pipeline(
                        "text-classification",
                        model=self._settings.hf_injection_model,
                        top_k=None,
                    )
        return self._injection

    async def aclose(self) -> None:
        self._injection = None

    async def detect(
        self,
        *,
        candidate_id: str,
        text: str,
        prescan: PrescanResult,
        role_context: dict,
    ) -> tuple[list[IntegrityAuditResult], list[AgentCall]]:
        note = None
        try:
            import asyncio

            scores = await asyncio.to_thread(
                lambda: self._injection_pipeline()(text[:2000])
            )
            top = _top_label(scores)
            if top and top[0].upper().startswith(("INJECT", "UNSAFE", "JAILBREAK")):
                note = f"local classifier: {top[0]} {top[1]:.2f}"
        except Exception as exc:
            logger.debug("local injection classifier failed: %s", exc)

        results: list[IntegrityAuditResult] = []
        calls: list[AgentCall] = []
        for spec in detectors.SPECS:
            res = detectors.fallback(spec.agent_name, prescan, candidate_id)
            results.append(res)
            calls.append(
                AgentCall(
                    agent_name=spec.agent_name,
                    tier=_TIER,
                    model="hf_local (pre-scan + local classifier)",
                    raw_response=res.model_dump_json(),
                    parsed_result=res.model_dump(),
                    parsed_ok=True,
                    degraded=True,
                    notes=note if spec.agent_name == "manipulation_guard" else None,
                    input_chars=len(text),
                )
            )
        return results, calls

    def describe(self) -> dict[str, str]:
        return {"detection": "hf_local"}


def _top_label(scores):
    try:
        flat = scores[0] if scores and isinstance(scores[0], list) else scores
        best = max(flat, key=lambda s: s["score"])
        return best["label"], float(best["score"])
    except Exception:
        return None
