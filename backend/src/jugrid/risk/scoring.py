"""From an indicator value to a 0-1 score and a level, and from scores to an asset's risk."""

import math
from collections.abc import Mapping

from jugrid.risk.hazards import HAZARDS, LEVEL_BOUNDS, VULNERABILITY, AssetKind, Hazard, Level


def hazard_score(hazard: Hazard, value: float | None) -> float | None:
    """Where ``value`` sits between the hazard's low and high marks, clipped to 0-1."""
    if value is None or math.isnan(value):
        return None
    spec = HAZARDS[hazard]
    span = spec.high - spec.low
    return min(1.0, max(0.0, (value - spec.low) / span))


def asset_score(kind: AssetKind, hazard: Hazard, value: float | None) -> float | None:
    """The hazard's score weighted by how much that hazard hurts this kind of asset."""
    score = hazard_score(hazard, value)
    if score is None:
        return None
    return round(score * VULNERABILITY[kind][hazard], 4)


def overall_score(scores: Mapping[Hazard, float | None]) -> float | None:
    """An asset fails on its worst hazard, so the overall score is the highest one."""
    known = [s for s in scores.values() if s is not None]
    return max(known) if known else None


def level(score: float | None) -> Level | None:
    if score is None:
        return None
    for bound, name in LEVEL_BOUNDS:
        if score < bound:
            return name
    return Level.VERY_HIGH
