"""CLI driver for arac.regression.headline_rates.

Usage:
    python scripts/run_full_regression.py
    python scripts/run_full_regression.py --atlas /path/to/atlas.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Recompute repro-floor-atlas v0.1.0 headline non-reproducibility rates."
    )
    ap.add_argument(
        "--atlas",
        type=Path,
        default=None,
        help="Path to repro-floor-atlas outputs/atlas.csv "
             "(default: auto-discover via REPRO_FLOOR_ATLAS_OUTPUT or candidate paths)",
    )
    args = ap.parse_args()

    # Import here so the script can be run from the repo root without install
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from arac.regression import REPRO_ATLAS_CSV, headline_rates

    atlas_path: Path = args.atlas if args.atlas is not None else REPRO_ATLAS_CSV

    if not atlas_path.is_file():
        print(f"FAIL: atlas.csv not found at {atlas_path}", file=sys.stderr)
        print(
            "Set REPRO_FLOOR_ATLAS_OUTPUT env var or pass --atlas /path/to/atlas.csv",
            file=sys.stderr,
        )
        return 1

    rates = headline_rates(atlas_path)

    print("Headline non-reproducibility rates (repro-floor-atlas v0.1.0 recompute):")
    published = {"overall": 14.3, "binary": 12.9, "continuous": 25.0, "giv": 27.0}
    for key in ("overall", "binary", "continuous", "giv"):
        val = rates.get(key, float("nan"))
        ref = published.get(key, float("nan"))
        delta = val - ref
        flag = " PASS" if abs(delta) <= 0.5 else " FAIL (OUT OF TOLERANCE)"
        print(f"  {key:12s}: {val:.2f}%  (published {ref:.1f}%, d={delta:+.2f}pp){flag}")
    n = int(rates.get("_n_rows", 0))
    print(f"  {'_n_rows':12s}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
