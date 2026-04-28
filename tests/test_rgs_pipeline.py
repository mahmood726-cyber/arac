"""RGS pipeline: end-to-end MA → resolved trials → tier subsets → RGS rows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from arac.bridge import MARecord, TrialRow, load_all_mas
from arac.classify.tier_a import AuthorPosition, TierA, TierAResult
from arac.classify.tier_p import TierP, TierPResult
from arac.classify.tier_s import TierS, TierSResult, TierSSource
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata
from arac.rgs.engine import RGSTier
from arac.rgs.pipeline import RGSPipeline, TierMode


# Mock classifiers — return canned results per trial_id, so the pipeline test
# doesn't need real Pairwise70 metadata or LLM access.

@dataclass
class _MockResolver:
    def resolve(self, trial: TrialRow, study_string: str) -> ResolvedMetadata:
        return ResolvedMetadata(
            trial_id=trial.trial_id,
            method=ResolutionMethod.AUTHOR_YEAR,
            confidence=0.8,
            pmid="1", nct_id=None, title="t",
            first_author=None, first_affiliation_raw=None, country_list=(),
        )


@dataclass
class _MockTierS:
    african_indices: set[int]  # which trial_indices count as Tier-S African
    def classify(self, meta: ResolvedMetadata) -> TierSResult:
        idx = int(meta.trial_id.rsplit("::t", 1)[-1])
        if idx in self.african_indices:
            return TierSResult(meta.trial_id, TierS.AFRICAN_SITE, TierSSource.AACT, 0.97, "Uganda")
        return TierSResult(meta.trial_id, TierS.NO_AFRICAN_SITE, TierSSource.AACT, 0.97, None)


@dataclass
class _MockTierA:
    african_indices: set[int]
    def classify(self, meta: ResolvedMetadata) -> TierAResult:
        idx = int(meta.trial_id.rsplit("::t", 1)[-1])
        if idx in self.african_indices:
            return TierAResult(meta.trial_id, TierA.AFRICAN_LED, AuthorPosition.FIRST, 0.85, "Uganda")
        return TierAResult(meta.trial_id, TierA.NOT_AFRICAN_LED, AuthorPosition.NONE, 0.85, None)


@dataclass
class _MockTierP:
    african_indices: set[int]
    def classify(self, meta: ResolvedMetadata) -> TierPResult:
        idx = int(meta.trial_id.rsplit("::t", 1)[-1])
        if idx in self.african_indices:
            return TierPResult(meta.trial_id, TierP.AFRICAN_MAJORITY, 0.95, 100.0, ("Uganda",), "evidence")
        return TierPResult(meta.trial_id, TierP.NOT_AFRICAN_MAJORITY, 0.95, 10.0, ("USA",), "evidence")


def _study_string_for(trial: TrialRow) -> str:
    return f"author {1990 + trial.trial_index}"


def test_pipeline_emits_rows_per_tier(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 4), None)
    if ma is None:
        pytest.skip("need an MA with k>=4")

    # First 3 trials are "African" by all three tiers; rest are not.
    african = {0, 1, 2}
    pipeline = RGSPipeline(
        resolver=_MockResolver(),
        tier_s=_MockTierS(african),
        tier_a=_MockTierA(african),
        tier_p=_MockTierP(african),
        study_string_lookup=_study_string_for,
    )

    rows = list(pipeline.run([ma], tier_mode=TierMode.SAP))
    # 3 rows per MA (one per tier).
    assert len(rows) == 3
    tiers_emitted = {r.tier for r in rows}
    assert tiers_emitted == {RGSTier.SITE, RGSTier.AUTHORSHIP, RGSTier.PARTICIPANT}

    # All 3 should have k_subset = 3 (the 3 African trials).
    for r in rows:
        assert r.k_subset == 3
        assert r.invisible is False  # k=3 is the threshold


def test_pipeline_sa_only_skips_tier_p(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 4), None)
    if ma is None:
        pytest.skip()

    pipeline = RGSPipeline(
        resolver=_MockResolver(),
        tier_s=_MockTierS({0, 1, 2}),
        tier_a=_MockTierA({0, 1, 2}),
        tier_p=None,  # MUST be None when SA_ONLY
        study_string_lookup=_study_string_for,
    )
    rows = list(pipeline.run([ma], tier_mode=TierMode.SA_ONLY))
    # 2 rows per MA (S and A, no P).
    assert len(rows) == 2
    tiers = {r.tier for r in rows}
    assert tiers == {RGSTier.SITE, RGSTier.AUTHORSHIP}


def test_pipeline_s_only(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 4), None)
    if ma is None:
        pytest.skip()

    pipeline = RGSPipeline(
        resolver=_MockResolver(),
        tier_s=_MockTierS({0, 1, 2}),
        tier_a=None,
        tier_p=None,
        study_string_lookup=_study_string_for,
    )
    rows = list(pipeline.run([ma], tier_mode=TierMode.S_ONLY))
    assert len(rows) == 1
    assert rows[0].tier is RGSTier.SITE
