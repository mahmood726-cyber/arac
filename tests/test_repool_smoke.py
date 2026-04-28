"""Repool engine smoke: importable + can compute a pool from a single MA."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from arac.bridge import load_all_mas
from arac.repool import PoolResult, repool_subset


def test_repool_subset_returns_result(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    # Find the first MA with k>=3 (single-study k=1 cases would return invisible)
    ma = next((m for m in mas if m.k >= 3), None)
    assert ma is not None, "smoke fixture needs at least one MA with k>=3"
    indices = tuple(range(ma.k))  # full subset = original pool

    result = repool_subset(ma, indices)
    assert isinstance(result, PoolResult)
    assert result.k_subset == ma.k
    assert result.invisible is False


def test_repool_invisibility_flag(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=5)
    # Find an MA with k>=3 to exercise all four boundaries.
    ma = next((m for m in mas if m.k >= 3), None)
    assert ma is not None, "test fixture needs at least one MA with k>=3"

    # k_subset = 0 → invisible, pooled_estimate is None
    r0 = repool_subset(ma, indices=())
    assert r0.invisible is True
    assert r0.pooled_estimate is None
    assert r0.k_subset == 0

    # k_subset = 1 → invisible, pooled_estimate is None
    r1 = repool_subset(ma, indices=(0,))
    assert r1.invisible is True
    assert r1.pooled_estimate is None
    assert r1.k_subset == 1

    # k_subset = 2 → invisible (under threshold), but pool may still compute
    r2 = repool_subset(ma, indices=(0, 1))
    assert r2.invisible is True
    assert r2.k_subset == 2

    # k_subset >= 3 → not invisible, math runs
    r3 = repool_subset(ma, indices=(0, 1, 2))
    assert r3.invisible is False
    assert r3.k_subset == 3
    assert r3.pooled_estimate is not None


def test_reml_tau2_zero_when_no_heterogeneity(pairwise70_dir: Path) -> None:
    """When all trials report the same effect with the same variance, τ² should be 0."""
    from arac.repool import _reml_tau2
    yi = np.array([0.5, 0.5, 0.5, 0.5, 0.5])
    vi = np.array([0.04, 0.04, 0.04, 0.04, 0.04])
    tau2 = _reml_tau2(yi, vi)
    assert tau2 < 1e-6  # essentially zero


def test_reml_tau2_positive_with_heterogeneity() -> None:
    """When effects vary substantially given their reported precision, τ² > 0."""
    from arac.repool import _reml_tau2
    # Wildly different effects with low reported variance → high τ²
    yi = np.array([-0.5, 0.0, 0.5, 1.0, -1.0])
    vi = np.array([0.01, 0.01, 0.01, 0.01, 0.01])
    tau2 = _reml_tau2(yi, vi)
    assert tau2 > 0.1  # substantial heterogeneity


def test_compute_i2_zero_when_tau2_zero() -> None:
    from arac.repool import _compute_i2
    yi = np.array([0.5, 0.5, 0.5])
    vi = np.array([0.04, 0.04, 0.04])
    i2 = _compute_i2(yi, vi, tau2=0.0)
    assert 0.0 <= i2 <= 0.05  # I² is essentially zero


def test_compute_i2_high_when_tau2_dominates() -> None:
    from arac.repool import _compute_i2
    yi = [-0.5, 0.0, 0.5]
    vi = [0.01, 0.01, 0.01]
    i2 = _compute_i2(yi, vi, tau2=1.0)
    assert i2 > 0.9  # almost all variation is between-study


def test_repool_subset_populates_tau2_and_i2(pairwise70_dir: Path) -> None:
    """After Plan 3A.1, repool_subset returns PoolResult with tau2 and i2 populated
    (no longer None for k>=3 visible subsets)."""
    from arac.bridge import load_all_mas
    from arac.repool import repool_subset
    mas = load_all_mas(pairwise70_dir, max_reviews=5)
    ma = next((m for m in mas if m.k >= 5), None)
    assert ma is not None
    result = repool_subset(ma, indices=tuple(range(ma.k)))
    assert result.invisible is False
    # Both fields populated for visible subsets
    assert result.tau2 is not None
    assert result.tau2 >= 0
    assert result.i2 is not None
    assert 0.0 <= result.i2 <= 1.0
