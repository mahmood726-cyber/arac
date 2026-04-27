"""Pre-flight regression: verify Pairwise70 .rda files contain a per-trial
identifier column. The pre-flight discovery (2026-04-27) found that the
`Study` field is universally present, even though it is freeform (Author-Year
+ NCT IDs + trial acronyms). This test guards against future Pairwise70
updates that might drop or rename this column.

If this test fails, Plan 2 (classifier) cannot proceed without an alternate
metadata source. STOP and escalate to the user.
"""

from __future__ import annotations

from pathlib import Path

import pyreadr
import pytest


# Identifier columns we hope to find. At least ONE must be present per file
# for downstream Tier-S/A/P classification to be feasible from .rda alone.
# Pre-flight discovery (2026-04-27) confirmed `Study` is the canonical column.
ACCEPTABLE_TRIAL_ID_COLS = {
    "study", "study_id", "trial_id", "nct", "nct_id",
    "pmid", "pubmed_id", "doi", "first_author", "author", "ref",
}


def test_pairwise70_rda_contains_trial_identifier(pairwise70_dir: Path) -> None:
    sample = sorted(pairwise70_dir.glob("CD*.rda"))[:5]
    assert sample, f"No .rda files found in {pairwise70_dir}"

    found_id_cols: set[str] = set()
    inspected_objects: list[str] = []

    for rda in sample:
        bundle = pyreadr.read_r(str(rda))
        for obj_name, df in bundle.items():
            inspected_objects.append(f"{rda.name}:{obj_name}")
            cols_lower = {c.lower() for c in df.columns}
            found_id_cols |= (cols_lower & ACCEPTABLE_TRIAL_ID_COLS)

    assert found_id_cols, (
        "PRE-FLIGHT FAILURE: no trial-bibliographic identifier column found "
        f"in any of {len(sample)} sampled .rda files. "
        f"Inspected objects: {inspected_objects[:10]}. "
        f"Acceptable columns were: {sorted(ACCEPTABLE_TRIAL_ID_COLS)}. "
        "Plan 2 (classifier) cannot run from .rda alone — escalate to user "
        "before proceeding."
    )
