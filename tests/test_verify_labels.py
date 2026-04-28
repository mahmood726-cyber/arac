"""Per-trial labels CSV: emit one row per (trial, tier) for verification UI."""

from __future__ import annotations

import csv
from pathlib import Path

from arac.verify.labels import (
    LABEL_COLUMNS,
    TrialLabel,
    write_trial_labels,
)


def test_label_columns_count() -> None:
    # 18 columns total (identifier + per-tier fields + source context)
    assert len(LABEL_COLUMNS) == 18
    assert LABEL_COLUMNS[0] == "trial_id"
    assert "tier_s_label" in LABEL_COLUMNS
    assert "tier_a_label" in LABEL_COLUMNS
    assert "tier_p_label" in LABEL_COLUMNS
    assert "abstract_excerpt" in LABEL_COLUMNS


def test_write_labels_round_trip(tmp_path: Path) -> None:
    rows = [
        TrialLabel(
            trial_id="MA1::t0", ma_id="MA1", trial_index=0,
            study_string="Smith 2010",
            pmid="12345", nct_id=None, title="Test Trial",
            tier_s_label="african_site", tier_s_source="aact",
            tier_s_confidence=0.97, tier_s_country="Uganda",
            tier_a_label="african_led", tier_a_position="first",
            tier_a_confidence=0.85, tier_a_country="Uganda",
            tier_p_label="african_majority", tier_p_confidence=0.95,
            tier_p_african_pct=80.0, tier_p_evidence="800 of 1000 in Uganda.",
            abstract_excerpt="Test abstract excerpt...",
            authors_list="Smith, Jones, Mukasa",
        ),
    ]
    out = tmp_path / "trial_labels.csv"
    n = write_trial_labels(rows, out)
    assert n == 1

    with out.open() as f:
        loaded = list(csv.DictReader(f))
    assert len(loaded) == 1
    assert loaded[0]["trial_id"] == "MA1::t0"
    assert loaded[0]["tier_s_label"] == "african_site"
    assert loaded[0]["tier_p_african_pct"] == "80.0"
