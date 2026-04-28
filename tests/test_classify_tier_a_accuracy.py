"""Tier-A accuracy regression on a 5-trial smoke fixture."""

from __future__ import annotations

import json
from pathlib import Path

from arac.classify.tier_a import (
    AuthorPosition, TierA, TierAClassifier,
)
from arac.resolve.http_cache import HttpCache
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tier_a_smoke.json"


def _xml_for_trial(pmid: str, authors: list) -> str:
    blocks = []
    for entry in authors:
        lastname, aff = entry
        aff_block = (
            f"<AffiliationInfo><Affiliation>{aff}</Affiliation></AffiliationInfo>"
            if aff else ""
        )
        blocks.append(f"<Author><LastName>{lastname}</LastName>{aff_block}</Author>")
    return (
        f'<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        f'<PMID>{pmid}</PMID><Article><AuthorList>{"".join(blocks)}</AuthorList>'
        f'</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )


def _seed(cache_dir: Path, pmid: str, xml: str) -> None:
    cache = HttpCache(root=cache_dir / "pubmed", ttl_seconds=3600)
    client = PubMedClient(cache_dir=cache_dir / "pubmed")
    cache.set(client._build_url(pmid), b"", xml.encode())


def _meta(pmid: str | None, idx: int) -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id=f"SMOKE::t{idx}",
        method=ResolutionMethod.AUTHOR_YEAR if pmid else ResolutionMethod.FAILED,
        confidence=0.8 if pmid else 0.0,
        pmid=pmid, nct_id=None, title="test",
        first_author=None, first_affiliation_raw=None,
        country_list=(),
    )


def test_tier_a_smoke_accuracy(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    trials = fixture["trials"]

    # Pre-seed PubMed cache for every fixture trial.
    for t in trials:
        _seed(tmp_path, t["pmid"], _xml_for_trial(t["pmid"], t["authors"]))

    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))

    tier_lookup = {
        "african_led": TierA.AFRICAN_LED,
        "not_african_led": TierA.NOT_AFRICAN_LED,
        "insufficient_data": TierA.INSUFFICIENT_DATA,
    }
    pos_lookup = {
        "first": AuthorPosition.FIRST,
        "senior": AuthorPosition.SENIOR,
        "none": AuthorPosition.NONE,
    }

    correct = 0
    mismatches = []
    for i, t in enumerate(trials):
        result = classifier.classify(_meta(t["pmid"], i))
        if result.tier_a is not tier_lookup[t["expected_tier_a"]]:
            mismatches.append(
                f"  [{i}] {t['comment']}: expected {t['expected_tier_a']}, got {result.tier_a.value}"
            )
            continue
        if result.matched_position is not pos_lookup[t["expected_position"]]:
            mismatches.append(
                f"  [{i}] {t['comment']}: expected position {t['expected_position']}, got {result.matched_position.value}"
            )
            continue
        correct += 1

    accuracy = correct / len(trials)
    assert accuracy >= 0.8, (
        f"Tier-A smoke accuracy {accuracy:.0%} below 80% gate "
        f"({correct}/{len(trials)} correct)\n"
        + "\n".join(mismatches)
    )
