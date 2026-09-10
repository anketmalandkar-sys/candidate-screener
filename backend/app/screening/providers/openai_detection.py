"""Detection tier with the sub-agents on OpenAI (the default).

Sub-agents 1–3 (manipulation_guard, timeline_auditor, inflation_auditor) run as
tool-using agents on ``openai_subagent_model`` (default ``gpt-4.1-mini``),
calling the deterministic checks in ``app/screening/tools.py``. The
prompt-injection classifier stays an HF ``hf-inference`` task model — that call,
and the deterministic pre-scan, are unchanged and still the coverage backstop.

Everything except the two provider seams (``_chat`` / ``_classify_segment``) and
client construction is inherited from :class:`HFDetectionProvider`.
"""

from __future__ import annotations

import asyncio
import logging

from app.screening.providers._endpoint import resolve_endpoint
from app.screening.providers.hf_inference import HFDetectionProvider, _as_label_list

logger = logging.getLogger(__name__)


class OpenAIAgenticDetectionProvider(HFDetectionProvider):
    _tier = "openai"

    def __init__(self, settings, client=None, hf_client=None) -> None:
        self._settings = settings
        ep = resolve_endpoint(settings, "detection")
        # `_chat_model` truthy => detect() takes the agentic branch (never the
        # HF "pre-scan mode" branch).
        self._chat_model = ep.model

        if client is not None:
            self._openai = client
        else:
            from openai import AsyncOpenAI

            # base_url is always absolute here; api_key is None (not "") when
            # unset, which the SDK requires.
            self._openai = AsyncOpenAI(
                api_key=ep.api_key,
                base_url=ep.base_url,
                timeout=90,
            )

        # HF task client — only for the injection classifier (best effort).
        self._hf = hf_client
        if self._hf is None and getattr(settings, "hf_token", ""):
            try:
                from huggingface_hub import InferenceClient

                kwargs = {"token": settings.hf_token or None, "timeout": 60}
                if getattr(settings, "hf_bill_to", ""):
                    kwargs["bill_to"] = settings.hf_bill_to
                try:
                    self._hf = InferenceClient(provider="hf-inference", **kwargs)
                except TypeError:
                    self._hf = InferenceClient(**kwargs)
            except Exception:
                self._hf = None

    # -- provider seams --------------------------------------------------------

    async def _chat(self, messages, *, tools=None, response_format=None):
        kw: dict = {
            "model": self._chat_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 1200,
        }
        if tools is not None:
            kw["tools"] = tools
            kw["tool_choice"] = "auto"
        if response_format is not None:
            kw["response_format"] = response_format
        resp = await self._openai.chat.completions.create(**kw)
        return resp.choices[0].message

    async def _classify_segment(self, segment: str) -> list[dict]:
        if self._hf is None:
            raise RuntimeError("no HF token configured for the injection classifier")
        res = await asyncio.to_thread(
            lambda: self._hf.text_classification(
                segment, model=self._settings.hf_injection_model
            )
        )
        return _as_label_list(res)

    def describe(self) -> dict[str, str]:
        return {"detection": "openai_agentic"}

    async def aclose(self) -> None:
        for c in (getattr(self, "_openai", None), getattr(self, "_hf", None)):
            close = getattr(c, "close", None)
            if close is None:
                continue
            try:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass
