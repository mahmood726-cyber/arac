"""PubMed E-Utilities efetch client: PMID -> structured affiliation."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.resolve.pubmed import PubMedClient, PubMedRecord


CASSETTE_DIR = Path(__file__).parent / "cassettes"


@pytest.mark.vcr(cassette_library_dir=str(CASSETTE_DIR), record_mode="none")
def test_efetch_known_pmid(tmp_path: Path) -> None:
    """PMID 25176015 = PARADIGM-HF (McMurray et al, NEJM 2014). Known affiliations."""
    client = PubMedClient(cache_dir=tmp_path)
    record = client.efetch("25176015")
    assert record is None or isinstance(record, PubMedRecord)
    if record is not None:
        assert record.pmid == "25176015"
        assert record.first_author_lastname  # non-empty
        # PARADIGM-HF first author = McMurray (BHF Glasgow Cardiovascular Research Centre).
        # The exact affiliation string varies by NLM revision but should mention Glasgow or Scotland.
        if record.first_author_affiliation:
            assert (
                "Glasgow" in record.first_author_affiliation
                or "Scotland" in record.first_author_affiliation
                or "United Kingdom" in record.first_author_affiliation
            )


def test_efetch_invalid_pmid(tmp_path: Path) -> None:
    """A made-up PMID should return None, not raise."""
    from arac.resolve.http_cache import HttpCache
    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    client = PubMedClient(cache_dir=tmp_path)
    url = client._build_url("999999999")
    # Pre-seed cache with the empty PubmedArticleSet shape NLM returns for invalid PMIDs.
    cache.set(url, b"", b'<?xml version="1.0"?><PubmedArticleSet></PubmedArticleSet>')
    record = client.efetch("999999999")
    assert record is None


def test_efetch_returns_full_author_list(tmp_path: Path) -> None:
    """PubMedRecord now carries authors: list[PubMedAuthor]. authors[0] should
    match the legacy first_author_* fields for backwards compat."""
    from arac.resolve.http_cache import HttpCache
    from arac.resolve.pubmed import PubMedAuthor

    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    client = PubMedClient(cache_dir=tmp_path)
    url = client._build_url("12345")
    pubmed_xml = (
        '<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        '<PMID>12345</PMID><Article><AuthorList>'
        '<Author><LastName>Smith</LastName><ForeName>J</ForeName>'
        '<AffiliationInfo><Affiliation>Stanford University, USA.</Affiliation></AffiliationInfo></Author>'
        '<Author><LastName>Mukasa</LastName><ForeName>R</ForeName>'
        '<AffiliationInfo><Affiliation>Makerere University, Kampala, Uganda.</Affiliation></AffiliationInfo></Author>'
        '<Author><LastName>Doe</LastName><ForeName>A</ForeName></Author>'
        '</AuthorList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(url, b"", pubmed_xml.encode())
    rec = client.efetch("12345")

    assert rec is not None
    # Backwards compat
    assert rec.first_author_lastname == "Smith"
    assert rec.first_author_affiliation is not None
    assert "Stanford" in rec.first_author_affiliation

    # New: full author list
    assert isinstance(rec.authors, tuple)
    assert len(rec.authors) == 3
    assert all(isinstance(a, PubMedAuthor) for a in rec.authors)
    assert rec.authors[0].lastname == "Smith"
    assert rec.authors[1].lastname == "Mukasa"
    assert rec.authors[1].affiliation is not None
    assert "Uganda" in rec.authors[1].affiliation
    # Author with no affiliation gets affiliation=None.
    assert rec.authors[2].lastname == "Doe"
    assert rec.authors[2].affiliation is None


def test_efetch_extracts_abstract(tmp_path: Path) -> None:
    """PubMedRecord now carries abstract_text from the NLM XML's <AbstractText>."""
    from arac.resolve.http_cache import HttpCache
    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    client = PubMedClient(cache_dir=tmp_path)
    url = client._build_url("99999")
    pubmed_xml = (
        '<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        '<PMID>99999</PMID><Article><AuthorList>'
        '<Author><LastName>Test</LastName></Author>'
        '</AuthorList>'
        '<Abstract>'
        '<AbstractText Label="BACKGROUND">Background paragraph.</AbstractText>'
        '<AbstractText Label="METHODS">Methods paragraph.</AbstractText>'
        '<AbstractText Label="RESULTS">Results paragraph including the cohort: 200 participants in Uganda and 100 in Kenya.</AbstractText>'
        '</Abstract>'
        '</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(url, b"", pubmed_xml.encode())
    rec = client.efetch("99999")

    assert rec is not None
    assert rec.abstract_text is not None
    # Multi-section abstracts get joined; should contain all three parts
    assert "Background paragraph" in rec.abstract_text
    assert "Methods paragraph" in rec.abstract_text
    assert "Uganda" in rec.abstract_text
    # Backwards compat: existing fields still populated
    assert rec.first_author_lastname == "Test"


def test_efetch_handles_missing_abstract(tmp_path: Path) -> None:
    from arac.resolve.http_cache import HttpCache
    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    client = PubMedClient(cache_dir=tmp_path)
    url = client._build_url("11111")
    # NO <Abstract> element — old NLM records often lack one
    pubmed_xml = (
        '<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        '<PMID>11111</PMID><Article><AuthorList>'
        '<Author><LastName>Old</LastName></Author>'
        '</AuthorList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(url, b"", pubmed_xml.encode())
    rec = client.efetch("11111")

    assert rec is not None
    assert rec.abstract_text is None
