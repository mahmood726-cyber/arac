"""Tier-S classifier: ResolvedMetadata -> TierSResult.

Note: VICTORIA (NCT02861534) has all country rows marked removed='t' in the
2026-04-12 AACT snapshot. PARADIGM-HF (NCT01035255) is used instead — it has
47 active countries including South Africa. This mirrors the same fix applied
in Task 2 (test_classify_aact.py).
"""

from __future__ import annotations

import pytest

from arac.classify._aact_path import resolve_aact_location
from arac.classify.aact import AACTClient
from arac.classify.tier_s import (
    TierS,
    TierSResult,
    TierSSource,
    TierSClassifier,
)
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata


def _meta_with_nct(nct_id: str) -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id=f"TEST::t0::{nct_id}",
        method=ResolutionMethod.NCT_DIRECT,
        confidence=1.0,
        pmid=None,
        nct_id=nct_id,
        title="test",
        first_author=None,
        first_affiliation_raw=None,
        country_list=(),
    )


def _meta_with_affiliation(aff: str) -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id="TEST::t0::aff",
        method=ResolutionMethod.AUTHOR_YEAR,
        confidence=0.8,
        pmid="12345",
        nct_id=None,
        title="test",
        first_author="Smith J",
        first_affiliation_raw=aff,
        country_list=(),
    )


def _meta_failed() -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id="TEST::t0::failed",
        method=ResolutionMethod.FAILED,
        confidence=0.0,
        pmid=None,
        nct_id=None,
        title=None,
        first_author=None,
        first_affiliation_raw=None,
        country_list=(),
    )


@pytest.fixture
def classifier() -> TierSClassifier:
    try:
        loc = resolve_aact_location()
    except RuntimeError:
        # No AACT — tests that require it will skip via pytest.skip below.
        return TierSClassifier(aact_client=None)
    return TierSClassifier(aact_client=AACTClient(loc))


def test_nct_with_african_site(classifier: TierSClassifier) -> None:
    """PARADIGM-HF (NCT01035255) has South Africa among its 47 active sites.

    Note: VICTORIA (NCT02861534) was the original plan fixture but has all
    country rows marked removed='t' in the 2026-04-12 AACT snapshot, so
    PARADIGM-HF is used instead.
    """
    if classifier._aact is None:
        pytest.skip("AACT not configured")
    result = classifier.classify(_meta_with_nct("NCT01035255"))
    assert isinstance(result, TierSResult)
    assert result.tier_s is TierS.AFRICAN_SITE
    assert result.source is TierSSource.AACT
    assert result.confidence >= 0.95


def test_affiliation_uganda_african(classifier: TierSClassifier) -> None:
    aff = "Department of Medicine, Makerere University, Kampala, Uganda"
    result = classifier.classify(_meta_with_affiliation(aff))
    assert result.tier_s is TierS.AFRICAN_SITE
    assert result.source is TierSSource.AFFILIATION
    assert 0.4 <= result.confidence <= 0.7  # affiliation = lower confidence


def test_affiliation_us_not_african(classifier: TierSClassifier) -> None:
    aff = "Department of Medicine, Stanford University, Stanford, CA, USA"
    result = classifier.classify(_meta_with_affiliation(aff))
    assert result.tier_s is TierS.NO_AFRICAN_SITE
    assert result.source is TierSSource.AFFILIATION


def test_failed_metadata_insufficient(classifier: TierSClassifier) -> None:
    result = classifier.classify(_meta_failed())
    assert result.tier_s is TierS.INSUFFICIENT_DATA
    assert result.source is TierSSource.NONE
    assert result.confidence == 0.0
