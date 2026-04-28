# ARAC — Plan 3A.2: Recommendation-Change Metric (5th of 5 RGS Metrics)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the **5th and final** spec RGS metric — `recommendation_change`. After this plan, all 5 spec metrics (reproduction_gap, precision_gap_ratio, sign_flip, heterogeneity_gap, recommendation_change) are live in the engine, atlas CSV, and dashboard. v0.8.0 is the "5-of-5 metrics complete" milestone tag.

**Architecture:**
- New module `src/arac/rgs/mcid.py` with per-data-type MCID defaults dict + `classify_ci_vs_mcid(ci_lower, ci_upper, mcid_lower, mcid_upper) -> RecommendationState` (BENEFIT / UNCERTAIN / HARM)
- `RGSEngine.compute()` adds `full_recommendation`, `subset_recommendation`, `recommendation_change` fields
- `recommendation_change = full_state != subset_state` (when both visible; None if invisible)
- Atlas CSV: 21 → 24 columns (+ `full_recommendation`, `subset_recommendation`, `recommendation_change`)
- Dashboard renders the new column + summary metric

**MCID defaults (preliminary — Plan 4 governance will lock per-condition values):**
- Binary (logOR / logRR): MCID = ±log(0.80) ≈ ±0.223 → "important benefit" if effect direction implies clinically-meaningful event-rate change
- Continuous (mean difference): MCID = ±SMD 0.2 (Cohen's small) → outcome-specific MCIDs preregistered later override
- GIV (logHR / logRR via inverse-variance): MCID = ±log(0.85) ≈ ±0.163 → conservative default

**Recommendation states:** BENEFIT (CI excludes MCID on protective side — entirely below `−|MCID|`), HARM (CI excludes MCID on harmful side — entirely above `+|MCID|`), UNCERTAIN (CI overlaps the equivalence zone `[−|MCID|, +|MCID|]`).

**Tech Stack:** Python 3.13. No new dependencies.

**Out of scope:**
- Per-condition MCID overrides via CSV — Plan 4 (preregistration governance)
- HKSJ CI adjustment — Plan 3A.3
- Verification UI — Plan 3C

---

### Task 1: MCID module + recommendation-change metric in RGSEngine

**Files:**
- Create: `C:/Projects/arac/src/arac/rgs/mcid.py`
- Modify: `C:/Projects/arac/src/arac/rgs/engine.py`
- Create: `C:/Projects/arac/tests/test_rgs_mcid.py`
- Modify: `C:/Projects/arac/tests/test_rgs_engine.py`

- [ ] **Step 1: Write failing tests for `mcid.py`**

Create `tests/test_rgs_mcid.py`:

```python
"""MCID classifier: CI vs MCID equivalence zone → BENEFIT / UNCERTAIN / HARM."""

from __future__ import annotations

import math

import pytest

from arac.rgs.mcid import (
    DEFAULT_MCID_BY_DATA_TYPE,
    RecommendationState,
    classify_ci_vs_mcid,
    mcid_for_data_type,
)


def test_default_mcids_present() -> None:
    assert "binary" in DEFAULT_MCID_BY_DATA_TYPE
    assert "continuous" in DEFAULT_MCID_BY_DATA_TYPE
    assert "giv" in DEFAULT_MCID_BY_DATA_TYPE
    # Binary default ≈ ±log(0.80)
    assert abs(DEFAULT_MCID_BY_DATA_TYPE["binary"] - abs(math.log(0.80))) < 1e-6


def test_mcid_for_data_type() -> None:
    assert mcid_for_data_type("binary") > 0
    assert mcid_for_data_type("continuous") > 0
    assert mcid_for_data_type("giv") > 0
    with pytest.raises(KeyError):
        mcid_for_data_type("unknown_type")


def test_classify_benefit_ci_below_negative_mcid() -> None:
    """CI entirely below -MCID → important benefit."""
    state = classify_ci_vs_mcid(ci_lower=-0.5, ci_upper=-0.3, mcid=0.2)
    assert state is RecommendationState.BENEFIT


def test_classify_harm_ci_above_positive_mcid() -> None:
    state = classify_ci_vs_mcid(ci_lower=0.3, ci_upper=0.5, mcid=0.2)
    assert state is RecommendationState.HARM


def test_classify_uncertain_overlaps_equivalence() -> None:
    state = classify_ci_vs_mcid(ci_lower=-0.1, ci_upper=0.1, mcid=0.2)
    assert state is RecommendationState.UNCERTAIN
    state = classify_ci_vs_mcid(ci_lower=-0.3, ci_upper=0.05, mcid=0.2)
    assert state is RecommendationState.UNCERTAIN


def test_classify_handles_none() -> None:
    """None ci bounds → None recommendation state."""
    assert classify_ci_vs_mcid(None, -0.3, 0.2) is None
    assert classify_ci_vs_mcid(-0.5, None, 0.2) is None
```

- [ ] **Step 2: Implement `src/arac/rgs/mcid.py`**

```python
"""Minimum Clinically Important Difference (MCID) infrastructure.

Per ARAC spec §3 step 4: recommendation-change is flagged when the African-
subset pool's CI lands in a different equivalence-zone state than the full
pool's CI. The equivalence zone is [−MCID, +MCID].

States:
- BENEFIT: CI entirely below −MCID (effect is clinically meaningful + protective)
- HARM: CI entirely above +MCID (effect is clinically meaningful + harmful)
- UNCERTAIN: CI overlaps the equivalence zone (no confident clinical claim)

MCID defaults are placeholders; Plan 4's preregistration locks per-condition
values that override these defaults via a per-MA MCID CSV.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional


# Defaults per data_type (absolute values — interpreted as ±MCID equivalence zone).
# All on the natural pooling scale (log scale for binary/giv; raw for continuous).
DEFAULT_MCID_BY_DATA_TYPE: dict[str, float] = {
    "binary": abs(math.log(0.80)),       # ≈ 0.2231 — 20% relative reduction is "important"
    "continuous": 0.2,                    # Cohen's small SMD
    "giv": abs(math.log(0.85)),           # ≈ 0.1625 — conservative for HR/RR
}


class RecommendationState(Enum):
    BENEFIT = "benefit"
    UNCERTAIN = "uncertain"
    HARM = "harm"


def mcid_for_data_type(data_type: str) -> float:
    """Return the default MCID (absolute) for a data type. Raises KeyError if
    the type is unknown — Plan 1's three types are the only supported set."""
    return DEFAULT_MCID_BY_DATA_TYPE[data_type]


def classify_ci_vs_mcid(
    ci_lower: Optional[float],
    ci_upper: Optional[float],
    mcid: float,
) -> Optional[RecommendationState]:
    """Classify a CI against the equivalence zone [−mcid, +mcid].

    Returns None if either bound is None (insufficient data).
    """
    if ci_lower is None or ci_upper is None:
        return None
    if ci_upper < -mcid:
        return RecommendationState.BENEFIT
    if ci_lower > mcid:
        return RecommendationState.HARM
    return RecommendationState.UNCERTAIN
```

- [ ] **Step 3: Run, verify mcid tests PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_rgs_mcid.py -v`
Expected: 6 PASSED.

- [ ] **Step 4: Append failing tests to `test_rgs_engine.py`**

```python
def test_rgs_recommendation_state_populated_when_visible(pairwise70_dir: Path) -> None:
    from arac.bridge import load_all_mas
    from arac.rgs.engine import RGSEngine, RGSTier
    from arac.rgs.mcid import RecommendationState
    mas = load_all_mas(pairwise70_dir, max_reviews=5)
    ma = next((m for m in mas if m.k >= 5), None)
    assert ma is not None
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.SITE, indices=tuple(range(ma.k)))

    assert result.invisible is False
    assert result.full_recommendation in (
        RecommendationState.BENEFIT, RecommendationState.UNCERTAIN, RecommendationState.HARM,
    )
    # Subset = full → recommendations match → no change
    assert result.full_recommendation == result.subset_recommendation
    assert result.recommendation_change is False


def test_rgs_recommendation_change_invisible(pairwise70_dir: Path) -> None:
    from arac.bridge import load_all_mas
    from arac.rgs.engine import RGSEngine, RGSTier
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 3), None)
    assert ma is not None
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.PARTICIPANT, indices=())  # invisible

    assert result.invisible is True
    # full_recommendation populated (we always compute full pool)
    assert result.full_recommendation is not None
    # subset and change are None
    assert result.subset_recommendation is None
    assert result.recommendation_change is None
```

- [ ] **Step 5: Modify `src/arac/rgs/engine.py`**

Extend `RGSResult` with 3 new fields (at end, all `Optional` with `= None` defaults):

```python
full_recommendation: Optional["RecommendationState"] = None
subset_recommendation: Optional["RecommendationState"] = None
recommendation_change: Optional[bool] = None
```

Add import at top:
```python
from arac.rgs.mcid import RecommendationState, classify_ci_vs_mcid, mcid_for_data_type
```

Modify `compute()` to populate the new fields:
- After computing `full` PoolResult: `mcid = mcid_for_data_type(record.data_type)` and `full_rec = classify_ci_vs_mcid(full.ci_lower, full.ci_upper, mcid)`
- For invisible branch: `full_recommendation=full_rec, subset_recommendation=None, recommendation_change=None`
- For visible branch: `subset_rec = classify_ci_vs_mcid(subset.ci_lower, subset.ci_upper, mcid)` and `recommendation_change = (full_rec != subset_rec) if (full_rec is not None and subset_rec is not None) else None`

- [ ] **Step 6: Run, verify all rgs_engine tests PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_rgs_engine.py -v`
Expected: 9 PASSED (7 existing + 2 new).

- [ ] **Step 7: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/rgs/mcid.py src/arac/rgs/engine.py tests/test_rgs_mcid.py tests/test_rgs_engine.py
git commit -m "feat(rgs): recommendation-change metric (CI vs MCID equivalence zone) — 5 of 5 spec metrics"
```

---

### Task 2: Atlas CSV + dashboard updated

**Files:**
- Modify: `C:/Projects/arac/src/arac/rgs/csv_writer.py` — add 3 columns to `RGS_COLUMNS`, extend `_row_to_dict`
- Modify: `C:/Projects/arac/src/arac/rgs/dashboard.py` — `summarize` adds `recommendation_change_count`
- Modify: `C:/Projects/arac/src/arac/rgs/html_template.py` — JS table column for recommendation_change, summary metric
- Modify: `C:/Projects/arac/tests/test_rgs_csv_writer.py` — update for 24 columns
- Modify: `C:/Projects/arac/tests/test_rgs_dashboard.py` — update _seed_atlas + render checks

- [ ] **Step 1: Update `csv_writer.py`**

Append to `RGS_COLUMNS`:
```python
"full_recommendation",
"subset_recommendation",
"recommendation_change",
```

Extend `_row_to_dict` — for the recommendation enum fields, serialize `.value` if not None, else empty string. Use a dedicated helper:

```python
def _enum_cell(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)
```

Then in the dict:
```python
"full_recommendation": _enum_cell(r.full_recommendation),
"subset_recommendation": _enum_cell(r.subset_recommendation),
"recommendation_change": _cell(r.recommendation_change),
```

- [ ] **Step 2: Update `dashboard.py::summarize`**

Add `recommendation_change_count: int = 0` to `AtlasSummary`. Compute it in `summarize`:
```python
recommendation_change = sum(1 for r in rows if r.get("recommendation_change") == "True")
```
Pass to constructor. Update `_summary_html` to include the new metric card.

- [ ] **Step 3: Update `html_template.py`**

JS `cols` array adds `recommendation_change`. `colLabels` adds `Rec change`. Row rendering adds a cell — use `tag-flag` styling when True.

- [ ] **Step 4: Update tests**

Modify `test_rgs_csv_writer.py::test_write_csv_round_trip` — add 3 new fields to test data; assert `len(RGS_COLUMNS) == 24`.

Modify `test_rgs_dashboard.py::_seed_atlas` — add the 3 new columns to each writerow. At least one row should have `recommendation_change=True`. Update `test_summarize_basic_counts` to assert `summary.recommendation_change_count == 1` (or whatever the new count is). Update `test_render_dashboard_produces_self_contained_html` to verify the dashboard mentions "rec" / "recommendation".

- [ ] **Step 5: Run, verify all PASS**

Run: `cd C:/Projects/arac && python -m pytest -v 2>&1 | tail -3`
Expected: ~104 PASSED + 1 SKIP (97 from going-in + ~7 new).

- [ ] **Step 6: Re-run atlas + dashboard + verify column count**

```bash
cd "C:/Projects/arac"
python scripts/build_atlas.py --max-mas 3
python scripts/build_dashboard.py
head -1 outputs/atlas.csv | tr ',' '\n' | wc -l
```

Expected: 24 columns. Dashboard regenerates without error.

- [ ] **Step 7: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/rgs/csv_writer.py src/arac/rgs/dashboard.py src/arac/rgs/html_template.py tests/test_rgs_csv_writer.py tests/test_rgs_dashboard.py
git commit -m "feat(rgs): atlas CSV + dashboard show recommendation-change metric"
```

---

### Task 3: Baseline + v0.8.0 tag

**Files:**
- Modify: `C:/Projects/arac/baseline.json`

- [ ] **Step 1: Append v0.8.0 record**

```bash
cd "C:/Projects/arac" && python - <<'PY'
import json, subprocess
from datetime import datetime, timezone
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
baseline = json.loads(open("baseline.json").read())
baseline["records"]["arac-recommendation-change-v0.8.0"] = {
    "paper_id": "arac-recommendation-change-v0.8.0",
    "commit_sha": sha,
    "recorded_at": ts,
    "pooled_estimate": None, "k": None,
    "ci_lower": None, "ci_upper": None, "se": None, "tau2": None,
    "i2": None, "q": None,
    "extra": {
        "metrics_complete": ["reproduction_gap", "precision_gap_ratio", "sign_flip", "heterogeneity_gap", "recommendation_change"],
        "spec_5_of_5_metrics_shipped": True,
        "mcid_defaults_by_data_type": {
            "binary": "abs(log(0.80)) ≈ 0.2231",
            "continuous": "0.2 (Cohen's small SMD)",
            "giv": "abs(log(0.85)) ≈ 0.1625"
        },
        "recommendation_states": ["benefit", "uncertain", "harm"],
        "recommendation_change_logic": "full_state != subset_state",
        "atlas_csv_columns": 24,
        "matches_plan_3a2_design": True,
        "note": "Plan 3A.2 ships the 5th and final spec RGS metric. v0.8.0 = '5-of-5 metrics complete' milestone. MCID defaults are placeholders; Plan 4 governance will lock per-condition values via preregistered MCID CSV."
    },
}
with open("baseline.json", "w") as f:
    json.dump(baseline, f, indent=2)
print("baseline.json updated with v0.8.0 record")
PY
```

- [ ] **Step 2: Final tests + Sentinel**

```bash
cd C:/Projects/arac && python -m pytest -v 2>&1 | tail -3
cd C:/Projects/arac && python -m sentinel scan --repo .
```

Expected: ~104 tests PASS + 1 SKIP, 0 BLOCK.

- [ ] **Step 3: Commit + tag**

```bash
cd "C:/Projects/arac"
git add baseline.json
git commit -m "chore(baseline): record Plan 3A.2 recommendation-change v0.8.0 (5-of-5 metrics)"
git tag -a v0.8.0 -m "Plan 3A.2 — recommendation-change metric; ALL 5 spec RGS metrics shipped"
```

---

## Done criteria

- [ ] All 3 tasks committed
- [ ] `git tag` shows `v0.8.0`
- [ ] All tests PASS
- [ ] Sentinel 0 BLOCK
- [ ] `baseline.json` has 11 records
- [ ] Atlas CSV has 24 columns (3 new: full_recommendation, subset_recommendation, recommendation_change)
- [ ] Dashboard renders the new column + summary metric without errors
- [ ] **All 5 spec RGS metrics are now live in the engine, atlas, and dashboard**
