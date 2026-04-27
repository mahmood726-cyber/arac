"""Tier-S accuracy regression on a 5-trial smoke fixture.

Gate: >=80% of fixture trials must classify correctly (both tier_s AND source).
Skips entirely if AACT is not configured (NCT-based trials cannot be resolved).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arac.classify._aact_path import resolve_aact_location
from arac.classify.aact import AACTClient
from arac.classify.tier_s import TierS, TierSClassifier, TierSSource
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tier_s_smoke.json"


def _meta(idx: int, nct_id: str | None = None, aff: str | None = None) -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id=f"SMOKE::t{idx}",
        method=ResolutionMethod.NCT_DIRECT if nct_id else (
            ResolutionMethod.AUTHOR_YEAR if aff else ResolutionMethod.FAILED
        ),
        confidence=1.0 if nct_id else (0.8 if aff else 0.0),
        pmid=None,
        nct_id=nct_id,
        title="test",
        first_author=None,
        first_affiliation_raw=aff,
        country_list=(),
    )


def test_tier_s_smoke_accuracy() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    trials = fixture["trials"]

    try:
        loc = resolve_aact_location()
        classifier = TierSClassifier(aact_client=AACTClient(loc))
    except RuntimeError:
        pytest.skip("AACT not configured; Tier-S accuracy gate cannot run")

    method_lookup = {
        "african_site": TierS.AFRICAN_SITE,
        "no_african_site": TierS.NO_AFRICAN_SITE,
        "insufficient_data": TierS.INSUFFICIENT_DATA,
    }
    source_lookup = {
        "aact": TierSSource.AACT,
        "affiliation": TierSSource.AFFILIATION,
        "none": TierSSource.NONE,
    }

    correct = 0
    mismatches = []
    for i, t in enumerate(trials):
        meta = _meta(i, nct_id=t.get("nct_id"), aff=t.get("first_affiliation_raw"))
        result = classifier.classify(meta)

        # Tier-S match — supports both "expected_tier_s" and "expected_tier_s_any_of"
        expected_set: set[TierS] = set()
        if "expected_tier_s" in t:
            expected_set.add(method_lookup[t["expected_tier_s"]])
        if "expected_tier_s_any_of" in t:
            expected_set.update(method_lookup[v] for v in t["expected_tier_s_any_of"])

        if result.tier_s not in expected_set:
            mismatches.append(
                f"  [{i}] {t.get('comment')}: expected {expected_set}, got {result.tier_s}"
            )
            continue

        if result.source is not source_lookup[t["expected_source"]]:
            mismatches.append(
                f"  [{i}] {t.get('comment')}: expected source {t['expected_source']}, got {result.source.value}"
            )
            continue

        correct += 1

    accuracy = correct / len(trials)
    assert accuracy >= 0.8, (
        f"Tier-S smoke accuracy {accuracy:.0%} below 80% gate "
        f"({correct}/{len(trials)} correct)\n"
        + "\n".join(mismatches)
    )
