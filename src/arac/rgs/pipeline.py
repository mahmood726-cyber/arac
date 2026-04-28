"""End-to-end RGS atlas pipeline: MA → tier subsets → RGS rows.

Composes:
- Plan 2A's resolver (StudyResolver) — for trial → ResolvedMetadata
- Plan 2B's TierSClassifier — site location
- Plan 2C's TierAClassifier — first/senior author
- Plan 2D's TierPClassifier — participant geography (LLM-based)
- Plan 3A's RGSEngine — gap metrics

Configuration via TierMode flag determines which classifiers run, controlling
both runtime cost (Tier-P needs LLM API calls) and output completeness.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterator, Optional, Protocol

from arac.bridge import MARecord, TrialRow
from arac.classify.tier_a import TierA, TierAResult
from arac.classify.tier_p import TierP, TierPResult
from arac.classify.tier_s import TierS, TierSResult
from arac.resolve.resolver import ResolvedMetadata
from arac.rgs.engine import RGSEngine, RGSResult, RGSTier


class TierMode(Enum):
    S_ONLY = "s_only"
    SA_ONLY = "sa_only"
    SAP = "sap"


class _Resolver(Protocol):
    def resolve(self, trial: TrialRow, study_string: str) -> ResolvedMetadata: ...


class _TierS(Protocol):
    def classify(self, meta: ResolvedMetadata) -> TierSResult: ...


class _TierA(Protocol):
    def classify(self, meta: ResolvedMetadata) -> TierAResult: ...


class _TierP(Protocol):
    def classify(self, meta: ResolvedMetadata) -> TierPResult: ...


@dataclass
class RGSPipeline:
    resolver: _Resolver
    tier_s: _TierS
    tier_a: Optional[_TierA] = None
    tier_p: Optional[_TierP] = None
    study_string_lookup: Optional[Callable[[TrialRow], str]] = None
    engine: RGSEngine = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.engine is None:
            object.__setattr__(self, "engine", RGSEngine())

    def _resolve_all(self, ma: MARecord) -> list[ResolvedMetadata]:
        if self.study_string_lookup is None:
            raise RuntimeError(
                "RGSPipeline.study_string_lookup must be provided — "
                "it maps a TrialRow to its Study string from Pairwise70."
            )
        return [
            self.resolver.resolve(t, self.study_string_lookup(t))
            for t in ma.trials
        ]

    def run(
        self,
        records: list[MARecord],
        tier_mode: TierMode,
    ) -> Iterator[RGSResult]:
        if tier_mode is TierMode.SAP and self.tier_p is None:
            raise RuntimeError(
                "TierMode.SAP requires tier_p classifier; got None. "
                "Use SA_ONLY or S_ONLY if Tier-P is unavailable."
            )
        if tier_mode in (TierMode.SAP, TierMode.SA_ONLY) and self.tier_a is None:
            raise RuntimeError(
                f"TierMode.{tier_mode.value} requires tier_a; got None."
            )

        for ma in records:
            metas = self._resolve_all(ma)
            tier_s_results = [self.tier_s.classify(m) for m in metas]
            tier_s_indices = tuple(
                i for i, r in enumerate(tier_s_results)
                if r.tier_s is TierS.AFRICAN_SITE
            )
            yield self.engine.compute(ma, RGSTier.SITE, tier_s_indices)

            if tier_mode is TierMode.S_ONLY:
                continue

            assert self.tier_a is not None  # checked above
            tier_a_results = [self.tier_a.classify(m) for m in metas]
            tier_a_indices = tuple(
                i for i, r in enumerate(tier_a_results)
                if r.tier_a is TierA.AFRICAN_LED
            )
            yield self.engine.compute(ma, RGSTier.AUTHORSHIP, tier_a_indices)

            if tier_mode is TierMode.SA_ONLY:
                continue

            assert self.tier_p is not None
            tier_p_results = [self.tier_p.classify(m) for m in metas]
            tier_p_indices = tuple(
                i for i, r in enumerate(tier_p_results)
                if r.tier_p is TierP.AFRICAN_MAJORITY
            )
            yield self.engine.compute(ma, RGSTier.PARTICIPANT, tier_p_indices)
