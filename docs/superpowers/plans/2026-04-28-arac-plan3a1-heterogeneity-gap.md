# ARAC — Plan 3A.1: Heterogeneity-Gap Metric (REML τ² + I²)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 4th of 5 spec RGS metrics — **heterogeneity gap** — to the engine, atlas CSV, and dashboard. Implements REML τ² estimation per the user's `advanced-stats.md` rule ("Never use DL for k<10 — use REML or PM"). The 5th metric (recommendation-change, needs per-condition MCID table + governance) is deferred to Plan 3A.2.

**Architecture:**
- Extend `arac.repool` with `_reml_tau2(yi, vi)` (iterative REML) and `_compute_i2(yi, vi, tau2)` helpers
- `PoolResult.tau2` becomes populated (was always None in Plan 1's fixed-effect substrate); add `PoolResult.i2` field too
- `RGSEngine.compute()` adds `heterogeneity_gap: bool` field — True if `|I²_subset - I²_full| > 0.25` (25pp delta)
- Atlas CSV grows from 16 to 19 columns: `+ full_tau2, full_i2, subset_tau2, subset_i2, heterogeneity_gap`
- Dashboard adds the heterogeneity_gap column to the table view + a summary metric

**Threshold rationale:** ΔI² > 25 percentage points is a commonly-cited threshold for "important" heterogeneity difference (low/moderate/substantial breakpoints in Cochrane Handbook). Using 25pp as the gap threshold matches that convention. Plan 4's preregistration can confirm or revise.

**Tech Stack:** Python 3.13 (existing), numpy (existing). No new dependencies.

**Out of scope for Plan 3A.1:**
- Recommendation-change metric (needs per-condition MCID table) — Plan 3A.2
- HKSJ adjustment for CIs (REML τ² alone is sufficient for the heterogeneity-gap metric; HKSJ is a CI improvement that's a Plan 3A.3 polish)
- Re-pooling the smoke set with REML to verify the 14.3% headline still reproduces — Plan 1's regression test stays on fixed-effect (REML is now an additional method, not a replacement)

---

### Task 1: REML τ² estimator + I² helper in repool

**Files:**
- Modify: `C:/Projects/arac/src/arac/repool.py` — add `_reml_tau2`, `_compute_i2`, populate `tau2` and add `i2` field to `PoolResult`
- Modify: `C:/Projects/arac/tests/test_repool_smoke.py` — append REML accuracy + I² tests

**Backwards-compat constraint:** `PoolResult` already has `tau2: Optional[float] = None` from Plan 1. Adding `i2` is additive. The existing `_pool_fe` math continues to be used for `pooled_estimate` and `se` — REML τ² is a *side computation* surfaced alongside, not a replacement.

- [ ] **Step 1: Append failing tests**

```python
def test_reml_tau2_zero_when_no_heterogeneity(pairwise70_dir: Path) -> None:
    """When all trials report the same effect with the same variance, τ² should be 0."""
    from arac.repool import _reml_tau2
    import numpy as np
    yi = np.array([0.5, 0.5, 0.5, 0.5, 0.5])
    vi = np.array([0.04, 0.04, 0.04, 0.04, 0.04])
    tau2 = _reml_tau2(yi, vi)
    assert tau2 < 1e-6  # essentially zero


def test_reml_tau2_positive_with_heterogeneity() -> None:
    """When effects vary substantially given their reported precision, τ² > 0."""
    from arac.repool import _reml_tau2
    import numpy as np
    # Wildly different effects with low reported variance → high τ²
    yi = np.array([-0.5, 0.0, 0.5, 1.0, -1.0])
    vi = np.array([0.01, 0.01, 0.01, 0.01, 0.01])
    tau2 = _reml_tau2(yi, vi)
    assert tau2 > 0.1  # substantial heterogeneity


def test_compute_i2_zero_when_tau2_zero() -> None:
    from arac.repool import _compute_i2
    import numpy as np
    yi = np.array([0.5, 0.5, 0.5])
    vi = np.array([0.04, 0.04, 0.04])
    i2 = _compute_i2(yi, vi, tau2=0.0)
    assert 0.0 <= i2 <= 0.05  # I² is essentially zero


def test_compute_i2_high_when_tau2_dominates() -> None:
    from arac.repool import _compute_i2
    yi = [-0.5, 0.0, 0.5]
    vi = [0.01, 0.01, 0.01]
    i2 = _compute_i2(yi, vi, tau2=1.0)
    assert i2 > 0.9  # almost all variation is between-study


def test_repool_subset_populates_tau2_and_i2(pairwise70_dir: Path) -> None:
    """After Plan 3A.1, repool_subset returns PoolResult with tau2 and i2 populated
    (no longer None for k>=3 visible subsets)."""
    from arac.bridge import load_all_mas
    from arac.repool import repool_subset
    mas = load_all_mas(pairwise70_dir, max_reviews=5)
    ma = next((m for m in mas if m.k >= 5), None)
    assert ma is not None
    result = repool_subset(ma, indices=tuple(range(ma.k)))
    assert result.invisible is False
    # Both fields populated for visible subsets
    assert result.tau2 is not None
    assert result.tau2 >= 0
    assert result.i2 is not None
    assert 0.0 <= result.i2 <= 1.0
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL — `_reml_tau2`, `_compute_i2`, and `PoolResult.i2` don't exist.

- [ ] **Step 3: Modify `src/arac/repool.py`**

Add the helpers and extend `PoolResult`:

```python
# Add to PoolResult dataclass (alongside existing tau2 field):
i2: Optional[float] = None


# Add new helper functions near _pool_fe:

def _reml_tau2(
    yi: np.ndarray,
    vi: np.ndarray,
    max_iter: int = 100,
    tol: float = 1e-8,
) -> float:
    """REML estimator for between-study variance τ². Iterative.

    On each iteration:
      w_i  = 1 / (v_i + τ²)
      μ̂   = Σ w_i y_i / Σ w_i
      τ²_new = max(0, [Σ w_i² (y_i − μ̂)² − Σ w_i v_i + 1/Σw_i × tr_term])
                 / Σ w_i² × ...

    Simplified Paule-Mandel-style iteration that's standard for REML in MA:
      τ²_new = max(0, Σ w_i² ((y_i − μ̂)² − v_i) / Σ w_i²)

    Per advanced-stats.md: REML is preferred over DL for k<10. We start with
    τ²=0 (DL initial value) and iterate until convergence.

    Returns: τ² (clamped to [0, +inf)).
    """
    yi = np.asarray(yi, dtype=float)
    vi = np.asarray(vi, dtype=float)
    if len(yi) < 2:
        return 0.0

    tau2 = 0.0
    for _ in range(max_iter):
        w = 1.0 / (vi + tau2)
        mu = float(np.sum(w * yi) / np.sum(w))
        residuals_sq = (yi - mu) ** 2
        # REML/PM iteration (Paule-Mandel)
        numerator = float(np.sum(w**2 * (residuals_sq - vi)))
        denominator = float(np.sum(w**2))
        if denominator == 0:
            break
        tau2_new = max(0.0, numerator / denominator)
        if abs(tau2_new - tau2) < tol:
            tau2 = tau2_new
            break
        tau2 = tau2_new
    return tau2


def _compute_i2(yi: np.ndarray, vi: np.ndarray, tau2: float) -> float:
    """Higgins & Thompson I² statistic.
    I² = max(0, (Q − df) / Q), where Q = Σ w_i (y_i − μ̂)² with w_i = 1/v_i (FE weights).
    With τ² already estimated, an alternative formulation is:
      I² = τ² / (τ² + s²)
    where s² is the typical within-study variance. Use the latter for stability.
    """
    yi = np.asarray(yi, dtype=float)
    vi = np.asarray(vi, dtype=float)
    if len(yi) < 2:
        return 0.0
    # "Typical" within-study variance (Higgins & Thompson 2002, eq. 9):
    # s² = (k-1) Σ w_i / [(Σ w_i)² − Σ w_i²], where w_i = 1/v_i
    vi_safe = np.where(vi > 0, vi, np.finfo(float).eps)
    w = 1.0 / vi_safe
    sum_w = float(np.sum(w))
    sum_w_sq = float(np.sum(w**2))
    denom = sum_w**2 - sum_w_sq
    if denom <= 0:
        return 0.0
    s_sq = (len(yi) - 1) * sum_w / denom
    if (tau2 + s_sq) <= 0:
        return 0.0
    return float(tau2 / (tau2 + s_sq))
```

Then modify `repool_subset` so the return value has `tau2` and `i2` populated when k_subset >= 2:

```python
# Inside repool_subset, after computing pooled, se via _pool_fe:
yi, vi = _yi_vi(sliced)
pooled, se = _pool_fe(yi, vi)
tau2 = _reml_tau2(yi, vi)
i2 = _compute_i2(yi, vi, tau2)

return PoolResult(
    ma_id=record.ma_id,
    k_subset=k_subset,
    invisible=invisible,
    pooled_estimate=pooled,
    se=se,
    ci_lower=pooled - 1.96 * se,
    ci_upper=pooled + 1.96 * se,
    tau2=tau2,
    i2=i2,
)
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_repool_smoke.py -v`
Expected: 5 PASSED total — 2 existing (smoke + invisibility) + 3 new (REML zero, REML high, I² zero, I² high, populated). Wait that's 5 new. Let me count: 2 existing + 5 new = 7 PASSED.

Run: `cd C:/Projects/arac && python -m pytest tests/test_repool_smoke_regression.py tests/test_full_regression.py -v`
Expected: existing regression tests still PASS — REML τ² is a side computation; `pooled_estimate` and `se` are unchanged from fixed-effect.

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/repool.py tests/test_repool_smoke.py
git commit -m "feat(repool): REML τ² + I² (Higgins & Thompson) populated in PoolResult"
```

---

### Task 2: Heterogeneity-gap metric in RGSEngine

**Files:**
- Modify: `C:/Projects/arac/src/arac/rgs/engine.py` — extend `RGSResult` with `full_tau2`, `full_i2`, `subset_tau2`, `subset_i2`, `heterogeneity_gap`
- Modify: `C:/Projects/arac/tests/test_rgs_engine.py` — extend tests for new fields + heterogeneity_gap detection

- [ ] **Step 1: Append failing tests**

```python
def test_rgs_includes_tau2_and_i2_when_visible(pairwise70_dir: Path) -> None:
    from arac.rgs.engine import RGSEngine, RGSTier
    from arac.bridge import load_all_mas
    mas = load_all_mas(pairwise70_dir, max_reviews=5)
    ma = next((m for m in mas if m.k >= 5), None)
    assert ma is not None
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.SITE, indices=tuple(range(ma.k)))

    assert result.invisible is False
    # Full pool stats populated
    assert result.full_tau2 is not None
    assert result.full_tau2 >= 0
    assert result.full_i2 is not None
    assert 0 <= result.full_i2 <= 1
    # Subset = full → subset stats also populated and equal
    assert result.subset_tau2 == result.full_tau2
    assert result.subset_i2 == result.full_i2
    # No heterogeneity gap when subset = full
    assert result.heterogeneity_gap is False


def test_rgs_heterogeneity_gap_detected_on_skewed_subset(pairwise70_dir: Path) -> None:
    """When subset half differs in heterogeneity from full, heterogeneity_gap fires."""
    from arac.rgs.engine import RGSEngine, RGSTier
    from arac.bridge import load_all_mas
    mas = load_all_mas(pairwise70_dir, max_reviews=20)
    ma = next((m for m in mas if m.k >= 8 and m.data_type == "binary"), None)
    if ma is None:
        pytest.skip("no binary MA with k>=8 in first 20 reviews")
    engine = RGSEngine()
    half = ma.k // 2
    result = engine.compute(ma, RGSTier.SITE, indices=tuple(range(half)))

    assert result.invisible is False
    assert result.full_i2 is not None
    assert result.subset_i2 is not None
    # heterogeneity_gap = |subset_i2 - full_i2| > 0.25
    expected = abs(result.subset_i2 - result.full_i2) > 0.25
    assert result.heterogeneity_gap is expected


def test_rgs_invisible_has_none_for_new_fields(pairwise70_dir: Path) -> None:
    from arac.rgs.engine import RGSEngine, RGSTier
    from arac.bridge import load_all_mas
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 3), None)
    assert ma is not None
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.PARTICIPANT, indices=())  # invisible

    assert result.invisible is True
    # Full pool stats still populated (we always compute the full pool)
    assert result.full_tau2 is not None
    assert result.full_i2 is not None
    # Subset stats and metrics are None
    assert result.subset_tau2 is None
    assert result.subset_i2 is None
    assert result.heterogeneity_gap is None
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL — `RGSResult` doesn't have those fields yet.

- [ ] **Step 3: Modify `src/arac/rgs/engine.py`**

Add fields to `RGSResult`:

```python
# Inside @dataclass(frozen=True) class RGSResult:
# (after subset_ci_upper, before reproduction_gap)
full_tau2: Optional[float]
full_i2: Optional[float]
subset_tau2: Optional[float]
subset_i2: Optional[float]
# ...
heterogeneity_gap: Optional[bool]   # |subset_i2 - full_i2| > 0.25
```

Add the threshold constant:
```python
_HETEROGENEITY_THRESHOLD = 0.25  # I² delta in absolute (proportion) terms
```

Modify `compute` to populate the new fields. The full-pool branch (always computed) already calls `repool_subset` once with full indices — extract `full.tau2` and `full.i2` into the result. The subset branch (visible only) populates subset_tau2/subset_i2 and computes heterogeneity_gap.

For the invisible branch, `subset_tau2`, `subset_i2`, and `heterogeneity_gap` are all None.

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_rgs_engine.py -v`
Expected: 7 PASSED (4 existing + 3 new).

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/rgs/engine.py tests/test_rgs_engine.py
git commit -m "feat(rgs): heterogeneity-gap metric (|ΔI²| > 25pp) + tau2/i2 fields in RGSResult"
```

---

### Task 3: Atlas CSV schema bump + dashboard update

**Files:**
- Modify: `C:/Projects/arac/src/arac/rgs/csv_writer.py` — add 5 columns to `RGS_COLUMNS`, extend `_row_to_dict`
- Modify: `C:/Projects/arac/src/arac/rgs/dashboard.py` — `summarize` adds `heterogeneity_gap_count`
- Modify: `C:/Projects/arac/src/arac/rgs/html_template.py` — table column for heterogeneity_gap, summary metric
- Modify: `C:/Projects/arac/tests/test_rgs_csv_writer.py` — update test for new columns
- Modify: `C:/Projects/arac/tests/test_rgs_dashboard.py` — add summary count + render check

- [ ] **Step 1: Update `csv_writer.py`**

Extend `RGS_COLUMNS` (insert tau2/i2 columns alongside their pool stats):

```python
RGS_COLUMNS = (
    "ma_id",
    "tier",
    "k_total",
    "k_subset",
    "invisible",
    "full_pooled_estimate",
    "full_se",
    "full_ci_lower",
    "full_ci_upper",
    "full_tau2",
    "full_i2",
    "subset_pooled_estimate",
    "subset_se",
    "subset_ci_lower",
    "subset_ci_upper",
    "subset_tau2",
    "subset_i2",
    "reproduction_gap",
    "precision_gap_ratio",
    "sign_flip",
    "heterogeneity_gap",
)
```

Extend `_row_to_dict` to include the 5 new fields.

- [ ] **Step 2: Update `dashboard.py::summarize`**

Add `heterogeneity_gap_count` to `AtlasSummary` and compute it in `summarize`:

```python
@dataclass(frozen=True)
class AtlasSummary:
    total_rows: int
    unique_mas: int
    rows_by_tier: dict[str, int] = field(default_factory=dict)
    invisible_count: int = 0
    reproduction_gap_count: int = 0
    sign_flip_count: int = 0
    heterogeneity_gap_count: int = 0
```

```python
# Inside summarize():
heterogeneity_gap = sum(1 for r in rows if r.get("heterogeneity_gap") == "True")
# Add heterogeneity_gap_count=heterogeneity_gap to the AtlasSummary constructor.
```

Update `_summary_html` to include the new metric in the rendered card.

- [ ] **Step 3: Update `html_template.py`**

In the JS `cols` array, add `heterogeneity_gap`. In the `colLabels` array, add `Het gap`. Inside the row-rendering loop, add a cell for it (similar to `sign_flip` styling — `tag-flag` when True).

- [ ] **Step 4: Update tests**

Modify `test_rgs_csv_writer.py::test_write_csv_round_trip` to include values for the 5 new fields and assert `RGS_COLUMNS` has 21 entries.

Modify `test_rgs_dashboard.py::_seed_atlas` to write the 5 new columns. Add a heterogeneity_gap=True row. Assert `summary.heterogeneity_gap_count` equals expected.

Modify `test_rgs_dashboard.py::test_render_dashboard_produces_self_contained_html` to verify the dashboard HTML contains the string "het" or "heterogeneity" (case-insensitive).

- [ ] **Step 5: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest -v 2>&1 | tail -3`
Expected: ~95 PASSED + 1 SKIP (89 from Plan 3B + ~6 from this plan). All existing tests still pass.

- [ ] **Step 6: Re-run atlas + dashboard + verify**

```bash
cd "C:/Projects/arac"
python scripts/build_atlas.py --max-mas 3
python scripts/build_dashboard.py
head -1 outputs/atlas.csv
```

Expected output: header line should now have 21 comma-separated columns (verify via `head -1 outputs/atlas.csv | tr ',' '\n' | wc -l` returns 21). The dashboard.html should be slightly larger (more columns).

- [ ] **Step 7: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/rgs/csv_writer.py src/arac/rgs/dashboard.py src/arac/rgs/html_template.py tests/test_rgs_csv_writer.py tests/test_rgs_dashboard.py
git commit -m "feat(rgs): atlas CSV + dashboard show tau2 / i2 / heterogeneity-gap"
```

---

### Task 4: Baseline + v0.7.0 tag

**Files:**
- Modify: `C:/Projects/arac/baseline.json`

- [ ] **Step 1: Append v0.7.0 record**

```bash
cd "C:/Projects/arac" && python - <<'PY'
import json, subprocess
from datetime import datetime, timezone
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
baseline = json.loads(open("baseline.json").read())
baseline["records"]["arac-heterogeneity-gap-v0.7.0"] = {
    "paper_id": "arac-heterogeneity-gap-v0.7.0",
    "commit_sha": sha,
    "recorded_at": ts,
    "pooled_estimate": None, "k": None,
    "ci_lower": None, "ci_upper": None, "se": None, "tau2": None,
    "i2": None, "q": None,
    "extra": {
        "metrics_shipped_now": ["reproduction_gap", "precision_gap_ratio", "sign_flip", "heterogeneity_gap"],
        "metrics_remaining": ["recommendation_change (needs MCID table — Plan 3A.2)"],
        "tau2_method": "REML / Paule-Mandel iteration (per advanced-stats.md: never use DL for k<10)",
        "i2_method": "Higgins & Thompson 2002 eq. 9 (typical within-study variance formulation)",
        "heterogeneity_gap_threshold_pp": 25,
        "atlas_csv_columns": 21,
        "matches_plan_3a1_design": True,
        "note": "Plan 3A.1 ships 4 of 5 spec RGS metrics. Recommendation-change deferred to 3A.2 (needs preregistered per-condition MCID table)."
    },
}
with open("baseline.json", "w") as f:
    json.dump(baseline, f, indent=2)
print("baseline.json updated with v0.7.0 record")
PY
```

- [ ] **Step 2: Final tests + Sentinel**

```bash
cd C:/Projects/arac && python -m pytest -v 2>&1 | tail -3
cd C:/Projects/arac && python -m sentinel scan --repo .
```

Expected: all tests PASS, 0 BLOCK.

- [ ] **Step 3: Commit + tag**

```bash
cd "C:/Projects/arac"
git add baseline.json
git commit -m "chore(baseline): record Plan 3A.1 heterogeneity-gap v0.7.0"
git tag -a v0.7.0 -m "Plan 3A.1 — heterogeneity-gap metric (REML τ² + I²); 4 of 5 spec metrics shipped"
```

---

## Done criteria

- [ ] All 4 tasks committed
- [ ] `git tag` shows `v0.7.0`
- [ ] All tests PASS
- [ ] Sentinel 0 BLOCK
- [ ] `baseline.json` has 10 records
- [ ] Atlas CSV has 21 columns (5 new: full_tau2, full_i2, subset_tau2, subset_i2, heterogeneity_gap)
- [ ] Dashboard renders without errors and shows the new heterogeneity_gap column
