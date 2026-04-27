"""Accuracy regression: composite resolver matches expected resolutions on smoke fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arac.bridge import TrialRow
from arac.resolve.resolver import ResolutionMethod, StudyResolver


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "resolve_smoke.json"
CASSETTE_DIR = Path(__file__).parent / "cassettes"


def _trial(idx: int, study_string: str) -> TrialRow:
    return TrialRow(
        ma_id="SMOKE_MA",
        trial_index=idx,
        trial_id=f"SMOKE_MA::t{idx}",
        data_type="binary",
        k_total=5,
    )


@pytest.mark.vcr(cassette_library_dir=str(CASSETTE_DIR), record_mode="none")
def test_smoke_fixture_resolves(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    trials = fixture["trials"]
    resolver = StudyResolver(cache_dir=tmp_path)

    method_lookup = {
        "acronym": ResolutionMethod.ACRONYM,
        "nct_direct": ResolutionMethod.NCT_DIRECT,
        "author_year": ResolutionMethod.AUTHOR_YEAR,
        "failed": ResolutionMethod.FAILED,
    }

    correct = 0
    mismatches = []
    for i, t in enumerate(trials):
        result = resolver.resolve(
            _trial(i, t["study_string"]),
            study_string=t["study_string"],
        )
        expected_method = method_lookup[t["expected_method"]]
        if result.method is not expected_method:
            mismatches.append(
                f"  '{t['study_string']}': expected {expected_method.value}, got {result.method.value}"
            )
            continue
        if t.get("expected_pmid") and result.pmid != t["expected_pmid"]:
            mismatches.append(
                f"  '{t['study_string']}': expected pmid {t['expected_pmid']}, got {result.pmid}"
            )
            continue
        if t.get("expected_nct_id") and result.nct_id != t["expected_nct_id"]:
            mismatches.append(
                f"  '{t['study_string']}': expected nct {t['expected_nct_id']}, got {result.nct_id}"
            )
            continue
        correct += 1

    accuracy = correct / len(trials)
    assert accuracy >= 0.8, (
        f"resolver accuracy {accuracy:.0%} below 80% gate "
        f"({correct}/{len(trials)} correct)\nMismatches:\n"
        + "\n".join(mismatches)
    )
