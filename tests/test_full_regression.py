"""Gating regression: ARAC's headline reproduces repro-floor-atlas v0.1.0
within ±0.5 percentage points.

Per ARAC spec §6 stopping rule, failure of this test halts the entire project
before any classifier work begins.

Step 3 investigation result (run_full_regression.py output):
  dp is not a relevant parameter for this aggregation — the published headline
  uses scenario="forest_plot_extraction" + rounding_mode="adaptive" rows,
  counting exceeds_adaptive==True, with no filter on declared_dp.
  All four rates reproduced exactly (deltas within ±0.05pp):
    overall    : 14.30%  (d=+0.00pp)
    binary     : 12.89%  (d=-0.01pp)
    continuous : 25.03%  (d=+0.03pp)
    giv        : 26.96%  (d=-0.04pp)
"""

from __future__ import annotations

import pytest

from arac.regression import REPRO_ATLAS_CSV, headline_rates


@pytest.mark.skipif(
    not REPRO_ATLAS_CSV.is_file(),
    reason="repro-floor-atlas atlas.csv not present — set REPRO_FLOOR_ATLAS_OUTPUT",
)
def test_headline_within_tolerance(repro_floor_baseline: dict) -> None:
    """All four headline non-reproducibility rates must land within ±0.5pp of
    the repro-floor-atlas v0.1.0 published figures.

    This is the §6 stopping-rule gate: if any assertion fails, Plan 2
    classifier work must not begin until the discrepancy is resolved.
    """
    rates = headline_rates(REPRO_ATLAS_CSV)
    tol = repro_floor_baseline["tolerance_pp"]

    assert abs(rates["overall"] - repro_floor_baseline["pooled_estimate"]) <= tol, (
        f"overall headline drift: ARAC={rates['overall']:.2f}%, "
        f"published={repro_floor_baseline['pooled_estimate']}%, tol=+/-{tol}pp"
    )
    assert abs(rates.get("binary", 0.0) - repro_floor_baseline["binary"]) <= tol, (
        f"binary headline drift: ARAC={rates.get('binary', 0.0):.2f}%, "
        f"published={repro_floor_baseline['binary']}%"
    )
    assert abs(rates.get("continuous", 0.0) - repro_floor_baseline["continuous"]) <= tol, (
        f"continuous headline drift: ARAC={rates.get('continuous', 0.0):.2f}%, "
        f"published={repro_floor_baseline['continuous']}%"
    )
    assert abs(rates.get("giv", 0.0) - repro_floor_baseline["giv"]) <= tol, (
        f"giv headline drift: ARAC={rates.get('giv', 0.0):.2f}%, "
        f"published={repro_floor_baseline['giv']}%"
    )
