"""Composite resolver: TrialRow -> ResolvedMetadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.bridge import TrialRow
from arac.resolve.resolver import (
    ResolvedMetadata,
    ResolutionMethod,
    StudyResolver,
)


@pytest.fixture
def resolver(tmp_path: Path) -> StudyResolver:
    return StudyResolver(cache_dir=tmp_path)


def _trial(study_string: str) -> TrialRow:
    return TrialRow(
        ma_id="TEST_MA",
        trial_index=0,
        trial_id=f"TEST_MA::t0::{study_string}",
        data_type="binary",
        k_total=1,
    )


def test_resolve_acronym_in_seed_table(resolver: StudyResolver) -> None:
    # HYVET is in the seed acronym table (Task 3).
    # The resolver substitutes the Study string (since TrialRow doesn't carry it).
    result = resolver.resolve(_trial("HYVET 2008"), study_string="HYVET 2008")
    assert isinstance(result, ResolvedMetadata)
    assert result.method is ResolutionMethod.ACRONYM
    assert result.pmid == "18378519"
    assert result.confidence >= 0.9


def test_resolve_unknown_string(resolver: StudyResolver) -> None:
    result = resolver.resolve(_trial("???"), study_string="???")
    assert result.method is ResolutionMethod.FAILED
    assert result.confidence == 0.0
    assert result.pmid is None
    assert result.nct_id is None


def test_resolver_enriches_affiliation_via_pubmed(tmp_path: Path) -> None:
    """Europe PMC hit with no affiliation is enriched from PubMed efetch."""
    import json

    from arac.resolve.http_cache import HttpCache
    from arac.resolve.europepmc import EuropePMCClient
    from arac.resolve.pubmed import PubMedClient

    # --- Pre-seed Europe PMC cache -----------------------------------------
    # Returns a hit for McMurray 2014 but with NO affiliation field.
    epmc_payload = json.dumps({
        "resultList": {
            "result": [
                {
                    "pmid": "25176015",
                    "title": "Angiotensin-neprilysin inhibition versus enalapril in heart failure.",
                    "journalTitle": "N Engl J Med",
                    "pubYear": "2014",
                    "authorString": "McMurray JJV, Packer M, Desai AS",
                    # intentionally omitted: "affiliation"
                }
            ]
        }
    }).encode()

    epmc_client = EuropePMCClient(cache_dir=tmp_path / "europepmc")
    epmc_url = epmc_client._build_url("McMurray", 2014)
    epmc_cache = HttpCache(root=tmp_path / "europepmc", ttl_seconds=3600)
    epmc_cache.set(epmc_url, b"", epmc_payload)

    # --- Pre-seed PubMed cache ---------------------------------------------
    pubmed_xml = (
        b'<?xml version="1.0"?>'
        b"<PubmedArticleSet>"
        b"<PubmedArticle>"
        b"<MedlineCitation>"
        b"<PMID>25176015</PMID>"
        b"<Article>"
        b"<AuthorList>"
        b"<Author>"
        b"<LastName>McMurray</LastName>"
        b"<AffiliationInfo>"
        b"<Affiliation>BHF Glasgow Cardiovascular Research Centre, Glasgow, Scotland.</Affiliation>"
        b"</AffiliationInfo>"
        b"</Author>"
        b"</AuthorList>"
        b"</Article>"
        b"</MedlineCitation>"
        b"</PubmedArticle>"
        b"</PubmedArticleSet>"
    )

    pubmed_client = PubMedClient(cache_dir=tmp_path / "pubmed")
    pubmed_url = pubmed_client._build_url("25176015")
    pubmed_cache = HttpCache(root=tmp_path / "pubmed", ttl_seconds=3600)
    pubmed_cache.set(pubmed_url, b"", pubmed_xml)

    # --- Resolve -----------------------------------------------------------
    resolver = StudyResolver(cache_dir=tmp_path)
    trial = _trial("McMurray 2014")
    result = resolver.resolve(trial, study_string="McMurray 2014")

    assert result.method is ResolutionMethod.AUTHOR_YEAR
    assert result.pmid == "25176015"
    assert result.first_affiliation_raw is not None
    assert "Glasgow" in result.first_affiliation_raw
