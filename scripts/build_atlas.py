"""Build the ARAC atlas: per-MA × per-Tier RGS rows over Pairwise70.

Usage:
    python scripts/build_atlas.py [--max-mas N] [--tier-mode s_only|sa_only|sap] [--out outputs/atlas.csv]

By default runs SA_ONLY tier mode (no LLM cost) on the first 5 MAs — safe to
re-run without API key, useful for validating the pipeline.

For full atlas (~6,386 MAs):
    --tier-mode sap requires ARAC_ANTHROPIC_API_KEY; cost ~$30 amortized
    --tier-mode sa_only is free (AACT + PubMed only)

Output: CSV at outputs/atlas.csv (one row per (MA, Tier)).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyreadr

from arac.bridge import TrialRow, load_all_mas
from arac.classify.aact import AACTClient
from arac.classify._aact_path import resolve_aact_location
from arac.classify.tier_a import TierAClassifier
from arac.classify.tier_p import TierPClassifier
from arac.classify.tier_p_extractor import TierPExtractor
from arac.classify.tier_s import TierSClassifier
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import StudyResolver
from arac.rgs.csv_writer import write_rgs_rows
from arac.rgs.pipeline import RGSPipeline, TierMode


def _study_string_lookup_for_dir(pairwise70_dir: Path):
    """Build a lookup function: TrialRow → Pairwise70 Study string."""
    cache: dict[str, dict[int, str]] = {}

    def lookup(trial: TrialRow) -> str:
        # Cache study-strings per ma_id so each rda is only read once.
        if trial.ma_id not in cache:
            review_id = trial.ma_id.split("__")[0]
            rda = pairwise70_dir / f"{review_id}.rda"
            if not rda.is_file():
                cache[trial.ma_id] = {}
                return f"<missing-rda:{review_id}>"
            bundle = pyreadr.read_r(str(rda))
            df = next(iter(bundle.values()))
            try:
                analysis_n = int(trial.ma_id.split("__A")[-1])
            except ValueError:
                cache[trial.ma_id] = {}
                return f"<bad-ma-id:{trial.ma_id}>"
            sub = df[df["Analysis.number"] == analysis_n]
            cache[trial.ma_id] = {
                i: str(sub.iloc[i]["Study"]) for i in range(len(sub))
            }
        return cache[trial.ma_id].get(trial.trial_index, "<missing>")

    return lookup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-mas", type=int, default=5)
    ap.add_argument(
        "--tier-mode",
        choices=["s_only", "sa_only", "sap"],
        default="sa_only",
    )
    ap.add_argument("--out", default="outputs/atlas.csv")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from inspect_rda import _data_dir  # type: ignore
    pairwise70_dir = _data_dir()
    sys.path.pop(0)

    cache_dir = Path("outputs/cache/atlas")
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Resolver — Plan 2A
    resolver = StudyResolver(cache_dir=cache_dir)

    # Tier-S — Plan 2B (AACT)
    try:
        aact_loc = resolve_aact_location()
        tier_s = TierSClassifier(aact_client=AACTClient(aact_loc))
    except RuntimeError as e:
        print(f"AACT not configured: {e}", file=sys.stderr)
        print("Tier-S will fall back to affiliation-only (no AACT).", file=sys.stderr)
        tier_s = TierSClassifier(aact_client=None)

    pubmed = PubMedClient(cache_dir=cache_dir / "pubmed")

    tier_mode = TierMode(args.tier_mode)

    tier_a = None
    tier_p = None
    if tier_mode in (TierMode.SA_ONLY, TierMode.SAP):
        tier_a = TierAClassifier(pubmed_client=pubmed)
    if tier_mode is TierMode.SAP:
        from arac.classify._anthropic_pre import resolve_anthropic_config
        try:
            ant_config = resolve_anthropic_config()
        except RuntimeError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1
        tier_p_extractor = TierPExtractor(cache_dir=cache_dir, config=ant_config)
        tier_p = TierPClassifier(pubmed_client=pubmed, extractor=tier_p_extractor)

    pipeline = RGSPipeline(
        resolver=resolver,
        tier_s=tier_s,
        tier_a=tier_a,
        tier_p=tier_p,
        study_string_lookup=_study_string_lookup_for_dir(pairwise70_dir),
    )

    mas = load_all_mas(pairwise70_dir, max_reviews=None)[: args.max_mas]
    print(f"Building atlas: {len(mas)} MAs, tier_mode={tier_mode.value}")

    out_path = Path(args.out)
    n = write_rgs_rows(pipeline.run(mas, tier_mode=tier_mode), out_path)
    print(f"Wrote {n} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
