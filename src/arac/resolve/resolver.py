"""Composite metadata resolver -- orchestrates parser + acronym table + Europe PMC + CT.gov.

For Plan 2A's scope, the resolver is read-only: it takes a (TrialRow, study_string)
pair and returns a ResolvedMetadata record. The TrialRow doesn't itself carry
the Study string (Plan 1's bridge intentionally kept it minimal); the caller
(Plan 2B's classifier or the smoke runner) joins the Pairwise70 dataframe row
back to its TrialRow and passes both in.

Confidence scoring (hand-set defaults; Plan 2D will calibrate against gold standard):
- 1.00 -- NCT-direct hit returning a CT.gov record
- 0.95 -- Acronym hit in the seed table
- 0.80 -- Author-Year hit returning a single Europe PMC result
- 0.00 -- failed (Unknown form, or all dispatchers returned None)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from arac.bridge import TrialRow
from arac.resolve.acronyms import AcronymEntry, lookup_acronym
from arac.resolve.ctgov import CTGovClient, CTGovStudy
from arac.resolve.europepmc import EuropePMCClient, EuropePMCHit
from arac.resolve.parser import StudyForm, parse_study_string
from arac.resolve.pubmed import PubMedClient


class ResolutionMethod(Enum):
    NCT_DIRECT = "nct_direct"
    ACRONYM = "acronym"
    AUTHOR_YEAR = "author_year"
    FAILED = "failed"


@dataclass(frozen=True)
class ResolvedMetadata:
    trial_id: str
    method: ResolutionMethod
    confidence: float
    pmid: Optional[str]
    nct_id: Optional[str]
    title: Optional[str]
    first_author: Optional[str]
    first_affiliation_raw: Optional[str]
    country_list: tuple[str, ...]


class StudyResolver:
    def __init__(self, cache_dir: Path) -> None:
        self._epmc = EuropePMCClient(cache_dir=cache_dir / "europepmc")
        self._ctgov = CTGovClient(cache_dir=cache_dir / "ctgov")
        self._pubmed = PubMedClient(cache_dir=cache_dir / "pubmed")

    def _from_acronym(self, trial: TrialRow, entry: AcronymEntry) -> ResolvedMetadata:
        return ResolvedMetadata(
            trial_id=trial.trial_id,
            method=ResolutionMethod.ACRONYM,
            confidence=0.95,
            pmid=entry.pmid,
            nct_id=entry.nct_id,
            title=entry.full_name,
            first_author=None,
            first_affiliation_raw=None,
            country_list=(),
        )

    def _from_ctgov(self, trial: TrialRow, study: CTGovStudy) -> ResolvedMetadata:
        return ResolvedMetadata(
            trial_id=trial.trial_id,
            method=ResolutionMethod.NCT_DIRECT,
            confidence=1.0,
            pmid=None,
            nct_id=study.nct_id,
            title=study.title,
            first_author=None,
            first_affiliation_raw=None,
            country_list=study.country_list,
        )

    def _from_europepmc(self, trial: TrialRow, hit: EuropePMCHit) -> ResolvedMetadata:
        affiliation = hit.first_affiliation_raw
        if affiliation is None and hit.pmid:
            pubmed_record = self._pubmed.efetch(hit.pmid)
            if pubmed_record is not None and pubmed_record.first_author_affiliation:
                affiliation = pubmed_record.first_author_affiliation
        return ResolvedMetadata(
            trial_id=trial.trial_id,
            method=ResolutionMethod.AUTHOR_YEAR,
            confidence=0.80,
            pmid=hit.pmid,
            nct_id=None,
            title=hit.title,
            first_author=hit.first_author,
            first_affiliation_raw=affiliation,
            country_list=(),
        )

    def _failed(self, trial: TrialRow) -> ResolvedMetadata:
        return ResolvedMetadata(
            trial_id=trial.trial_id,
            method=ResolutionMethod.FAILED,
            confidence=0.0,
            pmid=None,
            nct_id=None,
            title=None,
            first_author=None,
            first_affiliation_raw=None,
            country_list=(),
        )

    def resolve(self, trial: TrialRow, study_string: str) -> ResolvedMetadata:
        ref = parse_study_string(study_string)

        if ref.form is StudyForm.NCT_DIRECT and ref.nct_id:
            study = self._ctgov.get_study(ref.nct_id)
            if study is not None:
                return self._from_ctgov(trial, study)
            return self._failed(trial)

        if ref.form is StudyForm.ACRONYM and ref.acronym:
            entry = lookup_acronym(ref.acronym)
            if entry is not None:
                return self._from_acronym(trial, entry)
            # Acronym not in seed table -- Plan 2A treats as failed.
            return self._failed(trial)

        if ref.form is StudyForm.AUTHOR_YEAR and ref.author_lastname and ref.year:
            hit = self._epmc.search_author_year(ref.author_lastname, ref.year)
            if hit is not None:
                return self._from_europepmc(trial, hit)
            return self._failed(trial)

        return self._failed(trial)
