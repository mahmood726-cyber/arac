"""RGS computation core.

For each (MA, Tier) pair, compute three orthogonal gap metrics:
1. Reproduction gap (binary): does the African-subset pool differ from the
   full pool by |delta| > 0.005? (Reuses Plan 1's published threshold.)
2. Precision gap (ratio): subset CI width / full CI width. Values >> 1
   indicate the subset is much less precise than the full pool.
3. Sign-flip (binary): does the subset pool's sign differ from the full pool?
   (Specifically: subset.pooled_estimate has different sign from full.)

INSUFFICIENT_DATA case: k_subset < 3 (Plan 1's invisibility threshold). All
metric fields return None to signal insufficient.

Plan 3A.1 will add Heterogeneity gap (τ² delta — needs REML) and
Recommendation-change (crosses MCID — needs per-condition MCID table).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arac.bridge import MARecord
from arac.repool import INVISIBILITY_THRESHOLD_K, PoolResult, repool_subset


_REPRODUCTION_THRESHOLD = 0.005  # |delta| > this → flagged non-reproducible (Plan 1)
_HETEROGENEITY_THRESHOLD = 0.25  # I² delta in absolute (proportion) terms


class RGSTier(Enum):
    SITE = "site"
    AUTHORSHIP = "authorship"
    PARTICIPANT = "participant"


@dataclass(frozen=True)
class RGSResult:
    """One row of the atlas: per-MA × per-Tier RGS computation."""
    ma_id: str
    tier: RGSTier
    k_total: int
    k_subset: int
    invisible: bool

    # Full-pool stats (always computed when MA has k>=2).
    full_pooled_estimate: Optional[float]
    full_se: Optional[float]
    full_ci_lower: Optional[float]
    full_ci_upper: Optional[float]
    full_tau2: Optional[float]             # REML τ² for full pool
    full_i2: Optional[float]              # I² for full pool

    # Subset-pool stats (None if invisible).
    subset_pooled_estimate: Optional[float]
    subset_se: Optional[float]
    subset_ci_lower: Optional[float]
    subset_ci_upper: Optional[float]
    subset_tau2: Optional[float]           # REML τ² for subset; None if invisible
    subset_i2: Optional[float]            # I² for subset; None if invisible

    # RGS metrics (None if invisible).
    reproduction_gap: Optional[bool]       # True if |subset - full| > 0.005
    precision_gap_ratio: Optional[float]   # subset_ci_width / full_ci_width
    sign_flip: Optional[bool]              # True if subset sign differs from full
    heterogeneity_gap: Optional[bool]      # True if |subset_i2 - full_i2| > 0.25


def _ci_width(pool: PoolResult) -> Optional[float]:
    if pool.ci_lower is None or pool.ci_upper is None:
        return None
    return pool.ci_upper - pool.ci_lower


def _same_sign(a: float, b: float) -> bool:
    """Return True if a and b have the same sign (both >= 0 or both < 0)."""
    return (a >= 0) == (b >= 0)


class RGSEngine:
    def compute(
        self,
        record: MARecord,
        tier: RGSTier,
        indices: tuple[int, ...],
    ) -> RGSResult:
        """Compute RGS for one (MA, Tier) pair given the trial-index subset."""
        full = repool_subset(record, tuple(range(record.k)))
        invisible = len(indices) < INVISIBILITY_THRESHOLD_K

        if invisible:
            return RGSResult(
                ma_id=record.ma_id,
                tier=tier,
                k_total=record.k,
                k_subset=len(indices),
                invisible=True,
                full_pooled_estimate=full.pooled_estimate,
                full_se=full.se,
                full_ci_lower=full.ci_lower,
                full_ci_upper=full.ci_upper,
                full_tau2=full.tau2,
                full_i2=full.i2,
                subset_pooled_estimate=None,
                subset_se=None,
                subset_ci_lower=None,
                subset_ci_upper=None,
                subset_tau2=None,
                subset_i2=None,
                reproduction_gap=None,
                precision_gap_ratio=None,
                sign_flip=None,
                heterogeneity_gap=None,
            )

        subset = repool_subset(record, indices)

        # Reproduction gap
        if (
            subset.pooled_estimate is None
            or full.pooled_estimate is None
        ):
            reproduction_gap: Optional[bool] = None
        else:
            reproduction_gap = (
                abs(subset.pooled_estimate - full.pooled_estimate)
                > _REPRODUCTION_THRESHOLD
            )

        # Precision gap ratio
        full_w = _ci_width(full)
        subset_w = _ci_width(subset)
        if full_w is None or subset_w is None or full_w == 0:
            precision_gap_ratio: Optional[float] = None
        else:
            precision_gap_ratio = subset_w / full_w

        # Sign flip
        if (
            subset.pooled_estimate is None
            or full.pooled_estimate is None
        ):
            sign_flip: Optional[bool] = None
        else:
            sign_flip = not _same_sign(
                subset.pooled_estimate, full.pooled_estimate
            )

        # Heterogeneity gap
        if full.i2 is None or subset.i2 is None:
            heterogeneity_gap: Optional[bool] = None
        else:
            heterogeneity_gap = abs(subset.i2 - full.i2) > _HETEROGENEITY_THRESHOLD

        return RGSResult(
            ma_id=record.ma_id,
            tier=tier,
            k_total=record.k,
            k_subset=len(indices),
            invisible=False,
            full_pooled_estimate=full.pooled_estimate,
            full_se=full.se,
            full_ci_lower=full.ci_lower,
            full_ci_upper=full.ci_upper,
            full_tau2=full.tau2,
            full_i2=full.i2,
            subset_pooled_estimate=subset.pooled_estimate,
            subset_se=subset.se,
            subset_ci_lower=subset.ci_lower,
            subset_ci_upper=subset.ci_upper,
            subset_tau2=subset.tau2,
            subset_i2=subset.i2,
            reproduction_gap=reproduction_gap,
            precision_gap_ratio=precision_gap_ratio,
            sign_flip=sign_flip,
            heterogeneity_gap=heterogeneity_gap,
        )
