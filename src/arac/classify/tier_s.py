"""Tier-S (Site) classifier — does this trial have >=1 site in an African country?

Sources, in priority order (first non-INSUFFICIENT result wins):
1. AACT lookup by NCT ID — confidence 0.97 (ground truth from CT.gov mirror).
   Returns AFRICAN_SITE or NO_AFRICAN_SITE. Falls through only if AACT has
   zero facilities rows for this NCT (e.g. trial pre-dates CT.gov coverage).
2. Affiliation substring scan — confidence 0.55 (low; affiliation country is a
   proxy for first-author location, not trial-site location).
3. INSUFFICIENT_DATA — when neither source applies (no NCT, no affiliation, or
   meta.method is FAILED).

The affiliation scanner is case-insensitive and uses all known aliases from
african_countries.yaml, matching on substring presence in the raw affiliation
string. False negatives are expected for non-English or historical country
names — Plan 2D's IRR will quantify the gap.

Confidence values (hand-set, pre-calibration):
- 0.97  AACT hit (active-site ground truth)
- 0.55  Affiliation substring match
- 0.0   INSUFFICIENT_DATA
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arac.classify.aact import AACTClient
from arac.classify.african_countries import is_african_country, scan_for_african_country
from arac.resolve.resolver import ResolvedMetadata


class TierS(Enum):
    AFRICAN_SITE = "african_site"
    NO_AFRICAN_SITE = "no_african_site"
    INSUFFICIENT_DATA = "insufficient_data"


class TierSSource(Enum):
    AACT = "aact"
    AFFILIATION = "affiliation"
    NONE = "none"


@dataclass(frozen=True)
class TierSResult:
    trial_id: str
    tier_s: TierS
    source: TierSSource
    confidence: float
    matched_country: Optional[str]  # African country name found, if any


class TierSClassifier:
    """Composite Tier-S classifier.

    Parameters
    ----------
    aact_client:
        Pre-configured AACTClient. Pass None to disable AACT lookups (affiliation
        fallback only). Tests inject None when AACT is not configured.
    """

    def __init__(self, aact_client: Optional[AACTClient]) -> None:
        self._aact = aact_client

    def classify(self, meta: ResolvedMetadata) -> TierSResult:
        """Classify a trial's Tier-S status from its ResolvedMetadata.

        Returns a frozen TierSResult. Never raises — INSUFFICIENT_DATA is
        returned when classification cannot be performed.
        """
        # --- Source 1: AACT lookup on NCT ID ---
        if self._aact is not None and meta.nct_id:
            countries = self._aact.get_countries(meta.nct_id)
            if countries:
                # get_countries already filters removed rows; first African match wins.
                african_match = next(
                    (c for c in countries if is_african_country(c)), None
                )
                if african_match:
                    return TierSResult(
                        trial_id=meta.trial_id,
                        tier_s=TierS.AFRICAN_SITE,
                        source=TierSSource.AACT,
                        confidence=0.97,
                        matched_country=african_match,
                    )
                return TierSResult(
                    trial_id=meta.trial_id,
                    tier_s=TierS.NO_AFRICAN_SITE,
                    source=TierSSource.AACT,
                    confidence=0.97,
                    matched_country=None,
                )
            # NCT present but AACT has no active-country rows — fall through to
            # affiliation, then INSUFFICIENT.

        # --- Source 2: Affiliation word-boundary scan (Plan 2C.1) ---
        if meta.first_affiliation_raw:
            matched_alias = scan_for_african_country(meta.first_affiliation_raw)
            if matched_alias:
                return TierSResult(
                    trial_id=meta.trial_id,
                    tier_s=TierS.AFRICAN_SITE,
                    source=TierSSource.AFFILIATION,
                    confidence=0.55,
                    matched_country=matched_alias.title(),
                )
            return TierSResult(
                trial_id=meta.trial_id,
                tier_s=TierS.NO_AFRICAN_SITE,
                source=TierSSource.AFFILIATION,
                confidence=0.55,
                matched_country=None,
            )

        # --- Source 3: INSUFFICIENT_DATA ---
        return TierSResult(
            trial_id=meta.trial_id,
            tier_s=TierS.INSUFFICIENT_DATA,
            source=TierSSource.NONE,
            confidence=0.0,
            matched_country=None,
        )
