"""Unit tests for tier_p_audit_compare.py — comparator math.

Covers Wilson CI, confusion matrix, Cohen's κ, sensitivity/specificity,
and Insufficient exclusion logic. All inputs are synthetic in-memory dicts;
no real audit files are required.

Run:
    python -m pytest tests/test_audit_compare.py -v
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# Make the scripts/ directory importable so we can import tier_p_audit_compare
# directly. This avoids any dependency on the package install path.
_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import tier_p_audit_compare as comp  # noqa: E402  (import after sys.path patch)


# ---------------------------------------------------------------------------
# Helpers for building synthetic llm / auditor dicts
# ---------------------------------------------------------------------------

def _make_llm_data(results: list[dict], n_trials: int | None = None) -> dict:
    return {
        "spec_version": "v0.1.1",
        "spec_commit": "ebc8c13",
        "amendment": "test",
        "sample_list_sha256": "abc",
        "model": "claude-opus-4-7",
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T01:00:00+00:00",
        "n_trials": n_trials if n_trials is not None else len(results),
        "n_api_calls": len(results),
        "n_cache_hits": 0,
        "results": results,
    }


def _make_auditor_data(results: list[dict]) -> dict:
    return {
        "spec_version": "v0.1.1",
        "results": results,
    }


def _llm_trial(trial_id: str, pmid: str, stratum: str, tier_p: str) -> dict:
    return {
        "trial_id": trial_id,
        "pmid": pmid,
        "stratum": stratum,
        "tier_p": tier_p,
        "confidence": "high",
        "african_pct": 75.0 if tier_p == "african_majority" else 10.0,
        "countries_mentioned": [],
        "evidence_source": "test",
    }


def _aud_trial(trial_id: str, verdict: str) -> dict:
    return {
        "trial_id": trial_id,
        "auditor_verdict": verdict,
        "evidence_quote": "test",
        "confidence": "high",
    }


def _make_dataset(
    n_tp: int,
    n_fn: int,
    n_fp: int,
    n_tn: int,
    n_insuf_llm: int = 0,
    n_insuf_aud: int = 0,
    n_insuf_both: int = 0,
) -> tuple[dict, dict]:
    """Build a synthetic dataset with specified confusion matrix + Insufficient counts."""
    llm_results = []
    aud_results = []
    idx = 0

    def _add(llm_tier: str, aud_verdict: str) -> None:
        nonlocal idx
        tid = f"TRIAL_{idx:03d}"
        llm_results.append(_llm_trial(tid, str(1000 + idx), "enriched", llm_tier))
        aud_results.append(_aud_trial(tid, aud_verdict))
        idx += 1

    for _ in range(n_tp):
        _add("african_majority", "African_majority")
    for _ in range(n_fn):
        _add("not_african_majority", "African_majority")
    for _ in range(n_fp):
        _add("african_majority", "Not_African_majority")
    for _ in range(n_tn):
        _add("not_african_majority", "Not_African_majority")
    # Insufficient — LLM only
    for _ in range(n_insuf_llm):
        _add("insufficient_data", "Not_African_majority")
    # Insufficient — auditor only
    for _ in range(n_insuf_aud):
        _add("african_majority", "Insufficient")
    # Insufficient — both
    for _ in range(n_insuf_both):
        _add("insufficient_data", "Insufficient")

    return _make_llm_data(llm_results), _make_auditor_data(aud_results)


# ---------------------------------------------------------------------------
# Test 1: perfect agreement → sensitivity = 1.0
# ---------------------------------------------------------------------------

def test_perfect_agreement_sensitivity_100pct() -> None:
    """All African-majority trials agree: TP=12, FN=0 → sensitivity = 1.0."""
    llm_data, aud_data = _make_dataset(n_tp=12, n_fn=0, n_fp=0, n_tn=18)
    report = comp.compute_calibration(llm_data, aud_data)
    assert report["confusion_matrix"]["TP"] == 12
    assert report["confusion_matrix"]["FN"] == 0
    sens = report["sensitivity"]
    assert sens["point"] == pytest.approx(1.0, abs=1e-9)
    # Wilson CI lower bound at p=1.0 should be > 0
    assert sens["ci_lower"] is not None and sens["ci_lower"] > 0.5


# ---------------------------------------------------------------------------
# Test 2: complete disagreement → sensitivity = 0.0
# ---------------------------------------------------------------------------

def test_no_overlap_sensitivity_0pct() -> None:
    """LLM disagrees on every African-majority trial: TP=0, FN=12 → sensitivity = 0.0."""
    llm_data, aud_data = _make_dataset(n_tp=0, n_fn=12, n_fp=0, n_tn=18)
    report = comp.compute_calibration(llm_data, aud_data)
    assert report["confusion_matrix"]["TP"] == 0
    assert report["confusion_matrix"]["FN"] == 12
    sens = report["sensitivity"]
    assert sens["point"] == pytest.approx(0.0, abs=1e-9)
    # Wilson CI upper bound at p=0.0, n=12 should be a real number < 1
    assert sens["ci_upper"] is not None and 0.0 < sens["ci_upper"] < 0.5


# ---------------------------------------------------------------------------
# Test 3: Wilson CI at n=15, p=12/15=0.8 — check against scipy
# ---------------------------------------------------------------------------

def test_wilson_ci_at_n_15_p_0_8() -> None:
    """TP=12, FN=3 → sensitivity=0.8, Wilson CI roughly (0.52, 0.94).

    Cross-check with a direct computation using the same formula to confirm
    the implementation is self-consistent and matches known values.
    """
    llm_data, aud_data = _make_dataset(n_tp=12, n_fn=3, n_fp=0, n_tn=15)
    report = comp.compute_calibration(llm_data, aud_data)
    sens = report["sensitivity"]
    assert sens["point"] == pytest.approx(0.8, abs=1e-9)
    # Wilson 95% CI for 12/15: published tables give roughly [0.52, 0.94]
    assert sens["ci_lower"] is not None
    assert sens["ci_upper"] is not None
    assert 0.50 < sens["ci_lower"] < 0.65  # lower bound roughly 0.52–0.55
    assert 0.90 < sens["ci_upper"] <= 1.0   # upper bound roughly 0.93–0.95

    # Direct formula cross-check using the same spec §5 formula (ground truth)
    import math as _math
    z = 1.96
    n, k = 15, 12
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    spread = (z * _math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    expected_lo = max(0.0, centre - spread)
    expected_hi = min(1.0, centre + spread)
    assert sens["ci_lower"] == pytest.approx(expected_lo, abs=1e-9), (
        f"Lower CI mismatch: ours={sens['ci_lower']:.9f}, formula={expected_lo:.9f}"
    )
    assert sens["ci_upper"] == pytest.approx(expected_hi, abs=1e-9), (
        f"Upper CI mismatch: ours={sens['ci_upper']:.9f}, formula={expected_hi:.9f}"
    )


# ---------------------------------------------------------------------------
# Test 4: Insufficient excluded correctly
# ---------------------------------------------------------------------------

def test_insufficient_excluded_correctly() -> None:
    """5 LLM-Insufficient + 5 auditor-Insufficient + 10 both-Insufficient → 20 evaluable.

    Total dataset = 8+2+5+5+5+5+10 = 40 trials. Pass expected_n=40 so the
    validator accepts it (the 30-trial limit is a production gate, not a math rule).
    """
    # 20 evaluable = 8 TP + 2 FN + 5 FP + 5 TN
    llm_data, aud_data = _make_dataset(
        n_tp=8,
        n_fn=2,
        n_fp=5,
        n_tn=5,
        n_insuf_llm=5,   # LLM insufficient, auditor gives evaluable verdict → excluded
        n_insuf_aud=5,   # Auditor insufficient, LLM gives evaluable verdict → excluded
        n_insuf_both=10, # both insufficient → excluded
    )
    report = comp.compute_calibration(llm_data, aud_data, expected_n=40)
    cm = report["confusion_matrix"]
    assert cm["TP"] == 8
    assert cm["FN"] == 2
    assert cm["FP"] == 5
    assert cm["TN"] == 5

    # Total excluded = 5 (llm-only) + 5 (aud-only) + 10 (both) = 20
    assert report["n_insufficient_excluded"] == 20
    assert report["n_insufficient_both"] == 10
    assert report["n_insufficient_llm_only"] == 5
    assert report["n_insufficient_auditor_only"] == 5

    # Sensitivity uses n_sens = 8 + 2 = 10, not 30
    sens = report["sensitivity"]
    assert sens["point"] == pytest.approx(0.8, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 5: Zero denominator → sensitivity = NaN, no crash
# ---------------------------------------------------------------------------

def test_zero_denominator_returns_nan() -> None:
    """TP=0, FN=0 → sensitivity denominator=0 → NaN, no crash."""
    llm_data, aud_data = _make_dataset(n_tp=0, n_fn=0, n_fp=3, n_tn=27)
    report = comp.compute_calibration(llm_data, aud_data)
    assert report["confusion_matrix"]["TP"] == 0
    assert report["confusion_matrix"]["FN"] == 0
    sens = report["sensitivity"]
    # Both point and CIs should be None (serialised NaN → None in report)
    assert sens["point"] is None
    assert sens["ci_lower"] is None
    assert sens["ci_upper"] is None
    # Specificity should still compute fine: n_spec = 3 + 27 = 30
    spec = report["specificity"]
    assert spec["point"] == pytest.approx(27 / 30, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 6: Cohen's κ matches sklearn (or hand-verified formula)
# ---------------------------------------------------------------------------

def test_kappa_computation_matches_sklearn() -> None:
    """κ for TP=10, FN=2, FP=3, TN=15 (n=30) matches sklearn to 1e-6."""
    tp, fn, fp, tn = 10, 2, 3, 15
    llm_data, aud_data = _make_dataset(n_tp=tp, n_fn=fn, n_fp=fp, n_tn=tn)
    report = comp.compute_calibration(llm_data, aud_data)
    kappa_ours = report["kappa"]
    assert kappa_ours is not None

    # Hand-verified formula cross-check (always available, no extra dep)
    n = tp + fn + fp + tn  # 30
    p_obs = (tp + tn) / n  # 25/30
    row_pos = tp + fn  # 12
    row_neg = fp + tn  # 18
    col_pos = tp + fp  # 13
    col_neg = fn + tn  # 17
    p_chance = (row_pos * col_pos + row_neg * col_neg) / (n * n)
    kappa_hand = (p_obs - p_chance) / (1 - p_chance)
    assert kappa_ours == pytest.approx(kappa_hand, abs=1e-9)

    # If sklearn is available, also cross-check against it
    sklearn_metrics = pytest.importorskip(
        "sklearn.metrics", reason="sklearn not installed — skipping sklearn cross-check"
    )
    # Build label arrays from confusion matrix: row=auditor, col=LLM
    y_true = (["african_majority"] * tp + ["african_majority"] * fn +
               ["not_african_majority"] * fp + ["not_african_majority"] * tn)
    y_pred = (["african_majority"] * tp + ["not_african_majority"] * fn +
               ["african_majority"] * fp + ["not_african_majority"] * tn)
    kappa_sklearn = sklearn_metrics.cohen_kappa_score(y_true, y_pred)
    assert kappa_ours == pytest.approx(kappa_sklearn, abs=1e-6), (
        f"κ mismatch: ours={kappa_ours:.8f}, sklearn={kappa_sklearn:.8f}"
    )


# ---------------------------------------------------------------------------
# Bonus test 7: PPV = None when TP+FP = 0
# ---------------------------------------------------------------------------

def test_ppv_none_when_no_positives_predicted() -> None:
    """TP=0, FP=0 → PPV is None (not a crash)."""
    llm_data, aud_data = _make_dataset(n_tp=0, n_fn=10, n_fp=0, n_tn=20)
    report = comp.compute_calibration(llm_data, aud_data)
    assert report["ppv"] is None


# ---------------------------------------------------------------------------
# Bonus test 8: specificity at 100%
# ---------------------------------------------------------------------------

def test_perfect_specificity() -> None:
    """FP=0, TN=18 → specificity = 1.0."""
    llm_data, aud_data = _make_dataset(n_tp=10, n_fn=2, n_fp=0, n_tn=18)
    report = comp.compute_calibration(llm_data, aud_data)
    spec = report["specificity"]
    assert spec["point"] == pytest.approx(1.0, abs=1e-9)
