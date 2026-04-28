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


def test_rgs_detects_gap_on_skewed_subset(pairwise70_dir: Path) -> None:
    """Pick an MA with k>=6, take only the first half as the 'tier subset'.
    The subset pool will likely differ from the full pool — verify metrics fire.
    """
    mas = load_all_mas(pairwise70_dir, max_reviews=10)
    ma = next((m for m in mas if m.k >= 6 and m.data_type == "binary"), None)
    if ma is None:
        pytest.skip("no binary MA with k>=6 found in first 10 reviews")

    engine = RGSEngine()
    half = ma.k // 2
    result = engine.compute(
        ma, RGSTier.SITE, indices=tuple(range(half)),
    )
    assert result.invisible is False
    assert result.k_subset == half

    # All metric fields populated (not None).
    assert result.reproduction_gap is not None
    assert result.precision_gap_ratio is not None
    assert result.sign_flip is not None

    # Precision gap should be > 1 (smaller subset → wider CI).
    assert result.precision_gap_ratio > 1.0


def test_rgs_includes_tau2_and_i2_when_visible(pairwise70_dir: Path) -> None:
    from arac.rgs.engine import RGSEngine, RGSTier
    from arac.bridge import load_all_mas
    mas = load_all_mas(pairwise70_dir, max_reviews=5)
    ma = next((m for m in mas if m.k >= 5), None)
    assert ma is not None
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.SITE, indices=tuple(range(ma.k)))

    assert result.invisible is False
    # Full pool stats populated
    assert result.full_tau2 is not None
    assert result.full_tau2 >= 0
    assert result.full_i2 is not None
    assert 0 <= result.full_i2 <= 1
    # Subset = full → subset stats also populated and equal
    assert result.subset_tau2 == result.full_tau2
    assert result.subset_i2 == result.full_i2
    # No heterogeneity gap when subset = full
    assert result.heterogeneity_gap is False


def test_rgs_heterogeneity_gap_detected_on_skewed_subset(pairwise70_dir: Path) -> None:
    """When subset half differs in heterogeneity from full, heterogeneity_gap fires."""
    from arac.rgs.engine import RGSEngine, RGSTier
    from arac.bridge import load_all_mas
    mas = load_all_mas(pairwise70_dir, max_reviews=20)
    ma = next((m for m in mas if m.k >= 8 and m.data_type == "binary"), None)
    if ma is None:
        pytest.skip("no binary MA with k>=8 in first 20 reviews")
    engine = RGSEngine()
    half = ma.k // 2
    result = engine.compute(ma, RGSTier.SITE, indices=tuple(range(half)))

    assert result.invisible is False
    assert result.full_i2 is not None
    assert result.subset_i2 is not None
    # heterogeneity_gap = |subset_i2 - full_i2| > 0.25
    expected = abs(result.subset_i2 - result.full_i2) > 0.25
    assert result.heterogeneity_gap is expected


def test_rgs_invisible_has_none_for_new_fields(pairwise70_dir: Path) -> None:
    from arac.rgs.engine import RGSEngine, RGSTier
    from arac.bridge import load_all_mas
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 3), None)
    assert ma is not None
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.PARTICIPANT, indices=())  # invisible

    assert result.invisible is True
    # Full pool stats still populated (we always compute the full pool)
    assert result.full_tau2 is not None
    assert result.full_i2 is not None
    # Subset stats and metrics are None
    assert result.subset_tau2 is None
    assert result.subset_i2 is None
    assert result.heterogeneity_gap is None


def test_rgs_recommendation_state_populated_when_visible(pairwise70_dir: Path) -> None:
    from arac.bridge import load_all_mas
    from arac.rgs.engine import RGSEngine, RGSTier
    from arac.rgs.mcid import RecommendationState
    mas = load_all_mas(pairwise70_dir, max_reviews=5)
    ma = next((m for m in mas if m.k >= 5), None)
    assert ma is not None
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.SITE, indices=tuple(range(ma.k)))

    assert result.invisible is False
    assert result.full_recommendation in (
        RecommendationState.BENEFIT, RecommendationState.UNCERTAIN, RecommendationState.HARM,
    )
    # Subset = full → recommendations match → no change
    assert result.full_recommendation == result.subset_recommendation
    assert result.recommendation_change is False


def test_rgs_recommendation_change_invisible(pairwise70_dir: Path) -> None:
    from arac.bridge import load_all_mas
    from arac.rgs.engine import RGSEngine, RGSTier
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 3), None)
    assert ma is not None
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.PARTICIPANT, indices=())  # invisible

    assert result.invisible is True
    # full_recommendation populated (we always compute full pool)
    assert result.full_recommendation is not None
    # subset and change are None
    assert result.subset_recommendation is None
    assert result.recommendation_change is None
