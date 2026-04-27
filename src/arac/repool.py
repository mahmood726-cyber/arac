"""Repool engine — computes pooled effect on an arbitrary trial-index subset.

Methodology: inverse-variance fixed-effect, identical to
repro-floor-atlas v0.1.0 (precision_floor._pool_fixed_effect). Vendored
inline (8 lines) so the smoke regression bit-matches the published atlas.csv.

REML+HKSJ+PI is the methodologically stronger choice for ARAC's per-tier
pooling question and is planned as the Plan 3 production pooler — fixed-effect
will be retained as a sensitivity cross-check. See Plan 1 architecture note for
the spec-deviation flag.

Invisibility rule (per ARAC spec §3): k_subset < 3 → flagged INVISIBLE for the
caller's tier. The repool still computes if k_subset >= 2 (math defined),
but the INVISIBLE flag is what the RGS layer (Plan 3) reads to gate
recommendation-change/sign-flip metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

# Import MARecord first — this triggers bridge._rfa_src_dir() which inserts
# repro-floor-atlas/src onto sys.path, making repro_floor_atlas importable.
from arac.bridge import MARecord

# These imports rely on sys.path being patched by bridge above.
from repro_floor_atlas import _metaaudit_path  # noqa: F401  (ensures metaaudit on sys.path)
from metaaudit.recompute import compute_log_or, compute_md
from repro_floor_atlas.loader import (
    BinaryTrials,
    ContinuousTrials,
    GIVTrials,
    MAInputs,
)


INVISIBILITY_THRESHOLD_K = 3  # per ARAC spec §3 step 4


@dataclass(frozen=True)
class PoolResult:
    ma_id: str
    k_subset: int
    invisible: bool                   # k_subset < INVISIBILITY_THRESHOLD_K
    pooled_estimate: Optional[float]  # None if subset is too small to pool at all (k<2)
    se: Optional[float]
    ci_lower: Optional[float]
    ci_upper: Optional[float]
    tau2: Optional[float]             # None for fixed-effect; populated by Plan 3's REML pooler


def _slice_inputs(inputs: MAInputs, indices: tuple[int, ...]) -> MAInputs:
    """Return a new MAInputs containing only the trials at the given indices."""
    idx = np.asarray(indices, dtype=int)
    if inputs.binary is not None:
        b = inputs.binary
        sliced = BinaryTrials(
            e_cases=b.e_cases[idx], e_n=b.e_n[idx],
            c_cases=b.c_cases[idx], c_n=b.c_n[idx],
        )
        return MAInputs(
            ma_id=inputs.ma_id, review_id=inputs.review_id,
            analysis_number=inputs.analysis_number, k=len(idx),
            data_type=inputs.data_type, binary=sliced,
        )
    if inputs.continuous is not None:
        c = inputs.continuous
        sliced = ContinuousTrials(
            e_mean=c.e_mean[idx], e_sd=c.e_sd[idx], e_n=c.e_n[idx],
            c_mean=c.c_mean[idx], c_sd=c.c_sd[idx], c_n=c.c_n[idx],
        )
        return MAInputs(
            ma_id=inputs.ma_id, review_id=inputs.review_id,
            analysis_number=inputs.analysis_number, k=len(idx),
            data_type=inputs.data_type, continuous=sliced,
        )
    if inputs.giv is not None:
        g = inputs.giv
        sliced = GIVTrials(yi=g.yi[idx], se=g.se[idx])
        return MAInputs(
            ma_id=inputs.ma_id, review_id=inputs.review_id,
            analysis_number=inputs.analysis_number, k=len(idx),
            data_type=inputs.data_type, giv=sliced,
        )
    raise ValueError(f"MAInputs {inputs.ma_id} has no trial data attached")


def _yi_vi(inputs: MAInputs) -> tuple[np.ndarray, np.ndarray]:
    """Compute trial-level (yi, vi) at machine precision. Mirrors
    repro_floor_atlas/precision_floor.py:_yi_vi_truth."""
    if inputs.data_type == "binary":
        b = inputs.binary
        return compute_log_or(b.e_cases, b.e_n, b.c_cases, b.c_n)
    if inputs.data_type == "continuous":
        c = inputs.continuous
        return compute_md(c.e_mean, c.e_sd, c.e_n, c.c_mean, c.c_sd, c.c_n)
    if inputs.data_type == "giv":
        g = inputs.giv
        return g.yi.copy(), g.se.copy() ** 2
    raise ValueError(f"unknown data_type: {inputs.data_type}")


def _pool_fe(yi: np.ndarray, vi: np.ndarray) -> tuple[float, float]:
    """Inverse-variance fixed-effect pool. Returns (pooled_estimate, se).
    Bit-identical to repro_floor_atlas/precision_floor.py:_pool_fixed_effect."""
    vi_safe = np.where(vi > 0, vi, np.finfo(float).eps)
    w = 1.0 / vi_safe
    sum_w = float(np.sum(w))
    pooled = float(np.sum(w * yi) / sum_w)
    se = float(np.sqrt(1.0 / sum_w))
    return pooled, se


def repool_subset(record: MARecord, indices: tuple[int, ...]) -> PoolResult:
    """Re-pool the MA using only the trial-index subset supplied."""
    k_subset = len(indices)
    invisible = k_subset < INVISIBILITY_THRESHOLD_K

    if k_subset < 2:
        return PoolResult(
            ma_id=record.ma_id, k_subset=k_subset, invisible=invisible,
            pooled_estimate=None, se=None, ci_lower=None, ci_upper=None, tau2=None,
        )

    sliced = _slice_inputs(record.inputs, indices)
    yi, vi = _yi_vi(sliced)
    pooled, se = _pool_fe(yi, vi)
    return PoolResult(
        ma_id=record.ma_id,
        k_subset=k_subset,
        invisible=invisible,
        pooled_estimate=pooled,
        se=se,
        ci_lower=pooled - 1.96 * se,
        ci_upper=pooled + 1.96 * se,
        tau2=None,  # fixed-effect: tau^2 not estimated in Plan 1
    )
