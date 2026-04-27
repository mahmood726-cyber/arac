"""Resolve every trial in one Pairwise70 MA and pretty-print results.

Usage:
    python scripts/resolve_smoke.py <ma_id>

Example:
    python scripts/resolve_smoke.py CD000028_pub4_data__A1

The Study string for each trial is read from the underlying Pairwise70
dataframe (joined via review_id + analysis_number). Cache lives at
outputs/cache/resolve/ — re-runs are fast.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyreadr

from arac.bridge import load_all_mas
from arac.resolve.resolver import StudyResolver


def _load_study_strings_for_ma(ma_id: str, pairwise70_dir: Path) -> dict[int, str]:
    """Map trial_index → Study string for one MA, by re-reading its .rda file."""
    review_id = ma_id.split("__")[0]
    rda = pairwise70_dir / f"{review_id}.rda"
    if not rda.is_file():
        raise SystemExit(f"missing rda: {rda}")
    bundle = pyreadr.read_r(str(rda))
    df = next(iter(bundle.values()))
    # Filter to this MA's analysis number.
    analysis_n = int(ma_id.split("__A")[-1])
    sub = df[df["Analysis.number"] == analysis_n]
    return {i: str(sub.iloc[i]["Study"]) for i in range(len(sub))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ma_id", help="e.g. CD000028_pub4_data__A1")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from inspect_rda import _data_dir  # type: ignore
    pairwise70_dir = _data_dir()
    sys.path.pop(0)

    cache_dir = Path("outputs/cache/resolve")
    cache_dir.mkdir(parents=True, exist_ok=True)

    mas = load_all_mas(pairwise70_dir, max_reviews=None)
    ma = next((m for m in mas if m.ma_id == args.ma_id), None)
    if ma is None:
        raise SystemExit(f"ma_id not found in Pairwise70: {args.ma_id}")

    study_strings = _load_study_strings_for_ma(args.ma_id, pairwise70_dir)
    resolver = StudyResolver(cache_dir=cache_dir)

    print(f"Resolving {len(ma.trials)} trials in {ma.ma_id}:")
    for trial in ma.trials:
        s = study_strings.get(trial.trial_index, "<MISSING>")
        result = resolver.resolve(trial, study_string=s)
        print(
            f"  [{trial.trial_index}] '{s}' -> "
            f"{result.method.value} (conf={result.confidence:.2f}) "
            f"pmid={result.pmid} nct={result.nct_id} "
            f"countries={list(result.country_list)[:3]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
