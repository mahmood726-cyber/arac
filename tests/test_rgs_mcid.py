"""MCID classifier: CI vs MCID equivalence zone → BENEFIT / UNCERTAIN / HARM."""

from __future__ import annotations

import math

import pytest

from arac.rgs.mcid import (
    DEFAULT_MCID_BY_DATA_TYPE,
    RecommendationState,
    classify_ci_vs_mcid,
    mcid_for_data_type,
)


def test_default_mcids_present() -> None:
    assert "binary" in DEFAULT_MCID_BY_DATA_TYPE
    assert "continuous" in DEFAULT_MCID_BY_DATA_TYPE
    assert "giv" in DEFAULT_MCID_BY_DATA_TYPE
    # Binary default ≈ ±log(0.80)
    assert abs(DEFAULT_MCID_BY_DATA_TYPE["binary"] - abs(math.log(0.80))) < 1e-6


def test_mcid_for_data_type() -> None:
    assert mcid_for_data_type("binary") > 0
    assert mcid_for_data_type("continuous") > 0
    assert mcid_for_data_type("giv") > 0
    with pytest.raises(KeyError):
        mcid_for_data_type("unknown_type")


def test_classify_benefit_ci_below_negative_mcid() -> None:
    """CI entirely below -MCID → important benefit."""
    state = classify_ci_vs_mcid(ci_lower=-0.5, ci_upper=-0.3, mcid=0.2)
    assert state is RecommendationState.BENEFIT


def test_classify_harm_ci_above_positive_mcid() -> None:
    state = classify_ci_vs_mcid(ci_lower=0.3, ci_upper=0.5, mcid=0.2)
    assert state is RecommendationState.HARM


def test_classify_uncertain_overlaps_equivalence() -> None:
    state = classify_ci_vs_mcid(ci_lower=-0.1, ci_upper=0.1, mcid=0.2)
    assert state is RecommendationState.UNCERTAIN
    state = classify_ci_vs_mcid(ci_lower=-0.3, ci_upper=0.05, mcid=0.2)
    assert state is RecommendationState.UNCERTAIN


def test_classify_handles_none() -> None:
    """None ci bounds → None recommendation state."""
    assert classify_ci_vs_mcid(None, -0.3, 0.2) is None
    assert classify_ci_vs_mcid(-0.5, None, 0.2) is None
