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
