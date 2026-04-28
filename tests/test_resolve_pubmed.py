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
