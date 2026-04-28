"""Resolve every trial in one Pairwise70 MA AND run Tier-P classification.

Usage:
    ARAC_ANTHROPIC_API_KEY=sk-ant-... python scripts/tier_p_smoke.py <ma_id>

Combines Plan 2A resolver + Plan 2A.1 PubMed enrichment + Plan 2D Tier-P.
LLM responses cached to outputs/cache/resolve/tier_p_llm/. First run on a
new MA will take longer (live API calls); re-runs are cache-served.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyreadr

from arac.bridge import load_all_mas
from arac.classify._anthropic_pre import resolve_anthropic_config
from arac.classify.tier_p import TierPClassifier
from arac.classify.tier_p_extractor import TierPExtractor
from arac.resolve.pubmed import PubMedClient
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
    ap = argparse.ArgumentParser(
        description="Run Tier-P (participant geography) classification over a Pairwise70 MA."
    )
    ap.add_argument("ma_id", help="e.g. CD000028_pub4_data__A1")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from inspect_rda import _data_dir  # type: ignore
    pairwise70_dir = _data_dir()
    sys.path.pop(0)

    try:
        config = resolve_anthropic_config()
    except RuntimeError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    cache_dir = Path("outputs/cache/resolve")
    cache_dir.mkdir(parents=True, exist_ok=True)

    mas = load_all_mas(pairwise70_dir, max_reviews=None)
    ma = next((m for m in mas if m.ma_id == args.ma_id), None)
    if ma is None:
        raise SystemExit(f"ma_id not found in Pairwise70: {args.ma_id}")

    study_strings = _load_study_strings_for_ma(args.ma_id, pairwise70_dir)
    resolver = StudyResolver(cache_dir=cache_dir)
    pubmed = PubMedClient(cache_dir=cache_dir / "pubmed")
    extractor = TierPExtractor(cache_dir=cache_dir, config=config)
    classifier = TierPClassifier(pubmed_client=pubmed, extractor=extractor)

    print(f"Tier-P for {len(ma.trials)} trials in {ma.ma_id} (model={config.model}):")
    for trial in ma.trials:
        s = study_strings.get(trial.trial_index, "<MISSING>")
        meta = resolver.resolve(trial, study_string=s)
        if meta.pmid is None:
            print(f"  [{trial.trial_index}] '{s}' -> resolve=FAILED -> tier_p=INSUFFICIENT")
            continue
        result = classifier.classify(meta)
        print(
            f"  [{trial.trial_index}] '{s}' -> "
            f"resolve={meta.method.value} (pmid={meta.pmid}) -> "
            f"tier_p={result.tier_p.value} (conf={result.confidence:.2f}, "
            f"african_pct={result.african_pct}, countries={list(result.countries_mentioned)[:3]})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
