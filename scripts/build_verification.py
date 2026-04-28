"""Generate the ARAC verification UI HTML from a trial_labels CSV.

Usage:
    python scripts/build_verification.py [--in outputs/trial_labels.csv] [--out outputs/verification.html]
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from arac.verify.labels import render_verification_ui


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="csv_in", default="outputs/trial_labels.csv")
    ap.add_argument("--out", dest="html_out", default="outputs/verification.html")
    args = ap.parse_args()

    csv_path = Path(args.csv_in)
    out_path = Path(args.html_out)

    if not csv_path.is_file():
        print(f"NOTE: {csv_path} does not exist; rendering empty UI.")
        rows: list = []
    else:
        with csv_path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

    html = render_verification_ui(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {len(html):,} bytes to {out_path} ({len(rows)} trials)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
