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
    tau2: Optional[float]             # REML τ²; populated for k>=2
    i2: Optional[float]               # Higgins & Thompson I²; populated for k>=2


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


def _reml_tau2(
    yi: np.ndarray,
    vi: np.ndarray,
    max_iter: int = 100,
    tol: float = 1e-8,
) -> float:
    """REML estimator for between-study variance τ². Iterative Paule-Mandel style.

    On each iteration:
      w_i  = 1 / (v_i + τ²)
      μ̂   = Σ w_i y_i / Σ w_i
      τ²_new = max(0, Σ w_i² ((y_i − μ̂)² − v_i) / Σ w_i²)

    Per advanced-stats.md: REML is preferred over DL for k<10. We iterate
    until convergence (|τ²_new - τ²| < tol).

    Returns: τ² (clamped to [0, +inf)).
    """
    yi = np.asarray(yi, dtype=float)
    vi = np.asarray(vi, dtype=float)
    if len(yi) < 2:
        return 0.0

    tau2 = 0.0
    for _ in range(max_iter):
        w = 1.0 / (vi + tau2)
        mu = float(np.sum(w * yi) / np.sum(w))
        residuals_sq = (yi - mu) ** 2
        # Paule-Mandel / REML iteration
        numerator = float(np.sum(w**2 * (residuals_sq - vi)))
        denominator = float(np.sum(w**2))
        if denominator == 0:
            break
        tau2_new = max(0.0, numerator / denominator)
        if abs(tau2_new - tau2) < tol:
            tau2 = tau2_new
            break
        tau2 = tau2_new
    return tau2


def _compute_i2(yi: np.ndarray, vi: np.ndarray, tau2: float) -> float:
    """Higgins & Thompson I² statistic (2002, eq. 9 typical within-study variance).

    I² = τ² / (τ² + s²)
    where s² = (k-1) Σ w_i / [(Σ w_i)² − Σ w_i²], w_i = 1/v_i.

    Returns a value in [0.0, 1.0].
    """
    yi = np.asarray(yi, dtype=float)
    vi = np.asarray(vi, dtype=float)
    if len(yi) < 2:
        return 0.0
    vi_safe = np.where(vi > 0, vi, np.finfo(float).eps)
    w = 1.0 / vi_safe
    sum_w = float(np.sum(w))
    sum_w_sq = float(np.sum(w**2))
    denom = sum_w**2 - sum_w_sq
    if denom <= 0:
        return 0.0
    s_sq = (len(yi) - 1) * sum_w / denom
    if (tau2 + s_sq) <= 0:
        return 0.0
    return float(tau2 / (tau2 + s_sq))


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
            pooled_estimate=None, se=None, ci_lower=None, ci_upper=None,
            tau2=None, i2=None,
        )

    sliced = _slice_inputs(record.inputs, indices)
    yi, vi = _yi_vi(sliced)
    pooled, se = _pool_fe(yi, vi)
    tau2 = _reml_tau2(yi, vi)
    i2 = _compute_i2(yi, vi, tau2)
    return PoolResult(
        ma_id=record.ma_id,
        k_subset=k_subset,
        invisible=invisible,
        pooled_estimate=pooled,
        se=se,
        ci_lower=pooled - 1.96 * se,
        ci_upper=pooled + 1.96 * se,
        tau2=tau2,
        i2=i2,
    )
