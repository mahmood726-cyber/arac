"""ClinicalTrials.gov v2 API client.

Only supports the one operation ARAC needs: fetch a study by NCT ID and return
the country list (deduplicated, derived from contactsLocationsModule.locations)
plus the lead sponsor name. Country classification (African vs not) is Plan 2B's
job — this module just returns the raw country strings.

All HTTP calls go through the file-based cache. TTL = 30 days (study-record
updates are rare for completed trials).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from arac.resolve.http_cache import HttpCache


_BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
_DEFAULT_TTL_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True)
class CTGovStudy:
    nct_id: str
    title: str
    overall_status: str
    lead_sponsor: str
    country_list: tuple[str, ...]


_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class CTGovClient:
    def __init__(
        self,
        cache_dir: Path,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        timeout_seconds: float = 10.0,
        user_agent: str = _DEFAULT_USER_AGENT,
    ) -> None:
        self._cache = HttpCache(root=cache_dir, ttl_seconds=ttl_seconds)
        self._timeout = timeout_seconds
        self._user_agent = user_agent

    def _build_url(self, nct_id: str) -> str:
        return f"{_BASE_URL}/{nct_id}?format=json"

    def get_study(self, nct_id: str) -> Optional[CTGovStudy]:
        url = self._build_url(nct_id)
        cached = self._cache.get(url, b"")
        if cached is None:
            r = httpx.get(url, timeout=self._timeout, headers={"User-Agent": self._user_agent})
            if r.status_code == 404:
                self._cache.set(url, b"", b'{"protocolSection":null}')
                return None
            r.raise_for_status()
            cached = r.content
            self._cache.set(url, b"", cached)

        data = json.loads(cached)
        proto = data.get("protocolSection")
        if proto is None:
            return None

        ident = proto.get("identificationModule", {})
        status = proto.get("statusModule", {})
        sponsor = proto.get("sponsorCollaboratorsModule", {}).get(
            "leadSponsor", {}
        ).get("name", "")
        locations = (
            proto.get("contactsLocationsModule", {}).get("locations", []) or []
        )
        countries = tuple(sorted({
            loc.get("country", "")
            for loc in locations
            if loc.get("country")
        }))

        return CTGovStudy(
            nct_id=ident.get("nctId", nct_id),
            title=ident.get("briefTitle", ""),
            overall_status=status.get("overallStatus", ""),
            lead_sponsor=sponsor,
            country_list=countries,
        )
