"""Tier-A (Authorship) classifier — is the first OR senior author African?

Source priority:
- PubMed efetch first-author affiliation → African substring scan
- PubMed efetch senior-author (= last author) affiliation → African substring scan
- AFRICAN_LED if either matches
- NOT_AFRICAN_LED if both have data and neither matches
- INSUFFICIENT_DATA if neither has affiliation data, or if no PMID

Confidence levels:
- 0.85 — first-author match (positive or negative; first author is the most direct signal)
- 0.75 — only senior-author match (slightly weaker; senior often = group head, not necessarily geographic origin)
- 0.0 — INSUFFICIENT
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arac.classify.african_countries import _load_aliases
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import ResolvedMetadata


class TierA(Enum):
    AFRICAN_LED = "african_led"
    NOT_AFRICAN_LED = "not_african_led"
    INSUFFICIENT_DATA = "insufficient_data"


class AuthorPosition(Enum):
    FIRST = "first"
    SENIOR = "senior"
    NONE = "none"


@dataclass(frozen=True)
class TierAResult:
    trial_id: str
    tier_a: TierA
    matched_position: AuthorPosition
    confidence: float
    matched_country: Optional[str]


def _scan_for_african_country(affiliation: str) -> Optional[str]:
    """Return the matched alias (lowercase) if any African country alias is a
    substring of `affiliation`, else None."""
    if not affiliation:
        return None
    aliases = _load_aliases()
    aff_lower = affiliation.lower()
    for alias in aliases:
        if alias in aff_lower:
            return alias
    return None


class TierAClassifier:
    def __init__(self, pubmed_client: PubMedClient) -> None:
        self._pubmed = pubmed_client

    def classify(self, meta: ResolvedMetadata) -> TierAResult:
        if not meta.pmid:
            return TierAResult(
                trial_id=meta.trial_id,
                tier_a=TierA.INSUFFICIENT_DATA,
                matched_position=AuthorPosition.NONE,
                confidence=0.0,
                matched_country=None,
            )

        record = self._pubmed.efetch(meta.pmid)
        if record is None or not record.authors:
            return TierAResult(
                trial_id=meta.trial_id,
                tier_a=TierA.INSUFFICIENT_DATA,
                matched_position=AuthorPosition.NONE,
                confidence=0.0,
                matched_country=None,
            )

        first_aff = record.authors[0].affiliation if record.authors else None
        senior_aff = (
            record.authors[-1].affiliation
            if len(record.authors) >= 2 else None
        )

        # Both missing → insufficient
        if not first_aff and not senior_aff:
            return TierAResult(
                trial_id=meta.trial_id,
                tier_a=TierA.INSUFFICIENT_DATA,
                matched_position=AuthorPosition.NONE,
                confidence=0.0,
                matched_country=None,
            )

        first_match = _scan_for_african_country(first_aff) if first_aff else None
        senior_match = _scan_for_african_country(senior_aff) if senior_aff else None

        if first_match:
            return TierAResult(
                trial_id=meta.trial_id,
                tier_a=TierA.AFRICAN_LED,
                matched_position=AuthorPosition.FIRST,
                confidence=0.85,
                matched_country=first_match.title(),
            )
        if senior_match:
            return TierAResult(
                trial_id=meta.trial_id,
                tier_a=TierA.AFRICAN_LED,
                matched_position=AuthorPosition.SENIOR,
                confidence=0.75,
                matched_country=senior_match.title(),
            )

        # At least one had data; neither matched African.
        return TierAResult(
            trial_id=meta.trial_id,
            tier_a=TierA.NOT_AFRICAN_LED,
            matched_position=AuthorPosition.NONE,
            confidence=0.85 if first_aff else 0.75,
            matched_country=None,
        )
