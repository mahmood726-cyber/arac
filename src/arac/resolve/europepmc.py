"""Europe PMC search client.

Only supports the one query shape ARAC needs: Author-lastname + publication year.
Returns the top hit's PMID, title, journal, year, and (when present) the
first author's affiliation string. Affiliation parsing into ROR/country is
Plan 2C's job — this module just surfaces the raw string.

All HTTP calls go through the file-based cache. TTL = 30 days (Europe PMC
records do not change often once published).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx

from arac.resolve.http_cache import HttpCache


_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_DEFAULT_TTL_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True)
class EuropePMCHit:
    pmid: str
    title: str
    journal: str
    year: int
    first_author: Optional[str]
    first_affiliation_raw: Optional[str]


class EuropePMCClient:
    def __init__(
        self,
        cache_dir: Path,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._cache = HttpCache(root=cache_dir, ttl_seconds=ttl_seconds)
        self._timeout = timeout_seconds

    def _build_url(self, author_lastname: str, year: int) -> str:
        query = f'AUTH:"{author_lastname}" AND PUB_YEAR:{year}'
        return (
            f"{_BASE_URL}"
            f"?query={quote(query)}"
            f"&format=json&pageSize=1&resultType=core"
        )

    def search_author_year(
        self, author_lastname: str, year: int
    ) -> Optional[EuropePMCHit]:
        url = self._build_url(author_lastname, year)
        cached = self._cache.get(url, b"")
        if cached is None:
            r = httpx.get(url, timeout=self._timeout, headers={"User-Agent": "arac/0.1"})
            r.raise_for_status()
            cached = r.content
            self._cache.set(url, b"", cached)
        data = json.loads(cached)
        results = data.get("resultList", {}).get("result", [])
        if not results:
            return None
        top = results[0]
        return EuropePMCHit(
            pmid=str(top.get("pmid", "")),
            title=top.get("title", ""),
            journal=top.get("journalTitle", ""),
            year=int(top.get("pubYear", year)),
            first_author=top.get("authorString", "").split(",")[0].strip() or None,
            first_affiliation_raw=top.get("affiliation"),
        )
