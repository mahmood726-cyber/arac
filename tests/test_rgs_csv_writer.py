"""CSV writer: serialize RGSResult rows to CSV with stable column order."""

from __future__ import annotations

import csv
from pathlib import Path

from arac.rgs.csv_writer import RGS_COLUMNS, write_rgs_rows
from arac.rgs.engine import RGSResult, RGSTier


def test_write_csv_round_trip(tmp_path: Path) -> None:
    rows = [
        RGSResult(
            ma_id="CD000028__A1", tier=RGSTier.SITE,
            k_total=10, k_subset=3, invisible=False,
            full_pooled_estimate=-0.12, full_se=0.05,
            full_ci_lower=-0.22, full_ci_upper=-0.02,
            subset_pooled_estimate=-0.15, subset_se=0.10,
            subset_ci_lower=-0.35, subset_ci_upper=0.05,
            reproduction_gap=True, precision_gap_ratio=2.0, sign_flip=False,
        ),
        RGSResult(
            ma_id="CD000028__A1", tier=RGSTier.AUTHORSHIP,
            k_total=10, k_subset=1, invisible=True,
            full_pooled_estimate=-0.12, full_se=0.05,
            full_ci_lower=-0.22, full_ci_upper=-0.02,
            subset_pooled_estimate=None, subset_se=None,
            subset_ci_lower=None, subset_ci_upper=None,
            reproduction_gap=None, precision_gap_ratio=None, sign_flip=None,
        ),
    ]
    out = tmp_path / "atlas.csv"
    write_rgs_rows(rows, out)

    with out.open() as f:
        reader = csv.DictReader(f)
        loaded = list(reader)

    assert len(loaded) == 2
    assert reader.fieldnames == list(RGS_COLUMNS)
    # First row
    assert loaded[0]["ma_id"] == "CD000028__A1"
    assert loaded[0]["tier"] == "site"
    assert loaded[0]["invisible"] == "False"
    assert loaded[0]["reproduction_gap"] == "True"
    # Second row (invisible) should have empty cells for None metric fields.
    assert loaded[1]["invisible"] == "True"
    assert loaded[1]["reproduction_gap"] == ""
    assert loaded[1]["subset_pooled_estimate"] == ""
