"""Tier-A classifier: ResolvedMetadata → TierAResult."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.classify.tier_a import (
    TierA,
    TierAResult,
    TierAClassifier,
    AuthorPosition,
)
from arac.resolve.http_cache import HttpCache
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata


def _meta_with_pmid(pmid: str) -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id=f"TEST::t0::pmid={pmid}",
        method=ResolutionMethod.AUTHOR_YEAR,
        confidence=0.8,
        pmid=pmid,
        nct_id=None,
        title="test",
        first_author=None,
        first_affiliation_raw=None,
        country_list=(),
    )


def _meta_no_pmid() -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id="TEST::t0::no_pmid",
        method=ResolutionMethod.FAILED,
        confidence=0.0,
        pmid=None, nct_id=None, title=None,
        first_author=None, first_affiliation_raw=None,
        country_list=(),
    )


def _seed_pubmed(cache_dir: Path, pmid: str, xml: str) -> None:
    cache = HttpCache(root=cache_dir / "pubmed", ttl_seconds=3600)
    client = PubMedClient(cache_dir=cache_dir / "pubmed")
    cache.set(client._build_url(pmid), b"", xml.encode())


def _xml_with_authors(pmid: str, authors: list[tuple[str, str | None]]) -> str:
    """Build minimal PubmedArticleSet XML with given (lastname, affiliation) tuples."""
    author_blocks = []
    for lastname, aff in authors:
        aff_block = (
            f"<AffiliationInfo><Affiliation>{aff}</Affiliation></AffiliationInfo>"
            if aff else ""
        )
        author_blocks.append(
            f"<Author><LastName>{lastname}</LastName>{aff_block}</Author>"
        )
    return (
        f'<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        f'<PMID>{pmid}</PMID><Article><AuthorList>'
        f'{"".join(author_blocks)}'
        f'</AuthorList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )


def test_first_author_african(tmp_path: Path) -> None:
    pmid = "10001"
    xml = _xml_with_authors(pmid, [
        ("Mukasa", "Makerere University, Kampala, Uganda."),
        ("Smith", "Stanford University, USA."),
    ])
    _seed_pubmed(tmp_path, pmid, xml)
    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))
    result = classifier.classify(_meta_with_pmid(pmid))
    assert result.tier_a is TierA.AFRICAN_LED
    assert result.matched_position is AuthorPosition.FIRST
    assert result.confidence >= 0.8


def test_senior_author_african(tmp_path: Path) -> None:
    pmid = "10002"
    xml = _xml_with_authors(pmid, [
        ("Smith", "Stanford University, USA."),
        ("Doe", "Yale University, USA."),
        ("Mukasa", "Makerere University, Kampala, Uganda."),
    ])
    _seed_pubmed(tmp_path, pmid, xml)
    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))
    result = classifier.classify(_meta_with_pmid(pmid))
    assert result.tier_a is TierA.AFRICAN_LED
    assert result.matched_position is AuthorPosition.SENIOR


def test_neither_african(tmp_path: Path) -> None:
    pmid = "10003"
    xml = _xml_with_authors(pmid, [
        ("Smith", "Stanford University, USA."),
        ("Doe", "Cambridge University, United Kingdom."),
    ])
    _seed_pubmed(tmp_path, pmid, xml)
    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))
    result = classifier.classify(_meta_with_pmid(pmid))
    assert result.tier_a is TierA.NOT_AFRICAN_LED
    assert result.matched_position is AuthorPosition.NONE


def test_no_pmid_insufficient(tmp_path: Path) -> None:
    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))
    result = classifier.classify(_meta_no_pmid())
    assert result.tier_a is TierA.INSUFFICIENT_DATA
    assert result.confidence == 0.0


def test_no_affiliation_data_insufficient(tmp_path: Path) -> None:
    """PMID present but PubMed has no affiliation data on either author."""
    pmid = "10004"
    xml = _xml_with_authors(pmid, [
        ("Smith", None),
        ("Doe", None),
    ])
    _seed_pubmed(tmp_path, pmid, xml)
    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))
    result = classifier.classify(_meta_with_pmid(pmid))
    assert result.tier_a is TierA.INSUFFICIENT_DATA
    assert result.matched_position is AuthorPosition.NONE
