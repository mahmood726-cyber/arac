"""Headline regression — recompute the non-reproducibility rate that
repro-floor-atlas v0.1.0 published as 14.3% (binary 12.9 / continuous 25.0 /
giv 27.0). ARAC must land within ±0.5pp.

Approach: read repro-floor-atlas's published outputs/atlas.csv and recompute
the headline aggregation using the same logic as repro-floor-atlas's
report.py::_headline_stats — Scenario B (forest_plot_extraction) rows with
rounding_mode="adaptive", counting rows where exceeds_adaptive is True.

A future iteration of this module (Plan 3) will compute the headline from
ARAC's own re-built atlas, not from repro-floor-atlas's CSV. For Plan 1,
reading the published CSV is sufficient.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path


_CANDIDATE_ATLAS_PATHS = [
    "C:/Projects/repro-floor-atlas/outputs/atlas.csv",  # sentinel:skip-line P0-hardcoded-local-path
    "D:/Projects/repro-floor-atlas/outputs/atlas.csv",  # sentinel:skip-line P0-hardcoded-local-path
]


def _resolve_atlas_csv() -> Path | None:
    """Locate repro-floor-atlas's outputs/atlas.csv via env var or candidates.

    Returns None (instead of raising) so module-level code can set a default
    Path without blocking import on machines that don't have the atlas.
    Raises at call time if the caller actually needs the file.
    """
    env_override = os.environ.get("REPRO_FLOOR_ATLAS_OUTPUT")
    if env_override:
        p = Path(env_override)
        if not p.is_file():
            raise RuntimeError(
                f"REPRO_FLOOR_ATLAS_OUTPUT={env_override!r} is set but is not a file. "
                "Point it at outputs/atlas.csv, or unset to fall back to candidate discovery."
            )
        return p
    for candidate in _CANDIDATE_ATLAS_PATHS:
        p = Path(candidate)
        if p.is_file():
            return p
    return None


def _default_atlas_csv() -> Path:
    """Return resolved atlas path, or first candidate as a placeholder.

    Use this only where None would break type-checking (e.g. module-level
    constant). Callers that actually read the file must check .is_file().
    """
    resolved = _resolve_atlas_csv()
    if resolved is not None:
        return resolved
    # Return the first candidate as a sentinel Path (may not exist).
    return Path(_CANDIDATE_ATLAS_PATHS[0])  # sentinel:skip-line P0-hardcoded-local-path


REPRO_ATLAS_CSV: Path = _default_atlas_csv()

NONREPRO_THRESHOLD = 0.005  # |delta| > this → MA flagged non-reproducible (reference only)


def headline_rates(atlas_csv: Path | None = None) -> dict[str, float]:
    """Return overall + per-data-type non-reproducibility percentages.

    Replicates repro-floor-atlas report.py::_headline_stats logic:
    - Filter rows to scenario="forest_plot_extraction", rounding_mode="adaptive"
    - A row is non-reproducible if exceeds_adaptive == "True"
    - Percentages are computed at the *row* level (one row per MA per dp)
      which matches the published 14.3 / 12.9 / 25.0 / 27.0 figures.

    Returns a dict with keys: "overall", "binary", "continuous", "giv",
    "_n_rows" (float for API uniformity).
    """
    if atlas_csv is None:
        atlas_csv = _resolve_atlas_csv()
        if atlas_csv is None:
            raise RuntimeError(
                "repro-floor-atlas outputs/atlas.csv not found. "
                "Set REPRO_FLOOR_ATLAS_OUTPUT env var or place the file at one of: "
                f"{_CANDIDATE_ATLAS_PATHS}"
            )

    total_by_dt: dict[str, int] = defaultdict(int)
    fail_by_dt: dict[str, int] = defaultdict(int)

    with atlas_csv.open() as f:
        for row in csv.DictReader(f):
            if row["scenario"] != "forest_plot_extraction":
                continue
            if row["rounding_mode"] != "adaptive":
                continue
            dt = row["data_type"]
            total_by_dt[dt] += 1
            if row["exceeds_adaptive"].lower() == "true":
                fail_by_dt[dt] += 1

    rates: dict[str, float] = {}
    for dt in total_by_dt:
        rates[dt] = 100.0 * fail_by_dt[dt] / total_by_dt[dt]

    overall_total = sum(total_by_dt.values())
    overall_fail = sum(fail_by_dt.values())
    rates["overall"] = 100.0 * overall_fail / overall_total if overall_total else 0.0
    rates["_n_rows"] = float(overall_total)
    return rates
