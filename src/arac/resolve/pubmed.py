"""PubMed E-Utilities efetch client.

Given a PMID, fetches the NLM canonical XML and extracts the first author's
lastname + structured affiliation. Used by the composite resolver as an
enrichment step when Europe PMC returns a hit but no affiliation string.

NLM's E-Utilities are public, no auth required, but rate-limited to 3 req/sec
without an API key. Cached responses make this a non-issue for ARAC's batch
profile (most PMIDs hit the cache after the first run).

Per lessons.md "Handle auth expiry, rate limits, Cloudflare blocks": the
client treats HTTP 429 / 503 as transient and falls through to None rather
than raising -- callers (the composite resolver) treat None as "enrichment
unavailable" and continue with the original Europe PMC affiliation (which
may itself be None -- that's fine, Tier-S handles it).

PubMedRecord carries:
- pmid (legacy)
- first_author_lastname / first_author_affiliation (legacy, populated from authors[0])
- authors: tuple[PubMedAuthor, ...] (new in Plan 2C — full ordered author list)

The authors tuple is the source of truth; first_author_* fields are derived at
parse time. Last author = authors[-1] when len(authors) >= 1.
"""

from __future__ import annotations

import defusedxml.ElementTree as ET  # noqa: N817 — security: parse untrusted XML safely
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

from arac.resolve.http_cache import HttpCache


_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_DEFAULT_TTL_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True)
class PubMedAuthor:
    lastname: Optional[str]
    forename: Optional[str]
    affiliation: Optional[str]


@dataclass(frozen=True)
class PubMedRecord:
    pmid: str
    first_author_lastname: Optional[str]
    first_author_affiliation: Optional[str]
    authors: tuple[PubMedAuthor, ...] = field(default_factory=tuple)
    abstract_text: Optional[str] = None


class PubMedClient:
    def __init__(
        self,
        cache_dir: Path,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._cache = HttpCache(root=cache_dir, ttl_seconds=ttl_seconds)
        self._timeout = timeout_seconds

    def _build_url(self, pmid: str) -> str:
        return f"{_BASE_URL}?db=pubmed&id={pmid}&retmode=xml"

    def _parse_author(self, author_el: ET.Element) -> PubMedAuthor:
        lastname_el = author_el.find("LastName")
        forename_el = author_el.find("ForeName")
        affiliation_el = author_el.find("AffiliationInfo/Affiliation")
        return PubMedAuthor(
            lastname=lastname_el.text.strip() if lastname_el is not None and lastname_el.text else None,
            forename=forename_el.text.strip() if forename_el is not None and forename_el.text else None,
            affiliation=affiliation_el.text.strip() if affiliation_el is not None and affiliation_el.text else None,
        )

    def efetch(self, pmid: str) -> Optional[PubMedRecord]:
        url = self._build_url(pmid)
        cached = self._cache.get(url, b"")
        if cached is None:
            try:
                r = httpx.get(
                    url,
                    timeout=self._timeout,
                    headers={"User-Agent": "arac/0.1 (research; mahmood726@gmail.com)"},
                )
            except httpx.HTTPError:
                return None
            if r.status_code in (429, 503):
                # Rate-limited -- don't cache, return None.
                return None
            if r.status_code == 404:
                self._cache.set(
                    url,
                    b"",
                    b'<?xml version="1.0"?><PubmedArticleSet></PubmedArticleSet>',
                )
                return None
            r.raise_for_status()
            cached = r.content
            self._cache.set(url, b"", cached)

        try:
            root = ET.fromstring(cached)
        except ET.ParseError:
            return None

        article = root.find(".//PubmedArticle")
        if article is None:
            return None

        author_els = article.findall(".//AuthorList/Author")
        authors = tuple(self._parse_author(el) for el in author_els)

        first = authors[0] if authors else None

        # Extract abstract — concatenate all <AbstractText> elements (some PubMed
        # records have multi-section structured abstracts: BACKGROUND/METHODS/RESULTS).
        abstract_els = article.findall(".//Abstract/AbstractText")
        abstract_parts: list[str] = []
        for el in abstract_els:
            label = el.attrib.get("Label")
            text = (el.text or "").strip()
            if not text:
                continue
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract_text = "\n\n".join(abstract_parts) if abstract_parts else None

        return PubMedRecord(
            pmid=pmid,
            first_author_lastname=first.lastname if first else None,
            first_author_affiliation=first.affiliation if first else None,
            authors=authors,
            abstract_text=abstract_text,
        )
