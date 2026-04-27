"""Smoke regression: ARAC's full-subset repool matches repro-floor-atlas's
published atlas.csv truth_pooled column on a 10-MA sample, to 1e-10 tolerance.

Selection: first 10 MAs sorted by (review_id, analysis_number), then filtered
to k>=2 (k=1 MAs return pooled_estimate=None in ARAC — atlas.csv covers them
but ARAC's invisibility rule gates them; the smoke set excludes them for
apples-to-apples comparison).  Typically 9 of the 10 sorted MAs have k>=2.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest

from arac.bridge import load_all_mas
from arac.repool import repool_subset

# ---------------------------------------------------------------------------
# Resolve repro-floor-atlas outputs directory.
# Per lessons.md: "Do not hardcode one drive."
# ---------------------------------------------------------------------------
_CANDIDATE_ATLAS_OUTPUTS = [
    "C:/Projects/repro-floor-atlas/outputs",  # sentinel:skip-line P0-hardcoded-local-path
    "D:/Projects/repro-floor-atlas/outputs",  # sentinel:skip-line P0-hardcoded-local-path
]

_ENV_VAR = "REPRO_FLOOR_ATLAS_OUTPUT"


def _atlas_csv() -> Path | None:
    env_val = os.environ.get(_ENV_VAR)
    if env_val:
        p = Path(env_val)
        return p if p.is_file() else None
    for candidate in _CANDIDATE_ATLAS_OUTPUTS:
        p = Path(candidate) / "atlas.csv"
        if p.is_file():
            return p
    return None


_REPRO_ATLAS_CSV = _atlas_csv()


@pytest.mark.skipif(
    _REPRO_ATLAS_CSV is None,
    reason=(
        "repro-floor-atlas atlas.csv not present. "
        f"Set {_ENV_VAR}=/path/to/atlas.csv or place the project at "
        "C:/Projects/repro-floor-atlas."
    ),
)
def test_full_subset_matches_repro_floor_truth(pairwise70_dir: Path) -> None:
    """ARAC repool_subset must be bit-identical to repro-floor-atlas truth_pooled
    (1e-10 tolerance) on the canonical 10-MA smoke seed."""
    # Deterministic selection: sort by (review_id, analysis_number), take first
    # 10, then filter to k>=2 (ARAC returns None for k<2; atlas.csv covers k=1
    # separately but we compare poolable subsets only).
    mas = load_all_mas(pairwise70_dir, max_reviews=None)
    mas_sorted = sorted(mas, key=lambda m: (m.review_id, m.analysis_number))[:10]
    mas_poolable = [m for m in mas_sorted if m.k >= 2]
    target_ids = {m.ma_id for m in mas_poolable}

    assert len(mas_poolable) >= 1, "smoke set must contain at least one k>=2 MA"

    # Read repro-floor-atlas truth_pooled values for those ma_ids at the
    # raw_extraction / adaptive scenario (unmodified pool).
    expected: dict[str, float] = {}
    with _REPRO_ATLAS_CSV.open() as f:  # type: ignore[arg-type]
        for row in csv.DictReader(f):
            if (
                row["ma_id"] in target_ids
                and row["scenario"] == "raw_extraction"
                and row["rounding_mode"] == "adaptive"
            ):
                expected[row["ma_id"]] = float(row["truth_pooled"])

    missing = target_ids - set(expected)
    assert len(missing) == 0, (
        f"repro-floor-atlas atlas.csv missing truth_pooled rows for: {missing}"
    )

    # Compare ARAC's full-subset pool to atlas.csv truth_pooled at 1e-10.
    max_delta = 0.0
    for ma in mas_poolable:
        result = repool_subset(ma, indices=tuple(range(ma.k)))
        assert result.pooled_estimate is not None, (
            f"{ma.ma_id} k={ma.k}: expected a numeric pooled_estimate but got None"
        )
        exp = expected[ma.ma_id]
        delta = abs(result.pooled_estimate - exp)
        max_delta = max(max_delta, delta)
        assert delta < 1e-10, (
            f"drift on {ma.ma_id} (k={ma.k}): "
            f"ARAC={result.pooled_estimate!r}, "
            f"repro-floor-atlas={exp!r}, "
            f"delta={delta:.3e} (threshold=1e-10)"
        )

    # Sanity: confirm we actually checked the expected number of MAs.
    n_compared = len(mas_poolable)
    assert n_compared >= 1, "no MAs were compared — something went wrong in setup"
    # Log for diagnostics (visible in pytest -v / -s):
    print(
        f"\n[smoke-regression] compared {n_compared} MAs "
        f"(k>=2 from first-10 sorted); max delta={max_delta:.2e}"
    )
