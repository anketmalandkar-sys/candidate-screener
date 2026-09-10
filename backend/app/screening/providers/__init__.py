"""Provider selection.

``get_provider`` reads the settings and returns the object the coordinator
drives. In ``stub`` mode (the test default) both tiers are the deterministic
``StubProvider`` and no network client is ever constructed. Otherwise a
``CompositeProvider`` wires the configured detection + synthesis backends; if it
cannot be built (missing SDK / bad config) ``live`` falls back to the stub with
a logged warning rather than 500-ing a run.
"""

from __future__ import annotations

import logging

from app.screening.providers.base import Provider
from app.screening.providers.stub import StubProvider

logger = logging.getLogger(__name__)


def describe_configured(settings) -> dict[str, str]:
    """The detection/synthesis backend names from config alone — no client is
    constructed. ``coordinator._run`` overwrites this with ``provider.describe()``
    (the tiers that actually ran) once the run starts."""
    if not settings.screening_is_live:
        return {"detection": "stub", "synthesis": "stub"}
    return {
        "detection": settings.screening_detection_backend,
        "synthesis": settings.screening_synthesis_backend,
    }


def get_provider(settings) -> Provider:
    if not settings.screening_is_live:
        return StubProvider()

    detection = settings.screening_detection_backend
    synthesis = settings.screening_synthesis_backend
    if detection == "stub" and synthesis == "stub":
        return StubProvider()

    try:
        from app.screening.providers.composite import CompositeProvider

        return CompositeProvider(settings)
    except Exception:
        logger.exception(
            "could not build the live provider (detection=%s, synthesis=%s); "
            "falling back to the stub provider",
            detection,
            synthesis,
        )
        return StubProvider()
