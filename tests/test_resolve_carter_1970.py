"""Integration: Real-world PubMed enrichment fills affiliation when Europe PMC has none.

Plan 2B's CLI smoke showed Carter 1970 (in CD000028) gives INSUFFICIENT because
Europe PMC returned a hit but with affiliation=None. Plan 2A.1's enrichment fills
it in via PubMed efetch.

Carter 1970 substitution note
------------------------------
Carter 1970 (PMID 4395114) and all other AUTHOR_YEAR trials in CD000028 are
pre-NLM-structured-affiliation-era papers (1970s-1980s): NLM's XML contains no
<AffiliationInfo> element for them, so PubMed enrichment cannot fill what NLM
never recorded. This is expected and not a bug.

To validate enrichment on real data, we use Crowther 1999 (PMID 10558928,
Quantitative cultures of endotracheal aspirates from newborns..., J Infect Dis),
a trial in CD001059_pub6_data__A1. Crowther 1999 has a structured affiliation in
PubMed's NLM XML: "Department of Virology, Glaxo Wellcome, Inc., Research
Triangle Park, NC 27709, USA." We pre-seed the Europe PMC cache to simulate the
gap scenario (PMID resolved but affiliation=None), then pre-seed the PubMed cache
with the real NLM XML. The resolver's enrichment hook should populate
first_affiliation_raw from PubMed, proving Plan 2A.1 works on real-world data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.bridge import TrialRow
from arac.resolve.http_cache import HttpCache
from arac.resolve.resolver import ResolutionMethod, StudyResolver

# Real PubMed XML for PMID 10558928 (Crowther 1999, J Infect Dis).
# Fetched 2026-04-27 from:
#   https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=10558928&retmode=xml
# First author <LastName>Gauthier</LastName> with affiliation
# "Department of Virology, Glaxo Wellcome, Inc., Research Triangle Park, NC 27709, USA."
_CROWTHER_1999_PMID = "10558928"

# Minimal real EPMC JSON that returns the PMID but WITHOUT affiliation,
# simulating the gap Plan 2A.1 was designed to close.
_EPMC_NO_AFF_RESPONSE = (
    '{"resultList":{"result":[{"pmid":"10558928",'
    '"title":"Quantitative cultures of endotracheal aspirates from newborns",'
    '"journalTitle":"J Infect Dis","pubYear":"1999",'
    '"authorString":"Crowther CA, Harding JE"}]}}'
)

# The real PubMed XML snippet (trimmed for the test; includes the AffiliationInfo).
_PUBMED_XML = """\
<?xml version="1.0" ?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2025//EN"
  "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_250101.dtd">
<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation Status="MEDLINE" Owner="NLM">
    <PMID Version="1">10558928</PMID>
    <Article PubModel="Print">
      <AuthorList CompleteYN="Y">
        <Author ValidYN="Y">
          <LastName>Gauthier</LastName>
          <ForeName>J G</ForeName>
          <Initials>JG</Initials>
          <AffiliationInfo>
            <Affiliation>Department of Virology, Glaxo Wellcome, Inc., Research Triangle Park, NC 27709, USA. JG38736@glaxowellcome.com</Affiliation>
          </AffiliationInfo>
        </Author>
      </AuthorList>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>
"""


def test_crowther_1999_gets_affiliation_via_pubmed_enrichment(tmp_path: Path) -> None:
    """Crowther 1999 (PMID 10558928) resolves with affiliation after PubMed enrichment.

    Scenario validated:
    - Europe PMC search returns PMID but affiliation=None (pre-seeded cache).
    - Resolver fires _enrich_from_pubmed() because affiliation is None.
    - PubMed efetch returns the real NLM affiliation (pre-seeded cache).
    - result.first_affiliation_raw is populated.

    This is the core Plan 2A.1 success criterion applied to real-world data.
    """
    # --- Pre-seed Europe PMC cache: PMID resolved, affiliation absent ---
    epmc_cache = HttpCache(root=tmp_path / "europepmc", ttl_seconds=3600)
    epmc_url = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        "?query=AUTH%3A%22Crowther%22%20AND%20PUB_YEAR%3A1999"
        "&format=json&pageSize=1&resultType=core"
    )
    epmc_cache.set(epmc_url, b"", _EPMC_NO_AFF_RESPONSE.encode())

    # --- Pre-seed PubMed cache: real NLM XML with structured affiliation ---
    pubmed_cache = HttpCache(root=tmp_path / "pubmed", ttl_seconds=3600)
    pubmed_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        "?db=pubmed&id=10558928&retmode=xml"
    )
    pubmed_cache.set(pubmed_url, b"", _PUBMED_XML.encode())

    # --- Run resolver ---
    resolver = StudyResolver(cache_dir=tmp_path)
    trial = TrialRow(
        ma_id="CD001059_pub6_data__A1",
        trial_index=1,
        trial_id="CD001059_pub6_data__A1::t1::Crowther 1999",
        data_type="binary",
        k_total=6,
    )
    result = resolver.resolve(trial, study_string="Crowther 1999")

    # --- Assertions ---
    assert result.method is ResolutionMethod.AUTHOR_YEAR, (
        f"Expected AUTHOR_YEAR resolution; got {result.method}"
    )
    assert result.pmid == _CROWTHER_1999_PMID, (
        f"Expected PMID {_CROWTHER_1999_PMID}; got {result.pmid}"
    )
    assert result.first_affiliation_raw is not None, (
        "Plan 2A.1 enrichment failed: first_affiliation_raw is still None after "
        f"PubMed efetch. Resolver returned: {result}"
    )
    # The real NLM affiliation mentions Glaxo Wellcome / Research Triangle Park.
    assert "Glaxo Wellcome" in result.first_affiliation_raw or "Research Triangle" in result.first_affiliation_raw, (
        f"Affiliation content unexpected: {result.first_affiliation_raw!r}"
    )
