"""Resolve every trial in one Pairwise70 MA AND run Tier-S classification.

Usage:
    python scripts/tier_s_smoke.py <ma_id>

Combines Plan 2A (resolve_smoke.py) with Plan 2B's Tier-S classifier in one
end-to-end pass. Per-trial output: study_string -> resolution -> tier_s.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyreadr

from arac.bridge import load_all_mas
from arac.classify._aact_path import resolve_aact_location
from arac.classify.aact import AACTClient
from arac.classify.tier_s import TierSClassifier
from arac.resolve.resolver import StudyResolver


def _load_study_strings_for_ma(ma_id: str, pairwise70_dir: Path) -> dict[int, str]:
    review_id = ma_id.split("__")[0]
    rda = pairwise70_dir / f"{review_id}.rda"
    if not rda.is_file():
        raise SystemExit(f"missing rda: {rda}")
    bundle = pyreadr.read_r(str(rda))
    df = next(iter(bundle.values()))
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

    try:
        aact_client = AACTClient(resolve_aact_location())
    except RuntimeError as e:
        print(f"NOTE: AACT not configured ({e}); Tier-S falls back to affiliation only", file=sys.stderr)
        aact_client = None

    mas = load_all_mas(pairwise70_dir, max_reviews=None)
    ma = next((m for m in mas if m.ma_id == args.ma_id), None)
    if ma is None:
        raise SystemExit(f"ma_id not found in Pairwise70: {args.ma_id}")

    study_strings = _load_study_strings_for_ma(args.ma_id, pairwise70_dir)
    resolver = StudyResolver(cache_dir=cache_dir)
    classifier = TierSClassifier(aact_client=aact_client)

    print(f"Tier-S for {len(ma.trials)} trials in {ma.ma_id}:")
    for trial in ma.trials:
        s = study_strings.get(trial.trial_index, "<MISSING>")
        meta = resolver.resolve(trial, study_string=s)
        ts = classifier.classify(meta)
        print(
            f"  [{trial.trial_index}] '{s}' -> "
            f"resolve={meta.method.value} (conf={meta.confidence:.2f}) -> "
            f"tier_s={ts.tier_s.value} (src={ts.source.value}, conf={ts.confidence:.2f}, country={ts.matched_country})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
