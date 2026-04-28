"""Generate the ARAC atlas dashboard from outputs/atlas.csv.

Usage:
    python scripts/build_dashboard.py [--in outputs/atlas.csv] [--out outputs/dashboard.html]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from arac.rgs.dashboard import load_atlas, render_dashboard, summarize


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="csv_in", default="outputs/atlas.csv")
    ap.add_argument("--out", dest="html_out", default="outputs/dashboard.html")
    args = ap.parse_args()

    csv_path = Path(args.csv_in)
    out_path = Path(args.html_out)

    if not csv_path.is_file():
        print(f"NOTE: {csv_path} does not exist; rendering empty dashboard.")
        rows = []
    else:
        rows = load_atlas(csv_path)

    summary = summarize(rows)
    html = render_dashboard(rows, summary)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    print(f"Wrote {len(html):,} bytes to {out_path} ({summary.total_rows} rows, {summary.unique_mas} MAs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
