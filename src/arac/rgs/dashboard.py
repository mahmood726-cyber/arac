"""Dashboard helpers: load the atlas CSV + compute summary stats.

The HTML generator (scripts/build_dashboard.py) calls these functions to
produce the data shown in the dashboard's headline section.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from arac.rgs.html_template import TEMPLATE


@dataclass(frozen=True)
class AtlasSummary:
    total_rows: int
    unique_mas: int
    rows_by_tier: dict[str, int] = field(default_factory=dict)
    invisible_count: int = 0
    reproduction_gap_count: int = 0
    sign_flip_count: int = 0
    heterogeneity_gap_count: int = 0
    recommendation_change_count: int = 0


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
    heterogeneity_gap = sum(1 for r in rows if r.get("heterogeneity_gap") == "True")
    recommendation_change = sum(1 for r in rows if r.get("recommendation_change") == "True")
    unique_mas = len({r["ma_id"] for r in rows})

    return AtlasSummary(
        total_rows=len(rows),
        unique_mas=unique_mas,
        rows_by_tier=dict(tier_counts),
        invisible_count=invisible,
        reproduction_gap_count=reproduction_gap,
        sign_flip_count=sign_flip,
        heterogeneity_gap_count=heterogeneity_gap,
        recommendation_change_count=recommendation_change,
    )


def _summary_html(summary: AtlasSummary) -> str:
    """Render the summary section as an HTML fragment."""
    if summary.total_rows == 0:
        return (
            '<div class="summary"><h2>Summary</h2>'
            '<div class="placeholder">The atlas is empty. Run '
            '<code>python scripts/build_atlas.py</code> to populate it.</div>'
            '</div>'
        )
    metrics = [
        ("Total rows", summary.total_rows),
        ("Unique MAs", summary.unique_mas),
        ("Invisible (insufficient African data)", summary.invisible_count),
        ("Reproduction gap (|&Delta;|&gt;0.005)", summary.reproduction_gap_count),
        ("Sign flip", summary.sign_flip_count),
        ("Heterogeneity gap (|&Delta;I&sup2;|&gt;25pp)", summary.heterogeneity_gap_count),
        ("Rec change (CI crosses MCID zone)", summary.recommendation_change_count),
    ]
    cells = "".join(
        f'<div class="metric"><div class="metric-value">{v}</div>'
        f'<div class="metric-label">{label}</div></div>'
        for label, v in metrics
    )
    return f'<div class="summary"><h2>Summary</h2><div class="summary-row">{cells}</div></div>'


def render_dashboard(rows: list[dict[str, str]], summary: AtlasSummary) -> str:
    """Render the full dashboard HTML. Returns the file content as a string."""
    return Template(TEMPLATE).substitute(
        atlas_data_json=json.dumps(rows, ensure_ascii=False),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        row_count=len(rows),
        summary=_summary_html(summary),
    )
