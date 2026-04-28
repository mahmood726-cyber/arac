"""Regression: HYVET 2008 (a UK-led trial) is NOT classified african_led.

Plan 2C's smoke run misclassified HYVET because alias 'car' (Central African
Republic abbreviation) substring-matched inside 'Cardiovascular' in HYVET's
first-author affiliation. Plan 2C.1's word-boundary fix should reject this.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.bridge import TrialRow
from arac.classify.tier_a import AuthorPosition, TierA, TierAClassifier
from arac.resolve.http_cache import HttpCache
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata


# A synthetic HYVET-shape affiliation. The exact NLM-recorded affiliation
# for HYVET first author varies by NLM revision, but it CONTAINS the word
# "Cardiovascular" (or similar -CAR-* word) that triggered the bug.
_HYVET_AFFILIATION = (
    "Cardiovascular Research Unit, Imperial College, London, United Kingdom"
)


def _seed_pubmed_with_hyvet(cache_dir: Path, pmid: str = "18378519") -> None:
    cache = HttpCache(root=cache_dir / "pubmed", ttl_seconds=3600)
    client = PubMedClient(cache_dir=cache_dir / "pubmed")
    xml = (
        f'<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        f'<PMID>{pmid}</PMID><Article><AuthorList>'
        f'<Author><LastName>Beckett</LastName>'
        f'<AffiliationInfo><Affiliation>{_HYVET_AFFILIATION}</Affiliation></AffiliationInfo></Author>'
        f'</AuthorList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(client._build_url(pmid), b"", xml.encode())


def test_hyvet_classified_not_african_led(tmp_path: Path) -> None:
    _seed_pubmed_with_hyvet(tmp_path)
    classifier = TierAClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed")
    )
    meta = ResolvedMetadata(
        trial_id="HYVET_TEST::t0",
        method=ResolutionMethod.ACRONYM,
        confidence=0.95,
        pmid="18378519",
        nct_id=None,
        title="HYVET",
        first_author=None,
        first_affiliation_raw=None,
        country_list=(),
    )
    result = classifier.classify(meta)

    # The whole point of Plan 2C.1: HYVET should NOT be african_led.
    # Pre-fix: was classified AFRICAN_LED with matched_country="Car"
    # Post-fix: should be NOT_AFRICAN_LED (UK-led trial)
    assert result.tier_a is TierA.NOT_AFRICAN_LED, (
        f"HYVET regression: expected NOT_AFRICAN_LED, got {result.tier_a.value} "
        f"(matched_country={result.matched_country!r}). Word-boundary fix "
        f"may not have eliminated the 'car' false-positive."
    )
    assert result.matched_country is None
