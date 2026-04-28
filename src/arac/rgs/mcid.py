"""Minimum Clinically Important Difference (MCID) infrastructure.

Per ARAC spec §3 step 4: recommendation-change is flagged when the African-
subset pool's CI lands in a different equivalence-zone state than the full
pool's CI. The equivalence zone is [−MCID, +MCID].

States:
- BENEFIT: CI entirely below −MCID (effect is clinically meaningful + protective)
- HARM: CI entirely above +MCID (effect is clinically meaningful + harmful)
- UNCERTAIN: CI overlaps the equivalence zone (no confident clinical claim)

MCID defaults are placeholders; Plan 4's preregistration locks per-condition
values that override these defaults via a per-MA MCID CSV.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional


# Defaults per data_type (absolute values — interpreted as ±MCID equivalence zone).
# All on the natural pooling scale (log scale for binary/giv; raw for continuous).
DEFAULT_MCID_BY_DATA_TYPE: dict[str, float] = {
    "binary": abs(math.log(0.80)),       # ≈ 0.2231 — 20% relative reduction is "important"
    "continuous": 0.2,                    # Cohen's small SMD
    "giv": abs(math.log(0.85)),           # ≈ 0.1625 — conservative for HR/RR
}


class RecommendationState(Enum):
    BENEFIT = "benefit"
    UNCERTAIN = "uncertain"
    HARM = "harm"


def mcid_for_data_type(data_type: str) -> float:
    """Return the default MCID (absolute) for a data type. Raises KeyError if
    the type is unknown — Plan 1's three types are the only supported set."""
    return DEFAULT_MCID_BY_DATA_TYPE[data_type]


def classify_ci_vs_mcid(
    ci_lower: Optional[float],
    ci_upper: Optional[float],
    mcid: float,
) -> Optional[RecommendationState]:
    """Classify a CI against the equivalence zone [−mcid, +mcid].

    Returns None if either bound is None (insufficient data).
    """
    if ci_lower is None or ci_upper is None:
        return None
    if ci_upper < -mcid:
        return RecommendationState.BENEFIT
    if ci_lower > mcid:
        return RecommendationState.HARM
    return RecommendationState.UNCERTAIN
