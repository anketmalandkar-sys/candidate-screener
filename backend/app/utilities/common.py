"""Constants and helpers shared across layers: requirement weights and a UTC
clock. Kept dependency-free so any layer can import it."""

from __future__ import annotations

from datetime import UTC, datetime

# Requirement weights. Exposed to the API as the strings below; stored as small
# integers so the score arithmetic is plain and the ordering is obvious.
WEIGHT_NICE = 1
WEIGHT_IMPORTANT = 2
WEIGHT_MUST = 3

WEIGHT_LABELS = {
    WEIGHT_NICE: "nice",
    WEIGHT_IMPORTANT: "important",
    WEIGHT_MUST: "must",
}
WEIGHT_VALUES = {v: k for k, v in WEIGHT_LABELS.items()}


def utcnow() -> datetime:
    return datetime.now(UTC)
