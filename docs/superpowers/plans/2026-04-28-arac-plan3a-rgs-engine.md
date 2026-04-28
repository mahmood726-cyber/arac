# ARAC — Plan 3A: RGS Engine + Atlas Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute the **Representation Gap Score (RGS)** per MA per Tier and emit an atlas CSV. The atlas is ARAC's central deliverable — a per-MA × per-tier table showing how the African-subset pool differs from the full pool. Plan 3A ships **3 of 5** RGS metrics from spec §6 (Reproduction gap, Precision gap, Sign-flip indicator). Heterogeneity gap (needs REML τ² infrastructure) and Recommendation-change (needs per-condition MCID table) are deferred to Plan 3A.1.

**Architecture:**
- `RGSResult` per (MA, Tier) row carries: ma_id, tier (S/A/P), invisibility flag, full-pool effect/CI, subset-pool effect/CI, 3 RGS metric values
- `RGSEngine.compute(record, tier_indices)` calls Plan 1's `repool_subset` on the tier subset, compares to the full pool, returns `RGSResult`
- Atlas pipeline (CLI): for each MA → resolve all trials → run Tier-S/A/P classifiers → compute RGS → emit one CSV row per (MA, Tier)
- `--tier-mode` flag: `SA_ONLY` (default, no LLM cost) | `SAP` (full triad, requires API key) | `S_ONLY` (fastest, AACT only)
- `--max-mas` flag for incremental runs
- `--max-cost-usd` ceiling for Tier-P (defensive — halts before exceeding budget)

**Tech Stack:** Python 3.13 (existing). Reuses Plan 1's `repool_subset`, Plan 2A's resolver, Plan 2B/2C/2D's classifiers. No new dependencies.

**Out of scope for Plan 3A:**
- Heterogeneity gap metric — Plan 3A.1 (needs REML τ² estimation)
- Recommendation-change metric — Plan 3A.1 (needs per-condition MCID table)
- Atlas dashboard (single-file HTML) — Plan 3B
- Verification UI — Plan 3C
- Full Pairwise70 production atlas extraction — user-driven batch session

**Companion files (read-only inputs):**
- All Plan 1–2D modules (resolver, repool, classifiers)
- `baseline.json` — append v0.5.0 record at end

**Critical guardrail:** The default `--tier-mode SA_ONLY` ensures running this pipeline does NOT trigger LLM API calls. Switching to `SAP` requires `ARAC_ANTHROPIC_API_KEY` set; if you forget, the pipeline halts at first Tier-P call with the actionable error from Plan 2D's pre-flight gate. This protects against accidental $30 cost.

---

### Task 1: RGSResult schema + RGSEngine core

**Files:**
- Create: `C:/Projects/arac/src/arac/rgs/__init__.py`
- Create: `C:/Projects/arac/src/arac/rgs/engine.py`
- Create: `C:/Projects/arac/tests/test_rgs_engine.py`

- [ ] **Step 1: Write the failing test**

```python
"""RGS engine: per-(MA, Tier) computation."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.bridge import load_all_mas
from arac.rgs.engine import RGSEngine, RGSResult, RGSTier


def test_rgs_result_full_subset_zero_gaps(pairwise70_dir: Path) -> None:
    """When tier subset = full set, all gap metrics should be zero."""
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 3), None)
    assert ma is not None

    engine = RGSEngine()
    full_indices = tuple(range(ma.k))
    result = engine.compute(ma, RGSTier.SITE, full_indices)

    assert isinstance(result, RGSResult)
    assert result.ma_id == ma.ma_id
    assert result.tier is RGSTier.SITE
    assert result.invisible is False
    assert result.k_subset == ma.k
    # Full subset = full pool: zero gaps.
    assert result.reproduction_gap is False  # |delta| < 0.005
    assert abs(result.precision_gap_ratio - 1.0) < 1e-10
    assert result.sign_flip is False


def test_rgs_invisible_when_subset_too_small(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 3), None)
    assert ma is not None
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.AUTHORSHIP, indices=(0, 1))
    assert result.invisible is True
    assert result.k_subset == 2
    # Metric values should be None for invisible (insufficient data).
    assert result.reproduction_gap is None
    assert result.precision_gap_ratio is None
    assert result.sign_flip is None


def test_rgs_empty_subset_invisible(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = mas[0]
    engine = RGSEngine()
    result = engine.compute(ma, RGSTier.PARTICIPANT, indices=())
    assert result.invisible is True
    assert result.k_subset == 0
    assert result.reproduction_gap is None
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL on import.

- [ ] **Step 3: Implement `src/arac/rgs/__init__.py`**

```python
"""Representation Gap Score (RGS) engine for ARAC.

Computes per-MA × per-Tier RGS results: how the African-subset pool differs
from the full pool, along 3 orthogonal dimensions (Plan 3A; Plan 3A.1 will
add 2 more for the full 5-metric suite from spec §6).
"""
```

- [ ] **Step 4: Implement `src/arac/rgs/engine.py`**

```python
"""RGS computation core.

For each (MA, Tier) pair, compute three orthogonal gap metrics:
1. Reproduction gap (binary): does the African-subset pool differ from the
   full pool by |delta| > 0.005? (Reuses Plan 1's published threshold.)
2. Precision gap (ratio): subset CI width / full CI width. Values >> 1
   indicate the subset is much less precise than the full pool.
3. Sign-flip (binary): does the subset pool's sign differ from the full pool?
   (Specifically: subset.pooled_estimate has different sign from full.)

INSUFFICIENT_DATA case: k_subset < 3 (Plan 1's invisibility threshold). All
metric fields return None to signal insufficient.

Plan 3A.1 will add Heterogeneity gap (τ² delta — needs REML) and
Recommendation-change (crosses MCID — needs per-condition MCID table).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arac.bridge import MARecord
from arac.repool import INVISIBILITY_THRESHOLD_K, PoolResult, repool_subset


_REPRODUCTION_THRESHOLD = 0.005  # |delta| > this → flagged non-reproducible (Plan 1)


class RGSTier(Enum):
    SITE = "site"
    AUTHORSHIP = "authorship"
    PARTICIPANT = "participant"


@dataclass(frozen=True)
class RGSResult:
    """One row of the atlas: per-MA × per-Tier RGS computation."""
    ma_id: str
    tier: RGSTier
    k_total: int
    k_subset: int
    invisible: bool

    # Full-pool stats (always computed when MA has k>=2).
    full_pooled_estimate: Optional[float]
    full_se: Optional[float]
    full_ci_lower: Optional[float]
    full_ci_upper: Optional[float]

    # Subset-pool stats (None if invisible).
    subset_pooled_estimate: Optional[float]
    subset_se: Optional[float]
    subset_ci_lower: Optional[float]
    subset_ci_upper: Optional[float]

    # RGS metrics (None if invisible).
    reproduction_gap: Optional[bool]       # True if |subset - full| > 0.005
    precision_gap_ratio: Optional[float]   # subset_ci_width / full_ci_width
    sign_flip: Optional[bool]              # True if subset sign differs from full


def _ci_width(pool: PoolResult) -> Optional[float]:
    if pool.ci_lower is None or pool.ci_upper is None:
        return None
    return pool.ci_upper - pool.ci_lower


def _same_sign(a: float, b: float) -> bool:
    """Return True if a and b have the same sign (both >= 0 or both < 0)."""
    return (a >= 0) == (b >= 0)


class RGSEngine:
    def compute(
        self,
        record: MARecord,
        tier: RGSTier,
        indices: tuple[int, ...],
    ) -> RGSResult:
        """Compute RGS for one (MA, Tier) pair given the trial-index subset."""
        full = repool_subset(record, tuple(range(record.k)))
        invisible = len(indices) < INVISIBILITY_THRESHOLD_K

        if invisible:
            return RGSResult(
                ma_id=record.ma_id,
                tier=tier,
                k_total=record.k,
                k_subset=len(indices),
                invisible=True,
                full_pooled_estimate=full.pooled_estimate,
                full_se=full.se,
                full_ci_lower=full.ci_lower,
                full_ci_upper=full.ci_upper,
                subset_pooled_estimate=None,
                subset_se=None,
                subset_ci_lower=None,
                subset_ci_upper=None,
                reproduction_gap=None,
                precision_gap_ratio=None,
                sign_flip=None,
            )

        subset = repool_subset(record, indices)

        # Reproduction gap
        if (
            subset.pooled_estimate is None
            or full.pooled_estimate is None
        ):
            reproduction_gap: Optional[bool] = None
        else:
            reproduction_gap = (
                abs(subset.pooled_estimate - full.pooled_estimate)
                > _REPRODUCTION_THRESHOLD
            )

        # Precision gap ratio
        full_w = _ci_width(full)
        subset_w = _ci_width(subset)
        if full_w is None or subset_w is None or full_w == 0:
            precision_gap_ratio: Optional[float] = None
        else:
            precision_gap_ratio = subset_w / full_w

        # Sign flip
        if (
            subset.pooled_estimate is None
            or full.pooled_estimate is None
        ):
            sign_flip: Optional[bool] = None
        else:
            sign_flip = not _same_sign(
                subset.pooled_estimate, full.pooled_estimate
            )

        return RGSResult(
            ma_id=record.ma_id,
            tier=tier,
            k_total=record.k,
            k_subset=len(indices),
            invisible=False,
            full_pooled_estimate=full.pooled_estimate,
            full_se=full.se,
            full_ci_lower=full.ci_lower,
            full_ci_upper=full.ci_upper,
            subset_pooled_estimate=subset.pooled_estimate,
            subset_se=subset.se,
            subset_ci_lower=subset.ci_lower,
            subset_ci_upper=subset.ci_upper,
            reproduction_gap=reproduction_gap,
            precision_gap_ratio=precision_gap_ratio,
            sign_flip=sign_flip,
        )
```

- [ ] **Step 5: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_rgs_engine.py -v`
Expected: 3 PASSED.

- [ ] **Step 6: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/rgs tests/test_rgs_engine.py
git commit -m "feat(rgs): RGSEngine with reproduction-gap / precision-gap / sign-flip metrics"
```

---

### Task 2: Synthetic-tier-subset RGS regression

**Files:**
- Modify: `C:/Projects/arac/tests/test_rgs_engine.py`

This test exercises the engine with a synthetic tier subset that's KNOWN to differ from the full pool — proving the metrics actually detect the difference.

- [ ] **Step 1: Append the test**

```python
def test_rgs_detects_gap_on_skewed_subset(pairwise70_dir: Path) -> None:
    """Pick an MA with k>=6, take only the first half as the 'tier subset'.
    The subset pool will likely differ from the full pool — verify metrics fire.
    """
    mas = load_all_mas(pairwise70_dir, max_reviews=10)
    ma = next((m for m in mas if m.k >= 6 and m.data_type == "binary"), None)
    if ma is None:
        pytest.skip("no binary MA with k>=6 found in first 10 reviews")

    engine = RGSEngine()
    half = ma.k // 2
    result = engine.compute(
        ma, RGSTier.SITE, indices=tuple(range(half)),
    )
    assert result.invisible is False
    assert result.k_subset == half

    # All metric fields populated (not None).
    assert result.reproduction_gap is not None
    assert result.precision_gap_ratio is not None
    assert result.sign_flip is not None

    # Precision gap should be > 1 (smaller subset → wider CI).
    assert result.precision_gap_ratio > 1.0
```

- [ ] **Step 2: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_rgs_engine.py::test_rgs_detects_gap_on_skewed_subset -v`
Expected: 1 PASSED (or SKIP if no qualifying MA in first 10 reviews — unlikely).

- [ ] **Step 3: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add tests/test_rgs_engine.py
git commit -m "test(rgs): verify metrics detect gap on a skewed half-trial subset"
```

---

### Task 3: Atlas pipeline + tier-classifier composition

**Files:**
- Create: `C:/Projects/arac/src/arac/rgs/pipeline.py`
- Create: `C:/Projects/arac/tests/test_rgs_pipeline.py`

The pipeline composes resolver + classifiers + RGSEngine. For testability, it takes the classifiers as constructor args (so tests can inject mocks).

- [ ] **Step 1: Write the failing test**

```python
"""RGS pipeline: end-to-end MA → resolved trials → tier subsets → RGS rows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from arac.bridge import MARecord, TrialRow, load_all_mas
from arac.classify.tier_a import AuthorPosition, TierA, TierAResult
from arac.classify.tier_p import TierP, TierPResult
from arac.classify.tier_s import TierS, TierSResult, TierSSource
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata
from arac.rgs.engine import RGSTier
from arac.rgs.pipeline import RGSPipeline, TierMode


# Mock classifiers — return canned results per trial_id, so the pipeline test
# doesn't need real Pairwise70 metadata or LLM access.

@dataclass
class _MockResolver:
    def resolve(self, trial: TrialRow, study_string: str) -> ResolvedMetadata:
        return ResolvedMetadata(
            trial_id=trial.trial_id,
            method=ResolutionMethod.AUTHOR_YEAR,
            confidence=0.8,
            pmid="1", nct_id=None, title="t",
            first_author=None, first_affiliation_raw=None, country_list=(),
        )


@dataclass
class _MockTierS:
    african_indices: set[int]  # which trial_indices count as Tier-S African
    def classify(self, meta: ResolvedMetadata) -> TierSResult:
        idx = int(meta.trial_id.rsplit("::t", 1)[-1])
        if idx in self.african_indices:
            return TierSResult(meta.trial_id, TierS.AFRICAN_SITE, TierSSource.AACT, 0.97, "Uganda")
        return TierSResult(meta.trial_id, TierS.NO_AFRICAN_SITE, TierSSource.AACT, 0.97, None)


@dataclass
class _MockTierA:
    african_indices: set[int]
    def classify(self, meta: ResolvedMetadata) -> TierAResult:
        idx = int(meta.trial_id.rsplit("::t", 1)[-1])
        if idx in self.african_indices:
            return TierAResult(meta.trial_id, TierA.AFRICAN_LED, AuthorPosition.FIRST, 0.85, "Uganda")
        return TierAResult(meta.trial_id, TierA.NOT_AFRICAN_LED, AuthorPosition.NONE, 0.85, None)


@dataclass
class _MockTierP:
    african_indices: set[int]
    def classify(self, meta: ResolvedMetadata) -> TierPResult:
        idx = int(meta.trial_id.rsplit("::t", 1)[-1])
        if idx in self.african_indices:
            return TierPResult(meta.trial_id, TierP.AFRICAN_MAJORITY, 0.95, 100.0, ("Uganda",), "evidence")
        return TierPResult(meta.trial_id, TierP.NOT_AFRICAN_MAJORITY, 0.95, 10.0, ("USA",), "evidence")


def _study_string_for(trial: TrialRow) -> str:
    return f"author {1990 + trial.trial_index}"


def test_pipeline_emits_rows_per_tier(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 4), None)
    if ma is None:
        pytest.skip("need an MA with k>=4")

    # First 3 trials are "African" by all three tiers; rest are not.
    african = {0, 1, 2}
    pipeline = RGSPipeline(
        resolver=_MockResolver(),
        tier_s=_MockTierS(african),
        tier_a=_MockTierA(african),
        tier_p=_MockTierP(african),
        study_string_lookup=_study_string_for,
    )

    rows = list(pipeline.run([ma], tier_mode=TierMode.SAP))
    # 3 rows per MA (one per tier).
    assert len(rows) == 3
    tiers_emitted = {r.tier for r in rows}
    assert tiers_emitted == {RGSTier.SITE, RGSTier.AUTHORSHIP, RGSTier.PARTICIPANT}

    # All 3 should have k_subset = 3 (the 3 African trials).
    for r in rows:
        assert r.k_subset == 3
        assert r.invisible is False  # k=3 is the threshold


def test_pipeline_sa_only_skips_tier_p(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 4), None)
    if ma is None:
        pytest.skip()

    pipeline = RGSPipeline(
        resolver=_MockResolver(),
        tier_s=_MockTierS({0, 1, 2}),
        tier_a=_MockTierA({0, 1, 2}),
        tier_p=None,  # MUST be None when SA_ONLY
        study_string_lookup=_study_string_for,
    )
    rows = list(pipeline.run([ma], tier_mode=TierMode.SA_ONLY))
    # 2 rows per MA (S and A, no P).
    assert len(rows) == 2
    tiers = {r.tier for r in rows}
    assert tiers == {RGSTier.SITE, RGSTier.AUTHORSHIP}


def test_pipeline_s_only(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=1)
    ma = next((m for m in mas if m.k >= 4), None)
    if ma is None:
        pytest.skip()

    pipeline = RGSPipeline(
        resolver=_MockResolver(),
        tier_s=_MockTierS({0, 1, 2}),
        tier_a=None,
        tier_p=None,
        study_string_lookup=_study_string_for,
    )
    rows = list(pipeline.run([ma], tier_mode=TierMode.S_ONLY))
    assert len(rows) == 1
    assert rows[0].tier is RGSTier.SITE
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL on import.

- [ ] **Step 3: Implement `src/arac/rgs/pipeline.py`**

```python
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
    engine: RGSEngine = RGSEngine()

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
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_rgs_pipeline.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/rgs/pipeline.py tests/test_rgs_pipeline.py
git commit -m "feat(rgs): atlas pipeline composing resolver + tier classifiers + RGS engine"
```

---

### Task 4: CSV emitter + CLI runner

**Files:**
- Create: `C:/Projects/arac/src/arac/rgs/csv_writer.py`
- Create: `C:/Projects/arac/scripts/build_atlas.py`
- Create: `C:/Projects/arac/tests/test_rgs_csv_writer.py`

- [ ] **Step 1: Write the failing test**

```python
"""CSV writer: serialize RGSResult rows to CSV with stable column order."""

from __future__ import annotations

import csv
from pathlib import Path

from arac.rgs.csv_writer import RGS_COLUMNS, write_rgs_rows
from arac.rgs.engine import RGSResult, RGSTier


def test_write_csv_round_trip(tmp_path: Path) -> None:
    rows = [
        RGSResult(
            ma_id="CD000028__A1", tier=RGSTier.SITE,
            k_total=10, k_subset=3, invisible=False,
            full_pooled_estimate=-0.12, full_se=0.05,
            full_ci_lower=-0.22, full_ci_upper=-0.02,
            subset_pooled_estimate=-0.15, subset_se=0.10,
            subset_ci_lower=-0.35, subset_ci_upper=0.05,
            reproduction_gap=True, precision_gap_ratio=2.0, sign_flip=False,
        ),
        RGSResult(
            ma_id="CD000028__A1", tier=RGSTier.AUTHORSHIP,
            k_total=10, k_subset=1, invisible=True,
            full_pooled_estimate=-0.12, full_se=0.05,
            full_ci_lower=-0.22, full_ci_upper=-0.02,
            subset_pooled_estimate=None, subset_se=None,
            subset_ci_lower=None, subset_ci_upper=None,
            reproduction_gap=None, precision_gap_ratio=None, sign_flip=None,
        ),
    ]
    out = tmp_path / "atlas.csv"
    write_rgs_rows(rows, out)

    with out.open() as f:
        reader = csv.DictReader(f)
        loaded = list(reader)

    assert len(loaded) == 2
    assert reader.fieldnames == list(RGS_COLUMNS)
    # First row
    assert loaded[0]["ma_id"] == "CD000028__A1"
    assert loaded[0]["tier"] == "site"
    assert loaded[0]["invisible"] == "False"
    assert loaded[0]["reproduction_gap"] == "True"
    # Second row (invisible) should have empty cells for None metric fields.
    assert loaded[1]["invisible"] == "True"
    assert loaded[1]["reproduction_gap"] == ""
    assert loaded[1]["subset_pooled_estimate"] == ""
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL on import.

- [ ] **Step 3: Implement `src/arac/rgs/csv_writer.py`**

```python
"""CSV writer for RGSResult rows. Column order is stable (alphabetical-ish
within stat groups) so atlas consumers can rely on it."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Optional

from arac.rgs.engine import RGSResult


# Column order: identifiers → counts → invisibility → full pool → subset pool → metrics
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
    "subset_pooled_estimate",
    "subset_se",
    "subset_ci_lower",
    "subset_ci_upper",
    "reproduction_gap",
    "precision_gap_ratio",
    "sign_flip",
)


def _cell(value: Optional[object]) -> str:
    """None → empty string; bool → 'True'/'False'; floats → repr (full precision)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)  # full precision for atlas consumers
    return str(value)


def _row_to_dict(r: RGSResult) -> dict[str, str]:
    return {
        "ma_id": r.ma_id,
        "tier": r.tier.value,
        "k_total": _cell(r.k_total),
        "k_subset": _cell(r.k_subset),
        "invisible": _cell(r.invisible),
        "full_pooled_estimate": _cell(r.full_pooled_estimate),
        "full_se": _cell(r.full_se),
        "full_ci_lower": _cell(r.full_ci_lower),
        "full_ci_upper": _cell(r.full_ci_upper),
        "subset_pooled_estimate": _cell(r.subset_pooled_estimate),
        "subset_se": _cell(r.subset_se),
        "subset_ci_lower": _cell(r.subset_ci_lower),
        "subset_ci_upper": _cell(r.subset_ci_upper),
        "reproduction_gap": _cell(r.reproduction_gap),
        "precision_gap_ratio": _cell(r.precision_gap_ratio),
        "sign_flip": _cell(r.sign_flip),
    }


def write_rgs_rows(rows: Iterable[RGSResult], out: Path) -> int:
    """Write rows to a CSV with stable column order. Returns number of rows."""
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(RGS_COLUMNS))
        writer.writeheader()
        for r in rows:
            writer.writerow(_row_to_dict(r))
            n += 1
    return n
```

- [ ] **Step 4: Implement `scripts/build_atlas.py`**

```python
"""Build the ARAC atlas: per-MA × per-Tier RGS rows over Pairwise70.

Usage:
    python scripts/build_atlas.py [--max-mas N] [--tier-mode s_only|sa_only|sap] [--out outputs/atlas.csv]

By default runs SA_ONLY tier mode (no LLM cost) on the first 5 MAs — safe to
re-run without API key, useful for validating the pipeline.

For full atlas (~6,386 MAs):
    --tier-mode sap requires ARAC_ANTHROPIC_API_KEY; cost ~$30 amortized
    --tier-mode sa_only is free (AACT + PubMed only)

Output: CSV at outputs/atlas.csv (one row per (MA, Tier)).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyreadr

from arac.bridge import TrialRow, load_all_mas
from arac.classify.aact import AACTClient
from arac.classify._aact_path import resolve_aact_location
from arac.classify.tier_a import TierAClassifier
from arac.classify.tier_p import TierPClassifier
from arac.classify.tier_p_extractor import TierPExtractor
from arac.classify.tier_s import TierSClassifier
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import StudyResolver
from arac.rgs.csv_writer import write_rgs_rows
from arac.rgs.pipeline import RGSPipeline, TierMode


def _study_string_lookup_for_dir(pairwise70_dir: Path):
    """Build a lookup function: TrialRow → Pairwise70 Study string."""
    cache: dict[str, dict[int, str]] = {}

    def lookup(trial: TrialRow) -> str:
        # Cache study-strings per ma_id so each rda is only read once.
        if trial.ma_id not in cache:
            review_id = trial.ma_id.split("__")[0]
            rda = pairwise70_dir / f"{review_id}.rda"
            if not rda.is_file():
                cache[trial.ma_id] = {}
                return f"<missing-rda:{review_id}>"
            bundle = pyreadr.read_r(str(rda))
            df = next(iter(bundle.values()))
            try:
                analysis_n = int(trial.ma_id.split("__A")[-1])
            except ValueError:
                cache[trial.ma_id] = {}
                return f"<bad-ma-id:{trial.ma_id}>"
            sub = df[df["Analysis.number"] == analysis_n]
            cache[trial.ma_id] = {
                i: str(sub.iloc[i]["Study"]) for i in range(len(sub))
            }
        return cache[trial.ma_id].get(trial.trial_index, "<missing>")

    return lookup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-mas", type=int, default=5)
    ap.add_argument(
        "--tier-mode",
        choices=["s_only", "sa_only", "sap"],
        default="sa_only",
    )
    ap.add_argument("--out", default="outputs/atlas.csv")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from inspect_rda import _data_dir  # type: ignore
    pairwise70_dir = _data_dir()
    sys.path.pop(0)

    cache_dir = Path("outputs/cache/atlas")
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Resolver — Plan 2A
    resolver = StudyResolver(cache_dir=cache_dir)

    # Tier-S — Plan 2B (AACT)
    try:
        aact_loc = resolve_aact_location()
        tier_s = TierSClassifier(aact_client=AACTClient(aact_loc))
    except RuntimeError as e:
        print(f"AACT not configured: {e}", file=sys.stderr)
        print("Tier-S will fall back to affiliation-only (no AACT).", file=sys.stderr)
        tier_s = TierSClassifier(aact_client=None)

    pubmed = PubMedClient(cache_dir=cache_dir / "pubmed")

    tier_mode = TierMode(args.tier_mode)

    tier_a = None
    tier_p = None
    if tier_mode in (TierMode.SA_ONLY, TierMode.SAP):
        tier_a = TierAClassifier(pubmed_client=pubmed)
    if tier_mode is TierMode.SAP:
        from arac.classify._anthropic_pre import resolve_anthropic_config
        try:
            ant_config = resolve_anthropic_config()
        except RuntimeError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1
        tier_p_extractor = TierPExtractor(cache_dir=cache_dir, config=ant_config)
        tier_p = TierPClassifier(pubmed_client=pubmed, extractor=tier_p_extractor)

    pipeline = RGSPipeline(
        resolver=resolver,
        tier_s=tier_s,
        tier_a=tier_a,
        tier_p=tier_p,
        study_string_lookup=_study_string_lookup_for_dir(pairwise70_dir),
    )

    mas = load_all_mas(pairwise70_dir, max_reviews=None)[: args.max_mas]
    print(f"Building atlas: {len(mas)} MAs, tier_mode={tier_mode.value}")

    out_path = Path(args.out)
    n = write_rgs_rows(pipeline.run(mas, tier_mode=tier_mode), out_path)
    print(f"Wrote {n} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run csv_writer test**

Run: `cd C:/Projects/arac && python -m pytest tests/test_rgs_csv_writer.py -v`
Expected: 1 PASSED.

- [ ] **Step 6: Smoke-run the atlas builder (SA_ONLY default)**

Run: `cd C:/Projects/arac && python scripts/build_atlas.py --max-mas 3`
Expected: prints `Building atlas: 3 MAs, tier_mode=sa_only` then `Wrote N rows to outputs/atlas.csv` (N is 3 MAs × 2 tiers each = 6 rows, modulo any MAs that fail resolution).

The `outputs/atlas.csv` is .gitignored (already in `outputs/cache/`-style ignore — verify with `grep outputs .gitignore`). If not, add `outputs/atlas.csv` and `outputs/*.csv` to `.gitignore` BEFORE the next step.

- [ ] **Step 7: Sentinel scan**

Run: `cd C:/Projects/arac && python -m sentinel scan --repo .`
Expected: 0 BLOCK.

- [ ] **Step 8: Commit**

```bash
cd "C:/Projects/arac"
git add src/arac/rgs/csv_writer.py scripts/build_atlas.py tests/test_rgs_csv_writer.py
[ -n "$(git status --short .gitignore)" ] && git add .gitignore
git commit -m "feat(rgs): CSV emitter + build_atlas.py CLI (--max-mas/--tier-mode/--out flags)"
```

---

### Task 5: Baseline + v0.5.0 tag

**Files:**
- Modify: `C:/Projects/arac/baseline.json`

- [ ] **Step 1: Append v0.5.0 record**

```bash
cd "C:/Projects/arac" && python - <<'PY'
import json, subprocess
from datetime import datetime, timezone
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
baseline = json.loads(open("baseline.json").read())
baseline["records"]["arac-rgs-engine-v0.5.0"] = {
    "paper_id": "arac-rgs-engine-v0.5.0",
    "commit_sha": sha,
    "recorded_at": ts,
    "pooled_estimate": None, "k": None,
    "ci_lower": None, "ci_upper": None, "se": None, "tau2": None,
    "i2": None, "q": None,
    "extra": {
        "metrics_shipped": ["reproduction_gap", "precision_gap_ratio", "sign_flip"],
        "metrics_deferred": ["heterogeneity_gap (needs REML)", "recommendation_change (needs MCID table)"],
        "tier_modes": ["s_only", "sa_only", "sap"],
        "default_tier_mode": "sa_only",
        "atlas_csv_columns": 16,
        "matches_plan_3a_design": True,
        "production_atlas_extraction_status": "deferred — runs via `python scripts/build_atlas.py --max-mas 6386 --tier-mode sap` when user authorizes ~$30 LLM cost",
        "note": "Plan 3A ships the RGS engine + atlas pipeline + CSV emitter. 3 of 5 spec metrics shipped; 2 deferred to Plan 3A.1. Atlas dashboard (HTML) is Plan 3B; verification UI is Plan 3C."
    },
}
with open("baseline.json", "w") as f:
    json.dump(baseline, f, indent=2)
print("baseline.json updated with v0.5.0 record")
PY
```

- [ ] **Step 2: Final tests + Sentinel**

```bash
cd C:/Projects/arac && python -m pytest -v 2>&1 | tail -3
cd C:/Projects/arac && python -m sentinel scan --repo .
```

Expected: ~85 tests PASS + 1 SKIP (Plan 2D's live API skip), 0 BLOCK.

- [ ] **Step 3: Commit + tag**

```bash
cd "C:/Projects/arac"
git add baseline.json
git commit -m "chore(baseline): record Plan 3A RGS engine v0.5.0"
git tag -a v0.5.0 -m "Plan 3A — RGS engine + atlas pipeline (3 of 5 metrics; SA_ONLY default for safe smoke runs)"
```

---

## Done criteria

- [ ] All 5 tasks committed
- [ ] `git tag` shows `v0.5.0`
- [ ] All tests PASS
- [ ] Sentinel 0 BLOCK
- [ ] `baseline.json` has 8 records (foundation, resolve, tier-s, pubmed-enrichment, tier-a, word-boundary, tier-p, rgs-engine)
- [ ] `python scripts/build_atlas.py --max-mas 3` runs end-to-end and produces a 6-row CSV at `outputs/atlas.csv`
- [ ] User can authorize the full production run via `--max-mas N --tier-mode sap` when ready (separate batch session)

## What this plan deliberately defers

- **Heterogeneity gap metric** — needs REML τ² estimation (Plan 1 explicitly shipped fixed-effect). Plan 3A.1.
- **Recommendation-change metric** — needs per-condition MCID table that's preregistered. Plan 3A.1 builds the MCID infrastructure; Plan 4 locks the values.
- **Atlas dashboard (HTML)** — Plan 3B
- **Verification UI (RapidMeta-style)** — Plan 3C
- **Full Pairwise70 atlas extraction (~6,386 MAs)** — user-driven batch run when budget approved
