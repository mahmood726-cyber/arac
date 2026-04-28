"""Tier-P (Participant geography) classifier — does this trial have ≥50% African
participants?

Source: PubMed efetch for the trial's abstract → LLM-based extraction →
threshold check on african_participant_pct.

Confidence levels (output):
- 0.95 — extractor returned "high" confidence with explicit percentages
- 0.80 — extractor returned "medium" confidence (counts → computed pct)
- 0.55 — extractor returned "low" confidence (country list only, estimated)
- 0.00 — INSUFFICIENT (no abstract, or extractor said "insufficient")
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arac.classify.tier_p_extractor import ExtractionInput, TierPExtractor
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import ResolvedMetadata


_THRESHOLD_PCT = 50.0


class TierP(Enum):
    AFRICAN_MAJORITY = "african_majority"
    NOT_AFRICAN_MAJORITY = "not_african_majority"
    INSUFFICIENT_DATA = "insufficient_data"


_CONFIDENCE_BY_LEVEL = {
    "high": 0.95,
    "medium": 0.80,
    "low": 0.55,
    "insufficient": 0.0,
}


@dataclass(frozen=True)
class TierPResult:
    trial_id: str
    tier_p: TierP
    confidence: float
    african_pct: Optional[float]
    countries_mentioned: tuple[str, ...]
    evidence_source: Optional[str]


class TierPClassifier:
    def __init__(
        self,
        pubmed_client: PubMedClient,
        extractor: TierPExtractor,
    ) -> None:
        self._pubmed = pubmed_client
        self._extractor = extractor

    def classify(self, meta: ResolvedMetadata) -> TierPResult:
        if not meta.pmid:
            return self._insufficient(meta.trial_id)

        record = self._pubmed.efetch(meta.pmid)
        if record is None or not record.abstract_text:
            return self._insufficient(meta.trial_id)

        item = ExtractionInput(
            pmid=record.pmid,
            title=meta.title or "",
            abstract=record.abstract_text,
        )
        geo = self._extractor.extract(item)

        if geo.confidence == "insufficient" or geo.african_participant_pct is None:
            return TierPResult(
                trial_id=meta.trial_id,
                tier_p=TierP.INSUFFICIENT_DATA,
                confidence=0.0,
                african_pct=None,
                countries_mentioned=tuple(geo.countries_mentioned),
                evidence_source=geo.evidence_source,
            )

        confidence = _CONFIDENCE_BY_LEVEL.get(geo.confidence, 0.0)
        if geo.african_participant_pct >= _THRESHOLD_PCT:
            return TierPResult(
                trial_id=meta.trial_id,
                tier_p=TierP.AFRICAN_MAJORITY,
                confidence=confidence,
                african_pct=geo.african_participant_pct,
                countries_mentioned=tuple(geo.countries_mentioned),
                evidence_source=geo.evidence_source,
            )
        return TierPResult(
            trial_id=meta.trial_id,
            tier_p=TierP.NOT_AFRICAN_MAJORITY,
            confidence=confidence,
            african_pct=geo.african_participant_pct,
            countries_mentioned=tuple(geo.countries_mentioned),
            evidence_source=geo.evidence_source,
        )

    def _insufficient(self, trial_id: str) -> TierPResult:
        return TierPResult(
            trial_id=trial_id,
            tier_p=TierP.INSUFFICIENT_DATA,
            confidence=0.0,
            african_pct=None,
            countries_mentioned=(),
            evidence_source=None,
        )
