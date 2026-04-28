# ARAC — Plan 2C.1: Word-Boundary Affiliation Matching

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the substring-match false-positive bug discovered during Plan 2C's CLI smoke run. The current `african_countries.is_african_country()` does naive substring scanning, which causes the alias `"car"` (the "CAR" abbreviation for Central African Republic) to match inside non-African words like `"Caribbean"`, `"cardiology"`, `"cardiovascular"`, `"carbon"`. HYVET 2008 was incorrectly classified as `african_led` because of this. Plan 2C.1 switches to **word-boundary regex matching** so aliases only match as standalone tokens.

**Architecture:** Replace the substring-`in` operator with `re.search(r'\b<alias>\b', text, re.IGNORECASE)` per alias. Compile a single combined regex once at module load (cached), apply to each affiliation. Also tighten the YAML: short ambiguous aliases that would word-boundary-match real institution words (e.g., `"car"` → matches "the car" in arbitrary text but NOT in "Caribbean") are still problematic — review and remove the worst offenders OR lengthen them ("CAR" alone is too short; require it to be parenthesised in source like `"(CAR)"`).

**Tech Stack:** Python 3.13 (existing), stdlib `re`. No new dependencies.

**Out of scope for Plan 2C.1:**
- ROR-based institution canonicalisation (Plan 2D extension)
- Pre-1995 NLM affiliation gap (Plan 2D — needs Cochrane JATS scrape)
- Tier-P participant geography (Plan 2D)
- IRR validation against 50-trial gold standard (Plan 2D)

**Companion files (modified by this plan):**
- `C:/Projects/arac/src/arac/classify/african_countries.py` — main change
- `C:/Projects/arac/data/african_countries.yaml` — review short aliases
- `C:/Projects/arac/tests/test_classify_african_countries.py` — add false-positive regression tests
- `C:/Projects/arac/src/arac/classify/tier_s.py` — uses the matcher; no logic change but verify
- `C:/Projects/arac/src/arac/classify/tier_a.py` — uses the matcher; verify HYVET no longer false-positives

**Real-world target:** When `python scripts/tier_a_smoke.py CD000028_pub4_data__A1` is re-run after Plan 2C.1, HYVET 2008's affiliation should NOT classify as `african_led` (the trial is a UK-led study, not Central-African-Republic-led).

---

### Task 1: Word-boundary matcher + false-positive regression tests

**Files:**
- Modify: `C:/Projects/arac/src/arac/classify/african_countries.py`
- Modify: `C:/Projects/arac/tests/test_classify_african_countries.py`
- Modify: `C:/Projects/arac/data/african_countries.yaml` (if any aliases need removal — see Step 3)

- [ ] **Step 1: Append failing false-positive tests**

Append to `tests/test_classify_african_countries.py`:

```python
def test_substring_false_positives_rejected() -> None:
    """Aliases must word-boundary-match, not substring-match.
    
    Plan 2C smoke discovered HYVET classified as african_led because alias 'car'
    (Central African Republic abbreviation) matched inside 'Caribbean' /
    'cardiology' / 'cardiovascular'. These should now reject.
    """
    # All these strings contain alias substrings but should NOT match an
    # African country at the word-boundary level.
    rejecting = [
        "Caribbean Cardiovascular Health Initiative, Bridgetown, Barbados",
        "Department of Cardiology, Cleveland Clinic, OH, USA",
        "Cardiovascular Research Centre, University of Glasgow, UK",
        "Carbon Capture and Storage Group, MIT, MA, USA",
        # 'CHAD' could appear in non-African contexts
        "Chadwick Library, University of Liverpool, UK",
        # 'NIGER' could appear inside other words
        "Negotiated agreement, Geneva, Switzerland",  # avoid false-positives on 'NIGER' substring
        # 'BENIN' inside 'beni' / 'beneath' etc.
        "Beneath the surface lab, ETH Zurich, Switzerland",
        # Single-word matches that should still REJECT
        "United States of America",
        "United Kingdom",
        "Stanford, California, USA",
    ]
    for s in rejecting:
        for token in s.split():
            assert not is_african_country(token), (
                f"Token {token!r} from {s!r} should NOT be classified African"
            )
        # Also test the full string — none of these should contain a
        # word-boundary match for any African country alias.
        # (We test the full-string scan via tier_s/tier_a in their own tests;
        # here we only assert individual tokens don't match.)


def test_real_country_names_still_match() -> None:
    """Sanity: legitimate African country names continue to match."""
    matching = [
        "Uganda", "South Africa", "Nigeria", "Kenya", "Egypt", "Morocco",
        "Tanzania", "Ghana", "Senegal", "Ethiopia",
    ]
    for c in matching:
        assert is_african_country(c), f"{c!r} should still match"


def test_country_inside_full_affiliation_string() -> None:
    """A full affiliation string containing an African country name should
    word-boundary-match. This is the production usage pattern (tier_s /
    tier_a scan a freeform affiliation string)."""
    from arac.classify.african_countries import scan_for_african_country
    
    cases_match = [
        ("Department of Medicine, Makerere University, Kampala, Uganda.", "uganda"),
        ("BHF Glasgow Cardiovascular Research Centre, Glasgow, Scotland.", None),  # no match
        ("Caribbean Cardiology Centre, Bridgetown, Barbados.", None),  # no match (false-positive guard)
        ("University of Cape Town, Cape Town, South Africa.", "south africa"),
    ]
    for affiliation, expected in cases_match:
        result = scan_for_african_country(affiliation)
        if expected is None:
            assert result is None, (
                f"Expected no match in {affiliation!r}; got {result!r}"
            )
        else:
            assert result is not None, f"Expected match {expected!r} in {affiliation!r}; got None"
            assert result.lower() == expected, (
                f"Expected match {expected!r} in {affiliation!r}; got {result!r}"
            )
```

- [ ] **Step 2: Run, verify FAIL**

Run: `cd C:/Projects/arac && python -m pytest tests/test_classify_african_countries.py -v`
Expected: FAIL on the new tests because (a) substring-matching matches "Caribbean" → False positive on "car", (b) `scan_for_african_country` doesn't exist yet.

- [ ] **Step 3: Audit and tighten the YAML**

Read `data/african_countries.yaml`. Look for any aliases that are <=4 characters (these are the most likely false-positive sources at word boundaries):
- `"CAR"` — alias for "Central African Republic" — would still match "CAR" as a standalone word. The risk is when CAR appears as a token in NON-African contexts (e.g., a sentence like "I drove the car to the lab"). At word boundaries this is safer than substring-matching but still ambiguous.
- `"DRC"` — alias for "Democratic Republic of the Congo" — similar concern but more uniquely an institutional abbreviation.

**Decision:** Keep CAR and DRC at word-boundary scope. They're rare-enough as English words that the false-positive rate at word boundaries should be acceptable. (Substring was the killer; word-boundary is OK.)

If the test suite reveals any specific alias is still over-matching, document it as a known-issue note in the YAML rather than removing — Plan 2D's IRR will quantify the per-alias false-positive rate.

- [ ] **Step 4: Implement word-boundary matching in `african_countries.py`**

Replace the substring-based `is_african_country` and add a new `scan_for_african_country` function:

```python
"""African-country canonicalisation. Loads `data/african_countries.yaml`
into a frozenset of all known aliases (case-insensitive), and a compiled
word-boundary regex for affiliation scanning.

Plan 2C.1 fix: switched from substring matching (e.g. `alias in text`) to
word-boundary regex matching (`re.search(rf'\\b{alias}\\b', text, re.I)`).
This eliminates false positives where alias 'car' (Central African Republic)
matched inside 'Caribbean' / 'cardiology' / 'cardiovascular'.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml


_YAML_PATH = Path(__file__).resolve().parents[3] / "data" / "african_countries.yaml"


@lru_cache(maxsize=1)
def _load_aliases() -> frozenset[str]:
    if not _YAML_PATH.is_file():
        raise RuntimeError(f"african_countries YAML missing: {_YAML_PATH}")
    raw = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))
    out: set[str] = set()
    for canonical, aliases in raw.items():
        out.add(canonical.lower().strip())
        for a in aliases:
            out.add(str(a).lower().strip())
    return frozenset(out)


@lru_cache(maxsize=1)
def _load_canonical_names() -> frozenset[str]:
    if not _YAML_PATH.is_file():
        raise RuntimeError(f"african_countries YAML missing: {_YAML_PATH}")
    raw = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))
    return frozenset(raw.keys())


@lru_cache(maxsize=1)
def _build_combined_regex() -> re.Pattern[str]:
    """Compile a single regex matching any African-country alias at word
    boundaries. Aliases are sorted longest-first so 'South Africa' wins over
    a hypothetical 'south'-suffix alias."""
    aliases = sorted(_load_aliases(), key=len, reverse=True)
    # re.escape each alias to handle apostrophes ('Cote d'Ivoire'), hyphens,
    # and spaces. Use \b boundaries on either side.
    escaped = [re.escape(a) for a in aliases]
    pattern = r"\b(?:" + "|".join(escaped) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


# Public: canonical names only (for table-size assertions).
AFRICAN_COUNTRIES = _load_canonical_names()


def is_african_country(name: str) -> bool:
    """True if `name` is an African country (case-insensitive, word-boundary).

    Used for single-token checks. For full affiliation-string scanning, prefer
    `scan_for_african_country` which returns the matched alias.
    """
    if not name:
        return False
    return bool(_build_combined_regex().fullmatch(name.strip()))


def scan_for_african_country(text: str) -> Optional[str]:
    """Scan a freeform affiliation string for the first word-boundary match
    against any African-country alias. Returns the matched alias (lowercase,
    as it appears in the alias table), or None.

    This is the production matcher for tier_s and tier_a.
    """
    if not text:
        return None
    m = _build_combined_regex().search(text)
    if m is None:
        return None
    return m.group(0).lower()
```

- [ ] **Step 5: Run all tests, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_classify_african_countries.py -v`
Expected: all PASS — the 5 existing tests + 3 new ones.

If `test_substring_false_positives_rejected` fails on a specific token: investigate which alias word-boundary-matched it. May need to remove that alias from the YAML. Document the removal.

- [ ] **Step 6: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/classify/african_countries.py tests/test_classify_african_countries.py
[ -n "$(git status --short data/african_countries.yaml)" ] && git add data/african_countries.yaml
git commit -m "fix(classify): word-boundary alias matching (eliminates 'car' substring false-positive)"
```

---

### Task 2: Migrate Tier-S and Tier-A to use `scan_for_african_country`

**Files:**
- Modify: `C:/Projects/arac/src/arac/classify/tier_s.py`
- Modify: `C:/Projects/arac/src/arac/classify/tier_a.py`

The current implementations of these classifiers do their own substring scanning over `_load_aliases()`. After Plan 2C.1, they should use the new `scan_for_african_country` helper to get the same word-boundary semantics.

- [ ] **Step 1: Refactor `tier_s.py`**

Find the affiliation-scan code in `TierSClassifier.classify`. Replace:

```python
aliases = _load_aliases()
aff_lower = meta.first_affiliation_raw.lower()
matched = next(
    (a for a in aliases if a in aff_lower),
    None,
)
```

With:

```python
from arac.classify.african_countries import scan_for_african_country
# (move the import to the module top)
matched = scan_for_african_country(meta.first_affiliation_raw)
```

Adjust the surrounding logic so `matched` is the alias-or-None directly. If `matched is not None`, that's an African match.

- [ ] **Step 2: Refactor `tier_a.py`**

The internal `_scan_for_african_country` helper in `tier_a.py` already exists but uses substring matching. Either:
- Replace its body with a call to `african_countries.scan_for_african_country`, OR
- Delete the helper entirely and have `TierAClassifier.classify` import the public function

The public function is the better choice — keeps one source of truth.

- [ ] **Step 3: Run all classifier tests, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_classify_tier_s.py tests/test_classify_tier_a.py tests/test_classify_tier_s_accuracy.py tests/test_classify_tier_a_accuracy.py -v`
Expected: all PASS. Tier-S and Tier-A tests use full country names ("Uganda", "South Africa") in their fixtures, so word-boundary matching doesn't change their behaviour.

- [ ] **Step 4: Run full suite**

Run: `cd C:/Projects/arac && python -m pytest -v 2>&1 | tail -3`
Expected: 60 PASSED (57 + 3 new from Task 1).

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/classify/tier_s.py src/arac/classify/tier_a.py
git commit -m "refactor(classify): tier_s and tier_a both use scan_for_african_country (word-boundary)"
```

---

### Task 3: Real-world re-validation — HYVET no longer african_led

**Files:**
- Create: `C:/Projects/arac/tests/test_hyvet_no_false_positive.py`

- [ ] **Step 1: Determine HYVET's PubMed affiliation that triggered the false positive**

Run a one-shot lookup:

```bash
cd "C:/Projects/arac" && python -c "
from pathlib import Path
import tempfile
from arac.resolve.pubmed import PubMedClient
with tempfile.TemporaryDirectory() as td:
    client = PubMedClient(cache_dir=Path(td))
    rec = client.efetch('18378519')  # HYVET 2008
    if rec:
        print(f'PMID={rec.pmid}')
        for i, a in enumerate(rec.authors[:3]):
            print(f'  [{i}] {a.lastname}: {a.affiliation[:120] if a.affiliation else None}...')
"
```

Record the affiliation that triggered "car" matching (likely the first author's, e.g., something containing "Cardiovascular" or similar).

- [ ] **Step 2: Write the regression test**

Create `tests/test_hyvet_no_false_positive.py`:

```python
"""Regression: HYVET 2008 (a UK-led trial) is NOT classified african_led.

Plan 2C's smoke run misclassified HYVET because alias 'car' (Central African
Republic abbreviation) substring-matched inside 'Cardiovascular' in HYVET's
first-author affiliation. Plan 2C.1's word-boundary fix should reject this.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.bridge import TrialRow
from arac.classify.tier_a import AuthorPosition, TierA, TierAClassifier
from arac.resolve.http_cache import HttpCache
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata


# A synthetic HYVET-shape affiliation. The exact NLM-recorded affiliation
# for HYVET first author varies by NLM revision, but it CONTAINS the word
# "Cardiovascular" (or similar -CAR-* word) that triggered the bug.
_HYVET_AFFILIATION = (
    "Cardiovascular Research Unit, Imperial College, London, United Kingdom"
)


def _seed_pubmed_with_hyvet(cache_dir: Path, pmid: str = "18378519") -> None:
    cache = HttpCache(root=cache_dir / "pubmed", ttl_seconds=3600)
    client = PubMedClient(cache_dir=cache_dir / "pubmed")
    xml = (
        f'<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        f'<PMID>{pmid}</PMID><Article><AuthorList>'
        f'<Author><LastName>Beckett</LastName>'
        f'<AffiliationInfo><Affiliation>{_HYVET_AFFILIATION}</Affiliation></AffiliationInfo></Author>'
        f'</AuthorList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(client._build_url(pmid), b"", xml.encode())


def test_hyvet_classified_not_african_led(tmp_path: Path) -> None:
    _seed_pubmed_with_hyvet(tmp_path)
    classifier = TierAClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed")
    )
    meta = ResolvedMetadata(
        trial_id="HYVET_TEST::t0",
        method=ResolutionMethod.ACRONYM,
        confidence=0.95,
        pmid="18378519",
        nct_id=None,
        title="HYVET",
        first_author=None,
        first_affiliation_raw=None,
        country_list=(),
    )
    result = classifier.classify(meta)
    
    # The whole point of Plan 2C.1: HYVET should NOT be african_led.
    # Pre-fix: was classified AFRICAN_LED with matched_country="Car"
    # Post-fix: should be NOT_AFRICAN_LED (UK-led trial)
    assert result.tier_a is TierA.NOT_AFRICAN_LED, (
        f"HYVET regression: expected NOT_AFRICAN_LED, got {result.tier_a.value} "
        f"(matched_country={result.matched_country!r}). Word-boundary fix "
        f"may not have eliminated the 'car' false-positive."
    )
    assert result.matched_country is None
```

- [ ] **Step 3: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_hyvet_no_false_positive.py -v`
Expected: 1 PASSED.

If FAIL — the word-boundary regex still matches some alias inside the affiliation. Inspect: `python -c "from arac.classify.african_countries import scan_for_african_country; print(scan_for_african_country('Cardiovascular Research Unit, Imperial College, London, United Kingdom'))"`. The alias responsible for any match needs to be reviewed (likely candidates: "CAR", a country whose name contains "London"-prefix, etc.).

- [ ] **Step 4: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add tests/test_hyvet_no_false_positive.py
git commit -m "test(classify): HYVET regression — word-boundary fix eliminates 'car' false-positive"
```

---

### Task 4: Baseline.json + v0.3.1 tag

**Files:**
- Modify: `C:/Projects/arac/baseline.json`

- [ ] **Step 1: Append v0.3.1 record**

```bash
cd "C:/Projects/arac" && python - <<'PY'
import json, subprocess
from datetime import datetime, timezone
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
baseline = json.loads(open("baseline.json").read())
baseline["records"]["arac-word-boundary-v0.3.1"] = {
    "paper_id": "arac-word-boundary-v0.3.1",
    "commit_sha": sha,
    "recorded_at": ts,
    "pooled_estimate": None, "k": None,
    "ci_lower": None, "ci_upper": None, "se": None, "tau2": None,
    "i2": None, "q": None,
    "extra": {
        "fix_type": "word_boundary_regex",
        "false_positives_eliminated": ["car_in_caribbean", "car_in_cardiology", "car_in_cardiovascular"],
        "regression_test_added": "test_hyvet_no_false_positive",
        "matches_plan_2c1_design": True,
        "note": "Plan 2C.1 fixes the substring-match false-positive discovered during Plan 2C's CLI smoke. african_countries module now compiles a single word-boundary regex from all aliases and exposes scan_for_african_country() as the public matcher. tier_s and tier_a both use this. Plan 2D's IRR validation will quantify any remaining alias-level false-positive rate."
    },
}
with open("baseline.json", "w") as f:
    json.dump(baseline, f, indent=2)
print("baseline.json updated with v0.3.1 record")
PY
```

- [ ] **Step 2: Final tests + Sentinel**

```bash
cd C:/Projects/arac && python -m pytest -v 2>&1 | tail -3
cd C:/Projects/arac && python -m sentinel scan --repo .
```

Expected: 61 PASSED (57 + 4 new across Plan 2C.1), 0 BLOCK.

- [ ] **Step 3: Commit + tag**

```bash
cd "C:/Projects/arac"
git add baseline.json
git commit -m "chore(baseline): record Plan 2C.1 word-boundary fix v0.3.1"
git tag -a v0.3.1 -m "Plan 2C.1 — word-boundary alias matching eliminates substring false-positives"
```

---

## Done criteria

- [ ] All 4 tasks committed
- [ ] `git tag` shows `v0.3.1`
- [ ] All tests PASS (target ~61)
- [ ] Sentinel 0 BLOCK
- [ ] HYVET regression test PASSES — word-boundary matching eliminates the false-positive
- [ ] Tier-A CLI re-run on CD000028 shows HYVET as NOT_AFRICAN_LED (or INSUFFICIENT, due to pre-1995 NLM gap), NOT african_led
