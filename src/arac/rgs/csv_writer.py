"""CSV writer for RGSResult rows. Column order is stable (alphabetical-ish
within stat groups) so atlas consumers can rely on it."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Optional

from arac.rgs.engine import RGSResult


# Column order: identifiers → counts → invisibility → full pool → subset pool → metrics
RGS_COLUMNS = (
    "ma_id",
    "tier",
    "k_total",
    "k_subset",
    "invisible",
    "full_pooled_estimate",
    "full_se",
    "full_ci_lower",
    "full_ci_upper",
    "subset_pooled_estimate",
    "subset_se",
    "subset_ci_lower",
    "subset_ci_upper",
    "reproduction_gap",
    "precision_gap_ratio",
    "sign_flip",
)


def _cell(value: Optional[object]) -> str:
    """None → empty string; bool → 'True'/'False'; floats → repr (full precision)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)  # full precision for atlas consumers
    return str(value)


def _row_to_dict(r: RGSResult) -> dict[str, str]:
    return {
        "ma_id": r.ma_id,
        "tier": r.tier.value,
        "k_total": _cell(r.k_total),
        "k_subset": _cell(r.k_subset),
        "invisible": _cell(r.invisible),
        "full_pooled_estimate": _cell(r.full_pooled_estimate),
        "full_se": _cell(r.full_se),
        "full_ci_lower": _cell(r.full_ci_lower),
        "full_ci_upper": _cell(r.full_ci_upper),
        "subset_pooled_estimate": _cell(r.subset_pooled_estimate),
        "subset_se": _cell(r.subset_se),
        "subset_ci_lower": _cell(r.subset_ci_lower),
        "subset_ci_upper": _cell(r.subset_ci_upper),
        "reproduction_gap": _cell(r.reproduction_gap),
        "precision_gap_ratio": _cell(r.precision_gap_ratio),
        "sign_flip": _cell(r.sign_flip),
    }


def write_rgs_rows(rows: Iterable[RGSResult], out: Path) -> int:
    """Write rows to a CSV with stable column order. Returns number of rows."""
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(RGS_COLUMNS))
        writer.writeheader()
        for r in rows:
            writer.writerow(_row_to_dict(r))
            n += 1
    return n
