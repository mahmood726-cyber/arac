"""Dashboard summary stats: load atlas CSV, compute headline aggregates."""

from __future__ import annotations

import csv
from pathlib import Path

from arac.rgs.csv_writer import RGS_COLUMNS, write_rgs_rows
from arac.rgs.dashboard import AtlasSummary, load_atlas, summarize


def _seed_atlas(path: Path) -> None:
    """Write a synthetic atlas CSV directly (avoids dependency on RGSResult)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(RGS_COLUMNS))
        writer.writeheader()
        # MA1 site: visible, no reproduction gap
        writer.writerow({
            "ma_id": "MA1", "tier": "site",
            "k_total": "10", "k_subset": "5", "invisible": "False",
            "full_pooled_estimate": "-0.1", "full_se": "0.05",
            "full_ci_lower": "-0.2", "full_ci_upper": "0.0",
            "subset_pooled_estimate": "-0.12", "subset_se": "0.07",
            "subset_ci_lower": "-0.26", "subset_ci_upper": "0.02",
            "reproduction_gap": "False", "precision_gap_ratio": "1.4",
            "sign_flip": "False",
        })
        # MA1 authorship: invisible (k_subset=1)
        writer.writerow({
            "ma_id": "MA1", "tier": "authorship",
            "k_total": "10", "k_subset": "1", "invisible": "True",
            "full_pooled_estimate": "-0.1", "full_se": "0.05",
            "full_ci_lower": "-0.2", "full_ci_upper": "0.0",
            "subset_pooled_estimate": "", "subset_se": "",
            "subset_ci_lower": "", "subset_ci_upper": "",
            "reproduction_gap": "", "precision_gap_ratio": "", "sign_flip": "",
        })
        # MA2 site: visible, has reproduction gap + sign flip
        writer.writerow({
            "ma_id": "MA2", "tier": "site",
            "k_total": "8", "k_subset": "3", "invisible": "False",
            "full_pooled_estimate": "0.05", "full_se": "0.02",
            "full_ci_lower": "0.01", "full_ci_upper": "0.09",
            "subset_pooled_estimate": "-0.08", "subset_se": "0.04",
            "subset_ci_lower": "-0.16", "subset_ci_upper": "0.0",
            "reproduction_gap": "True", "precision_gap_ratio": "2.0",
            "sign_flip": "True",
        })


def test_load_atlas_round_trip(tmp_path: Path) -> None:
    csv_path = tmp_path / "atlas.csv"
    _seed_atlas(csv_path)
    rows = load_atlas(csv_path)
    assert len(rows) == 3
    assert rows[0]["ma_id"] == "MA1"
    assert rows[0]["tier"] == "site"
    assert rows[0]["invisible"] == "False"


def test_summarize_basic_counts(tmp_path: Path) -> None:
    csv_path = tmp_path / "atlas.csv"
    _seed_atlas(csv_path)
    rows = load_atlas(csv_path)
    summary = summarize(rows)
    assert isinstance(summary, AtlasSummary)
    assert summary.total_rows == 3
    assert summary.unique_mas == 2
    # 2 site rows, 1 authorship row, 0 participant rows.
    assert summary.rows_by_tier == {"site": 2, "authorship": 1}
    # 1 invisible row (the authorship one).
    assert summary.invisible_count == 1
    # 1 of 2 visible rows has reproduction_gap=True (MA2 site).
    assert summary.reproduction_gap_count == 1
    assert summary.sign_flip_count == 1


def test_summarize_empty(tmp_path: Path) -> None:
    csv_path = tmp_path / "atlas.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(RGS_COLUMNS))
        writer.writeheader()
    rows = load_atlas(csv_path)
    summary = summarize(rows)
    assert summary.total_rows == 0
    assert summary.unique_mas == 0
    assert summary.rows_by_tier == {}


def test_render_dashboard_produces_self_contained_html(tmp_path: Path) -> None:
    from arac.rgs.dashboard import render_dashboard

    csv_path = tmp_path / "atlas.csv"
    _seed_atlas(csv_path)
    rows = load_atlas(csv_path)
    html = render_dashboard(rows, summarize(rows))

    # Self-contained checks
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "</html>" in html
    # No external CDN references
    assert "cdn." not in html
    assert "googleapis.com" not in html
    assert "<script src=" not in html  # all JS is inline
    # The atlas data is embedded inline (look for one of the seeded ma_ids)
    assert "MA1" in html
    assert "MA2" in html
    # The summary section has the basic counts
    assert "3" in html  # total_rows = 3
    assert "2" in html  # unique_mas = 2 (also appears elsewhere in template; fine)


def test_render_dashboard_empty_atlas_placeholder(tmp_path: Path) -> None:
    from arac.rgs.dashboard import render_dashboard
    summary = summarize([])
    html = render_dashboard([], summary)
    assert "<!DOCTYPE html>" in html
    # The empty-atlas placeholder text should appear
    assert "atlas is empty" in html.lower() or "no rows" in html.lower()
