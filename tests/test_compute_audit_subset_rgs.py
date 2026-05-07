"""Tests for compute_audit_subset_rgs.py — subset-RGS computation.

All tests use synthetic in-memory MA data; no real .rda files required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pytest

# Ensure src/ on path before importing arac.
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from arac.bridge import MARecord
from arac.repool import PoolResult, INVISIBILITY_THRESHOLD_K
from arac.rgs.engine import RGSEngine, RGSTier


# ---------------------------------------------------------------------------
# Synthetic MARecord builder — avoids any dependency on real .rda files.
# ---------------------------------------------------------------------------

def _make_giv_record(
    ma_id: str,
    yi: list[float],
    se: list[float],
) -> MARecord:
    """Build a synthetic MARecord using GIV (generic inverse-variance) data."""
    from repro_floor_atlas.loader import GIVTrials, MAInputs  # type: ignore

    k = len(yi)
    inputs = MAInputs(
        ma_id=ma_id,
        review_id=ma_id.split("__")[0],
        analysis_number=1,
        k=k,
        data_type="giv",
        binary=None,
        continuous=None,
        giv=GIVTrials(
            yi=np.array(yi, dtype=float),
            se=np.array(se, dtype=float),
        ),
    )

    from arac.bridge import TrialRow

    trials = tuple(
        TrialRow(
            ma_id=ma_id,
            trial_index=i,
            trial_id=f"{ma_id}::t{i}",
            data_type="giv",
            k_total=k,
        )
        for i in range(k)
    )
    return MARecord(
        ma_id=ma_id,
        review_id=inputs.review_id,
        analysis_number=inputs.analysis_number,
        k=k,
        data_type="giv",
        inputs=inputs,
        trials=trials,
    )


# ---------------------------------------------------------------------------
# Test 1 — invisible when no african_majority trials.
# ---------------------------------------------------------------------------

def test_invisible_when_no_african_trials():
    """An MA whose audited subset has ZERO african_majority trials → invisible=True,
    subset_* fields are None, full pooled estimate is still computed."""
    record = _make_giv_record(
        "CD000001_pub1_data__A1",
        yi=[0.1, 0.2, 0.3, 0.4],
        se=[0.05, 0.06, 0.07, 0.08],
    )
    engine = RGSEngine()
    # Empty subset (no african_majority trials).
    result = engine.compute(record, RGSTier.PARTICIPANT, indices=())

    assert result.invisible is True
    assert result.k_subset == 0
    assert result.k_total == 4

    # Full pool stats always computed.
    assert result.full_pooled_estimate is not None
    assert result.full_se is not None

    # Subset stats are None when invisible.
    assert result.subset_pooled_estimate is None
    assert result.subset_se is None
    assert result.subset_ci_lower is None
    assert result.subset_ci_upper is None

    # Gap metrics are None.
    assert result.reproduction_gap is None
    assert result.precision_gap_ratio is None
    assert result.sign_flip is None
    assert result.heterogeneity_gap is None
    assert result.recommendation_change is None


# ---------------------------------------------------------------------------
# Test 2 — subset pooled estimate matches pooling the african_majority subset.
# ---------------------------------------------------------------------------

def test_subset_estimate_matches_pooling_african_subset():
    """MA with 5 trials, 3 african_majority → subset_pooled_estimate should equal
    the inverse-variance pool of those 3 trials (k_subset=3, visible)."""
    # We need k_subset >= 3 for visibility.
    yi = [0.5, 0.6, 0.7, -0.1, -0.2]  # trials 0,1,2 are african_majority
    se = [0.1, 0.1, 0.1, 0.1, 0.1]
    record = _make_giv_record("CD000002_pub1_data__A1", yi=yi, se=se)
    engine = RGSEngine()
    african_indices = (0, 1, 2)

    result = engine.compute(record, RGSTier.PARTICIPANT, indices=african_indices)
    assert result.invisible is False
    assert result.k_subset == 3

    # Manually compute expected pooled estimate for trials 0,1,2.
    yi_sub = np.array([yi[i] for i in african_indices])
    vi_sub = np.array([se[i] ** 2 for i in african_indices])
    w = 1.0 / vi_sub
    expected_pooled = float(np.sum(w * yi_sub) / np.sum(w))

    assert result.subset_pooled_estimate is not None
    assert abs(result.subset_pooled_estimate - expected_pooled) < 1e-8


# ---------------------------------------------------------------------------
# Test 3 — reproduction gap signals when full and subset materially differ.
# ---------------------------------------------------------------------------

def test_reproduction_gap_signal():
    """When full and subset estimates differ by more than 0.005,
    reproduction_gap should be True."""
    # Full pool: trials 0-4 (5 trials), estimate near 0.0.
    # Subset (african_majority): trials 0,1,2 with large positive effect.
    yi = [1.5, 1.6, 1.4, 0.0, 0.0]   # full mean ~0.6; subset mean ~1.5
    se = [0.1, 0.1, 0.1, 0.01, 0.01]  # last two very precise near 0 → pull full down
    record = _make_giv_record("CD000003_pub1_data__A1", yi=yi, se=se)
    engine = RGSEngine()
    african_indices = (0, 1, 2)

    result = engine.compute(record, RGSTier.PARTICIPANT, indices=african_indices)

    assert result.invisible is False
    assert result.reproduction_gap is True

    # Confirm the gap is indeed large.
    gap = abs(result.subset_pooled_estimate - result.full_pooled_estimate)
    assert gap > 0.005, f"Expected gap > 0.005 but got {gap}"


# ---------------------------------------------------------------------------
# Test 4 — _parse_trial_id parsing is correct.
# ---------------------------------------------------------------------------

def test_parse_trial_id():
    """Verify trial_id parsing extracts ma_id and trial_index correctly."""
    # Import from the script; adjust sys.path.
    scripts_dir = Path(__file__).parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from compute_audit_subset_rgs import _parse_trial_id  # type: ignore

    ma_id, idx = _parse_trial_id("CD006404_pub5_data__A10::t120")
    assert ma_id == "CD006404_pub5_data__A10"
    assert idx == 120

    ma_id2, idx2 = _parse_trial_id("CD001059_pub6_data__A1::t2")
    assert ma_id2 == "CD001059_pub6_data__A1"
    assert idx2 == 2


# ---------------------------------------------------------------------------
# Test 5 — _group_by_ma groups correctly.
# ---------------------------------------------------------------------------

def test_group_by_ma_groups_correctly():
    """_group_by_ma should produce one entry per unique MA, with audited trial
    verdicts keyed by trial index."""
    scripts_dir = Path(__file__).parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from compute_audit_subset_rgs import _group_by_ma  # type: ignore

    results = [
        {"trial_id": "MA_A1::t0", "tier_p": "african_majority"},
        {"trial_id": "MA_A1::t5", "tier_p": "not_african_majority"},
        {"trial_id": "MA_A2::t3", "tier_p": "insufficient_data"},
    ]
    sample_trials = [
        {"trial_id": "MA_A1::t0", "rda_filename": "MA.rda"},
        {"trial_id": "MA_A1::t5", "rda_filename": "MA.rda"},
        {"trial_id": "MA_A2::t3", "rda_filename": "MA.rda"},
    ]

    ma_map = _group_by_ma(results, sample_trials)
    assert set(ma_map.keys()) == {"MA_A1", "MA_A2"}
    assert ma_map["MA_A1"]["audited_trials"][0] == "african_majority"
    assert ma_map["MA_A1"]["audited_trials"][5] == "not_african_majority"
    assert ma_map["MA_A2"]["audited_trials"][3] == "insufficient_data"


# ---------------------------------------------------------------------------
# Test 6 — single-trial african_majority → invisible (k_subset=1 < 3).
# ---------------------------------------------------------------------------

def test_single_african_trial_is_invisible():
    """k_subset=1 is below the INVISIBILITY_THRESHOLD_K=3 → invisible=True."""
    record = _make_giv_record(
        "CD000004_pub1_data__A1",
        yi=[0.5, 0.1, 0.2, 0.3],
        se=[0.1, 0.1, 0.1, 0.1],
    )
    engine = RGSEngine()
    result = engine.compute(record, RGSTier.PARTICIPANT, indices=(0,))

    assert result.invisible is True
    assert result.k_subset == 1
    # Full estimate still computed.
    assert result.full_pooled_estimate is not None
    # Subset stats None.
    assert result.subset_pooled_estimate is None
