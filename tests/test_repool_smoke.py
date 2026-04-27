"""Repool engine smoke: importable + can compute a pool from a single MA."""

from __future__ import annotations

from pathlib import Path

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
