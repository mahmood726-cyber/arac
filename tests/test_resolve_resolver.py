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
