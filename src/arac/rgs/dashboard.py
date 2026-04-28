"""Dashboard helpers: load the atlas CSV + compute summary stats.

The HTML generator (scripts/build_dashboard.py) calls these functions to
produce the data shown in the dashboard's headline section.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AtlasSummary:
    total_rows: int
    unique_mas: int
    rows_by_tier: dict[str, int] = field(default_factory=dict)
    invisible_count: int = 0
    reproduction_gap_count: int = 0
    sign_flip_count: int = 0


def load_atlas(path: Path) -> list[dict[str, str]]:
    """Load the atlas CSV. Returns a list of dicts (one per row)."""
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def summarize(rows: list[dict[str, str]]) -> AtlasSummary:
    """Compute headline stats from atlas rows."""
    if not rows:
        return AtlasSummary(total_rows=0, unique_mas=0, rows_by_tier={})

    tier_counts = Counter(r["tier"] for r in rows)
    invisible = sum(1 for r in rows if r["invisible"] == "True")
    reproduction_gap = sum(1 for r in rows if r.get("reproduction_gap") == "True")
    sign_flip = sum(1 for r in rows if r.get("sign_flip") == "True")
    unique_mas = len({r["ma_id"] for r in rows})

    return AtlasSummary(
        total_rows=len(rows),
        unique_mas=unique_mas,
        rows_by_tier=dict(tier_counts),
        invisible_count=invisible,
        reproduction_gap_count=reproduction_gap,
        sign_flip_count=sign_flip,
    )
