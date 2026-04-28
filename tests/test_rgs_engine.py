"""RGS engine: per-(MA, Tier) computation."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.bridge import load_all_mas
from arac.rgs.engine import RGSEngine, RGSResult, RGSTier


def test_rgs_result_full_subset_zero_gaps(pairwise70_dir: Path) -> None:
    """When tier subset = full set, all gap metrics should be zero."""
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 3), None)
    assert ma is not None

    engine = RGSEngine()
    full_indices = tuple(range(ma.k))
    result = engine.compute(ma, RGSTier.SITE, full_indices)

    assert isinstance(result, RGSResult)
    assert result.ma_id == ma.ma_id
    assert result.tier is RGSTier.SITE
    assert result.invisible is False
    assert result.k_subset == ma.k
    # Full subset = full pool: zero gaps.
    assert result.reproduction_gap is False  # |delta| < 0.005
    assert abs(result.precision_gap_ratio - 1.0) < 1e-10
    assert result.sign_flip is False


def test_rgs_invisible_when_subset_too_small(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 3), None)
    assert ma is not None
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.AUTHORSHIP, indices=(0, 1))
    assert result.invisible is True
    assert result.k_subset == 2
    # Metric values should be None for invisible (insufficient data).
    assert result.reproduction_gap is None
    assert result.precision_gap_ratio is None
    assert result.sign_flip is None


def test_rgs_empty_subset_invisible(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = mas[0]
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.PARTICIPANT, indices=())
    assert result.invisible is True
    assert result.k_subset == 0
    assert result.reproduction_gap is None
