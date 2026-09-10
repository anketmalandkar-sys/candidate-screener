"""Wire a detection backend and a synthesis backend into one Provider.

Constructed once per run by ``get_provider`` when ``SCREENING_PROVIDER=live``.
Network clients are created here and closed via ``aclose()`` (the coordinator
calls it in a ``finally``).

Adding a backend is one entry in ``_DETECTION_BUILDERS`` / ``_SYNTHESIS_BUILDERS``
plus its module. An unknown backend name degrades that tier to the stub (the
candidate is still screened) rather than raising.
"""

from __future__ import annotations

import logging

from app.screening.providers.stub import StubProvider

logger = logging.getLogger(__name__)


class CompositeProvider:
    def __init__(self, settings) -> None:
        self._settings = settings
        self._stub = StubProvider()
        self._detection = self._build_detection(settings)
        self._synthesis = self._build_synthesis(settings)

    # -- construction -------------------------------------------------------------

    def _build_detection(self, settings):
        name = settings.screening_detection_backend
        builder = self._DETECTION_BUILDERS.get(name)
        if builder is None:
            logger.warning(
                "unknown SCREENING_DETECTION_BACKEND %r; using pre-scan-only "
                "detection.",
                name,
            )
            return self._stub
        return builder(self, settings)

    def _build_synthesis(self, settings):
        name = settings.screening_synthesis_backend
        builder = self._SYNTHESIS_BUILDERS.get(name)
        if builder is None:
            logger.warning(
                "unknown SCREENING_SYNTHESIS_BACKEND %r; synthesis will be "
                "deterministic assembly.",
                name,
            )
            return self._stub
        return builder(self, settings)

    # -- detection builders -----------------------------------------------------

    def _det_openai_agentic(self, settings):
        has_key = bool(
            getattr(settings, "openai_api_key", "")
            or getattr(settings, "screening_detection_api_key", "")
        )
        if has_key:
            from app.screening.providers.openai_detection import (
                OpenAIAgenticDetectionProvider,
            )

            return OpenAIAgenticDetectionProvider(settings)
        # No key for the detection chat tier — fall back to HF (pre-scan unless a
        # routed chat model is configured). The candidate is still screened.
        logger.warning(
            "openai_agentic detection needs an API key (OPENAI_API_KEY or "
            "SCREENING_DETECTION_API_KEY); falling back to hf_inference."
        )
        from app.screening.providers.hf_inference import HFDetectionProvider

        return HFDetectionProvider(settings)

    def _det_hf_inference(self, settings):
        from app.screening.providers.hf_inference import HFDetectionProvider

        return HFDetectionProvider(settings)

    def _det_hf_local(self, settings):
        try:
            from app.screening.providers.hf_local import HFLocalDetectionProvider

            return HFLocalDetectionProvider(settings)
        except ImportError:
            logger.warning(
                "hf_local backend not available; using pre-scan-only detection."
            )
            return self._stub

    def _det_stub(self, settings):
        return self._stub

    # -- synthesis builders ---------------------------------------------------

    def _syn_openai(self, settings):
        from app.screening.providers.openai_synth import OpenAISynthesisProvider

        # describe_fn is a bound method evaluated lazily at synthesize() time, by
        # which point both tiers are constructed — so the persisted record names
        # the tiers that actually ran.
        return OpenAISynthesisProvider(settings, describe_fn=self.describe)

    def _syn_stub(self, settings):
        return self._stub

    _DETECTION_BUILDERS = {
        "openai_agentic": _det_openai_agentic,
        "hf_inference": _det_hf_inference,
        "hf_local": _det_hf_local,
        "stub": _det_stub,
    }
    _SYNTHESIS_BUILDERS = {
        "openai": _syn_openai,
        "stub": _syn_stub,
    }

    # -- delegation ---------------------------------------------------------------

    def describe(self) -> dict[str, str]:
        return {
            "detection": self._detection.describe().get("detection", "stub"),
            "synthesis": self._synthesis.describe().get("synthesis", "stub"),
        }

    async def detect(self, **kwargs):
        return await self._detection.detect(**kwargs)

    async def synthesize(self, **kwargs):
        return await self._synthesis.synthesize(**kwargs)

    async def compare(self, **kwargs):
        return await self._synthesis.compare(**kwargs)

    async def aclose(self) -> None:
        for obj in (self._detection, self._synthesis):
            close = getattr(obj, "aclose", None)
            if close is not None:
                await close()
