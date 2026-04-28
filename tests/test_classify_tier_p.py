"""Tier-P classifier: ResolvedMetadata + PubMedRecord → TierPResult."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.classify._anthropic_pre import AnthropicConfig
from arac.classify.llm_cache import LLMCache
from arac.classify.tier_p import (
    TierP, TierPClassifier, TierPResult,
)
from arac.classify.tier_p_extractor import (
    ExtractionInput, ParticipantGeography, TierPExtractor, _SYSTEM_PROMPT,
)
from arac.resolve.pubmed import PubMedClient, PubMedRecord
from arac.resolve.http_cache import HttpCache
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata


def _meta_with_pmid(pmid: str) -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id=f"TEST::t0::pmid={pmid}",
        method=ResolutionMethod.AUTHOR_YEAR,
        confidence=0.8,
        pmid=pmid, nct_id=None, title="Test trial",
        first_author=None, first_affiliation_raw=None, country_list=(),
    )


def _seed_pubmed(cache_dir: Path, pmid: str, abstract: str) -> None:
    cache = HttpCache(root=cache_dir / "pubmed", ttl_seconds=3600)
    client = PubMedClient(cache_dir=cache_dir / "pubmed")
    xml = (
        f'<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        f'<PMID>{pmid}</PMID><Article><AuthorList>'
        f'<Author><LastName>X</LastName></Author></AuthorList>'
        f'<Abstract><AbstractText>{abstract}</AbstractText></Abstract>'
        f'</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(client._build_url(pmid), b"", xml.encode())


def _seed_llm(cache_dir: Path, pmid: str, title: str, abstract: str, geo: ParticipantGeography) -> None:
    cache = LLMCache(root=cache_dir / "tier_p_llm")
    user_text = f"PMID: {pmid}\n\nTitle: {title}\n\nAbstract:\n{abstract}"
    cache.set("claude-opus-4-7", _SYSTEM_PROMPT, user_text, geo.model_dump_json())


def _config() -> AnthropicConfig:
    return AnthropicConfig(api_key="sk-test-fake", model="claude-opus-4-7")


def test_african_majority(tmp_path: Path) -> None:
    abstract = "700 participants enrolled in Uganda and 300 in Kenya."
    _seed_pubmed(tmp_path, "100", abstract)
    _seed_llm(tmp_path, "100", "Test trial", abstract, ParticipantGeography(
        african_participant_pct=100.0, non_african_participant_pct=0.0,
        countries_mentioned=["Uganda", "Kenya"], evidence_source=abstract,
        confidence="high", reasoning="All 1000 in African countries.",
    ))
    classifier = TierPClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"),
        extractor=TierPExtractor(cache_dir=tmp_path, config=_config()),
    )
    result = classifier.classify(_meta_with_pmid("100"))
    assert result.tier_p is TierP.AFRICAN_MAJORITY
    assert result.african_pct == 100.0
    assert result.confidence >= 0.8


def test_not_african_majority(tmp_path: Path) -> None:
    abstract = "1000 participants from USA and Germany."
    _seed_pubmed(tmp_path, "200", abstract)
    _seed_llm(tmp_path, "200", "Test trial", abstract, ParticipantGeography(
        african_participant_pct=0.0, non_african_participant_pct=100.0,
        countries_mentioned=["USA", "Germany"], evidence_source=abstract,
        confidence="high", reasoning="No African participants.",
    ))
    classifier = TierPClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"),
        extractor=TierPExtractor(cache_dir=tmp_path, config=_config()),
    )
    result = classifier.classify(_meta_with_pmid("200"))
    assert result.tier_p is TierP.NOT_AFRICAN_MAJORITY


def test_insufficient_no_abstract(tmp_path: Path) -> None:
    """Trial has no abstract in PubMed → INSUFFICIENT."""
    cache = HttpCache(root=tmp_path / "pubmed", ttl_seconds=3600)
    client = PubMedClient(cache_dir=tmp_path / "pubmed")
    # PubMed XML with no <Abstract>
    xml = (
        '<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        '<PMID>300</PMID><Article><AuthorList>'
        '<Author><LastName>X</LastName></Author></AuthorList>'
        '</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(client._build_url("300"), b"", xml.encode())
    classifier = TierPClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"),
        extractor=TierPExtractor(cache_dir=tmp_path, config=_config()),
    )
    result = classifier.classify(_meta_with_pmid("300"))
    assert result.tier_p is TierP.INSUFFICIENT_DATA
    assert result.confidence == 0.0


def test_insufficient_llm_says_insufficient(tmp_path: Path) -> None:
    """Abstract present but LLM determines geography not extractable."""
    abstract = "500 participants in a double-blind RCT of drug X."
    _seed_pubmed(tmp_path, "400", abstract)
    _seed_llm(tmp_path, "400", "Test trial", abstract, ParticipantGeography(
        african_participant_pct=None, non_african_participant_pct=None,
        countries_mentioned=[], evidence_source=None,
        confidence="insufficient", reasoning="No geography mentioned.",
    ))
    classifier = TierPClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"),
        extractor=TierPExtractor(cache_dir=tmp_path, config=_config()),
    )
    result = classifier.classify(_meta_with_pmid("400"))
    assert result.tier_p is TierP.INSUFFICIENT_DATA


def test_no_pmid_insufficient(tmp_path: Path) -> None:
    classifier = TierPClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"),
        extractor=TierPExtractor(cache_dir=tmp_path, config=_config()),
    )
    meta = ResolvedMetadata(
        trial_id="x", method=ResolutionMethod.FAILED, confidence=0.0,
        pmid=None, nct_id=None, title=None, first_author=None,
        first_affiliation_raw=None, country_list=(),
    )
    result = classifier.classify(meta)
    assert result.tier_p is TierP.INSUFFICIENT_DATA
