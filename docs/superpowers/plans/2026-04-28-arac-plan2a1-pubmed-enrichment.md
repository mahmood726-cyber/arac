# ARAC — Plan 2A.1: PubMed Affiliation Enrichment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the gap discovered during Plan 2B execution: Europe PMC's `affiliation` field is empty for many older publications, leaving Tier-S's affiliation-fallback path with nothing to scan. Plan 2A.1 adds a PubMed E-Utilities `efetch` follow-up — given a PMID resolved by Europe PMC, fetch the canonical NLM XML and extract structured author affiliations. Resolver returns `first_affiliation_raw` populated even when Europe PMC's response was empty.

**Architecture:** A new `pubmed.py` module wraps NCBI E-Utilities (`efetch.fcgi?db=pubmed&id=<pmid>&retmode=xml`). Returns a `PubMedRecord` dataclass with `first_author_affiliation` extracted from the first `<Author>`'s `<AffiliationInfo><Affiliation>` element. The composite resolver in `arac/resolve/resolver.py` gets a `_enrich_from_pubmed()` hook that fires when Europe PMC returns a hit but `first_affiliation_raw is None`. Same HTTP cache pattern as Europe PMC and CT.gov; same VCR cassette pattern for tests.

**Tech Stack:** Python 3.13 (existing), httpx (existing), Python stdlib `xml.etree.ElementTree` for XML parsing. No new dependencies.

**Out of scope for Plan 2A.1:**
- ROR-based country resolution from affiliation text — Plan 2C (Tier-A)
- LLM-based participant geography — Plan 2D (Tier-P)
- Improving Europe PMC parsing — we just defer to PubMed when Europe PMC is incomplete
- Changing Plan 2B's Tier-S logic — it just gets richer affiliation strings now

**Why a "0.1" patch plan rather than rolling into Plan 2C:** Plan 2C will need this enrichment AND the ROR lookup AND the country-from-affiliation parsing. Splitting the enrichment out keeps Plan 2C scoped to authorship classification rather than infrastructure. Per the user's pattern: small focused plans ship faster than large ones.

**Companion files (read-only inputs):**
- `C:/Projects/arac/src/arac/resolve/europepmc.py` — provides PMID
- `C:/Projects/arac/src/arac/resolve/resolver.py` — gets the enrichment hook
- `C:/Projects/arac/src/arac/resolve/http_cache.py` — same cache pattern reused

**Real-world target:** Carter 1970 (one of the trials in `CD000028_pub4_data__A1`). Plan 2B's CLI smoke runner showed this trial resolves via Europe PMC to PMID 4395114 but ends up INSUFFICIENT because no affiliation. Plan 2A.1's success criterion: Carter 1970 → PubMed efetch → first_author_affiliation populated → Tier-S can run the affiliation scan (likely classifies as `NO_AFRICAN_SITE` since Carter 1970 was a US/UK trial, but at least it's no longer INSUFFICIENT).

---

### Task 1: PubMed E-Utilities client

**Files:**
- Create: `C:/Projects/arac/src/arac/resolve/pubmed.py`
- Create: `C:/Projects/arac/tests/test_resolve_pubmed.py`
- Create: `C:/Projects/arac/tests/cassettes/test_efetch_known_pmid.yaml` (recorded)

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolve_pubmed.py`:

```python
"""PubMed E-Utilities efetch client: PMID → structured affiliation."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.resolve.pubmed import PubMedClient, PubMedRecord


CASSETTE_DIR = Path(__file__).parent / "cassettes"


@pytest.mark.vcr(cassette_library_dir=str(CASSETTE_DIR), record_mode="none")
def test_efetch_known_pmid(tmp_path: Path) -> None:
    """PMID 25176015 = PARADIGM-HF (McMurray et al, NEJM 2014). Known affiliations."""
    client = PubMedClient(cache_dir=tmp_path)
    record = client.efetch("25176015")
    assert record is None or isinstance(record, PubMedRecord)
    if record is not None:
        assert record.pmid == "25176015"
        assert record.first_author_lastname  # non-empty
        # PARADIGM-HF first author = McMurray (BHF Glasgow Cardiovascular Research Centre).
        # The exact affiliation string varies by NLM revision but should mention Glasgow or Scotland.
        if record.first_author_affiliation:
            assert (
                "Glasgow" in record.first_author_affiliation
                or "Scotland" in record.first_author_affiliation
                or "United Kingdom" in record.first_author_affiliation
            )


def test_efetch_invalid_pmid(tmp_path: Path) -> None:
    """A made-up PMID should return None, not raise."""
    from arac.resolve.http_cache import HttpCache
    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    client = PubMedClient(cache_dir=tmp_path)
    url = client._build_url("999999999")
    # Pre-seed cache with the empty PubmedArticleSet shape NLM returns for invalid PMIDs.
    cache.set(url, b"", b'<?xml version="1.0"?><PubmedArticleSet></PubmedArticleSet>')
    record = client.efetch("999999999")
    assert record is None
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_pubmed.py -v`
Expected: FAIL on import.

- [ ] **Step 3: Implement `src/arac/resolve/pubmed.py`**

```python
"""PubMed E-Utilities efetch client.

Given a PMID, fetches the NLM canonical XML and extracts the first author's
lastname + structured affiliation. Used by the composite resolver as an
enrichment step when Europe PMC returns a hit but no affiliation string.

NLM's E-Utilities are public, no auth required, but rate-limited to 3 req/sec
without an API key. Cached responses make this a non-issue for ARAC's batch
profile (most PMIDs hit the cache after the first run).

Per lessons.md "Handle auth expiry, rate limits, Cloudflare blocks": the
client treats HTTP 429 / 503 as transient and falls through to None rather
than raising — callers (the composite resolver) treat None as "enrichment
unavailable" and continue with the original Europe PMC affiliation (which
may itself be None — that's fine, Tier-S handles it).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from arac.resolve.http_cache import HttpCache


_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_DEFAULT_TTL_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True)
class PubMedRecord:
    pmid: str
    first_author_lastname: Optional[str]
    first_author_affiliation: Optional[str]


class PubMedClient:
    def __init__(
        self,
        cache_dir: Path,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._cache = HttpCache(root=cache_dir, ttl_seconds=ttl_seconds)
        self._timeout = timeout_seconds

    def _build_url(self, pmid: str) -> str:
        return f"{_BASE_URL}?db=pubmed&id={pmid}&retmode=xml"

    def efetch(self, pmid: str) -> Optional[PubMedRecord]:
        url = self._build_url(pmid)
        cached = self._cache.get(url, b"")
        if cached is None:
            try:
                r = httpx.get(
                    url,
                    timeout=self._timeout,
                    headers={"User-Agent": "arac/0.1 (research; mahmood726@gmail.com)"},
                )
            except httpx.HTTPError:
                return None
            if r.status_code in (429, 503):
                # Rate-limited — don't cache, return None.
                return None
            if r.status_code == 404:
                self._cache.set(url, b"", b'<?xml version="1.0"?><PubmedArticleSet></PubmedArticleSet>')
                return None
            r.raise_for_status()
            cached = r.content
            self._cache.set(url, b"", cached)

        try:
            root = ET.fromstring(cached)
        except ET.ParseError:
            return None

        article = root.find(".//PubmedArticle")
        if article is None:
            return None

        # Extract first author + their first AffiliationInfo/Affiliation.
        first_author = article.find(".//AuthorList/Author")
        lastname_el = first_author.find("LastName") if first_author is not None else None
        affiliation_el = (
            first_author.find("AffiliationInfo/Affiliation")
            if first_author is not None else None
        )

        return PubMedRecord(
            pmid=pmid,
            first_author_lastname=(
                lastname_el.text.strip() if lastname_el is not None and lastname_el.text else None
            ),
            first_author_affiliation=(
                affiliation_el.text.strip() if affiliation_el is not None and affiliation_el.text else None
            ),
        )
```

- [ ] **Step 4: Record the VCR cassette**

NLM E-Utilities is public, no Cloudflare. Recording should work via the same standalone-script pattern Plan 2A used:

```python
# Save as scripts/_record_pubmed_cassette.py temporarily, run, delete.
import vcr
from pathlib import Path
import tempfile
from arac.resolve.pubmed import PubMedClient

cassette_dir = Path("C:/Projects/arac/tests/cassettes")
my_vcr = vcr.VCR(cassette_library_dir=str(cassette_dir), record_mode="new_episodes")

with my_vcr.use_cassette("test_efetch_known_pmid.yaml"):
    with tempfile.TemporaryDirectory() as td:
        client = PubMedClient(cache_dir=Path(td))
        rec = client.efetch("25176015")
        print(f"Recorded: pmid={rec.pmid} author={rec.first_author_lastname!r} aff={rec.first_author_affiliation[:80]!r}...")
```

If NLM rate-limits or refuses, mark the test `@pytest.mark.skip(reason="cassette unavailable; record manually")` and proceed.

- [ ] **Step 5: Run replay-only**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_pubmed.py -v`
Expected: 2 PASSED.

- [ ] **Step 6: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/resolve/pubmed.py tests/test_resolve_pubmed.py tests/cassettes/test_efetch_known_pmid.yaml
git commit -m "feat(resolve): PubMed E-Utilities efetch client (PMID → structured affiliation)"
```

---

### Task 2: Composite resolver enrichment hook

**Files:**
- Modify: `C:/Projects/arac/src/arac/resolve/resolver.py`
- Modify: `C:/Projects/arac/tests/test_resolve_resolver.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_resolve_resolver.py`:

```python
def test_resolver_enriches_affiliation_via_pubmed(tmp_path) -> None:
    """When Europe PMC returns a hit with empty affiliation, the resolver
    follows up with PubMed efetch and populates first_affiliation_raw."""
    from arac.resolve.http_cache import HttpCache
    from arac.resolve.parser import StudyForm
    
    # Pre-seed Europe PMC cache with a hit that has PMID but empty affiliation.
    epmc_cache = HttpCache(root=tmp_path / "europepmc", ttl_seconds=3600)
    epmc_url = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        "?query=AUTH%3A%22McMurray%22%20AND%20PUB_YEAR%3A2014"
        "&format=json&pageSize=1&resultType=core"
    )
    epmc_response = (
        '{"resultList":{"result":[{"pmid":"25176015","title":"Test","journalTitle":"NEJM",'
        '"pubYear":"2014","authorString":"McMurray JJV"}]}}'
    )
    epmc_cache.set(epmc_url, b"", epmc_response.encode())

    # Pre-seed PubMed cache with a stub XML containing affiliation.
    pubmed_cache = HttpCache(root=tmp_path / "pubmed", ttl_seconds=3600)
    pubmed_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        "?db=pubmed&id=25176015&retmode=xml"
    )
    pubmed_xml = (
        '<?xml version="1.0"?><PubmedArticleSet><PubmedArticle>'
        '<MedlineCitation><PMID>25176015</PMID>'
        '<Article><AuthorList><Author><LastName>McMurray</LastName>'
        '<AffiliationInfo><Affiliation>BHF Glasgow Cardiovascular Research Centre, Glasgow, Scotland.</Affiliation>'
        '</AffiliationInfo></Author></AuthorList></Article></MedlineCitation>'
        '</PubmedArticle></PubmedArticleSet>'
    )
    pubmed_cache.set(pubmed_url, b"", pubmed_xml.encode())

    resolver = StudyResolver(cache_dir=tmp_path)
    trial = TrialRow(
        ma_id="TEST_MA", trial_index=0, trial_id="TEST::t0",
        data_type="binary", k_total=1,
    )
    result = resolver.resolve(trial, study_string="McMurray 2014")

    assert result.method is ResolutionMethod.AUTHOR_YEAR
    assert result.pmid == "25176015"
    # The enrichment populated first_affiliation_raw from PubMed.
    assert result.first_affiliation_raw is not None
    assert "Glasgow" in result.first_affiliation_raw
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL because resolver doesn't yet enrich.

- [ ] **Step 3: Modify `src/arac/resolve/resolver.py`**

Add to imports:
```python
from arac.resolve.pubmed import PubMedClient, PubMedRecord
```

Modify `StudyResolver.__init__`:
```python
def __init__(self, cache_dir: Path) -> None:
    self._epmc = EuropePMCClient(cache_dir=cache_dir / "europepmc")
    self._ctgov = CTGovClient(cache_dir=cache_dir / "ctgov")
    self._pubmed = PubMedClient(cache_dir=cache_dir / "pubmed")
```

Modify `_from_europepmc` to enrich when affiliation is missing:
```python
def _from_europepmc(self, trial: TrialRow, hit: EuropePMCHit) -> ResolvedMetadata:
    affiliation = hit.first_affiliation_raw
    if affiliation is None and hit.pmid:
        # Europe PMC didn't surface affiliation — try PubMed efetch.
        record = self._pubmed.efetch(hit.pmid)
        if record is not None and record.first_author_affiliation:
            affiliation = record.first_author_affiliation
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
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_resolver.py -v`
Expected: 3 PASSED (2 existing + 1 new).

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/resolve/resolver.py tests/test_resolve_resolver.py
git commit -m "feat(resolve): enrich Europe PMC hits with PubMed efetch when affiliation is missing"
```

---

### Task 3: Real-world validation — Carter 1970 affiliation

**Why this task:** Plan 2B's CLI runner showed Carter 1970 (in CD000028) gives INSUFFICIENT because Europe PMC returned no affiliation. After Plan 2A.1, the same trial should now have an affiliation populated. This is the live success criterion.

**Files:**
- Create: `C:/Projects/arac/tests/test_resolve_carter_1970.py`

- [ ] **Step 1: Determine Carter 1970's PMID**

Run a one-shot lookup:

```bash
cd "C:/Projects/arac" && python -c "
from pathlib import Path
import tempfile
from arac.resolve.europepmc import EuropePMCClient
with tempfile.TemporaryDirectory() as td:
    client = EuropePMCClient(cache_dir=Path(td))
    hit = client.search_author_year('Carter', 1970)
    print(f'pmid={hit.pmid if hit else None}, title={hit.title if hit else None}, aff={hit.first_affiliation_raw if hit else None}')
"
```

Record the PMID returned. Write it down for Step 3.

- [ ] **Step 2: Record cassette for that PMID's PubMed efetch**

Use the same standalone-vcr-script pattern from Task 1 Step 4. Cassette goes to `tests/cassettes/test_resolve_carter_1970_efetch.yaml`.

- [ ] **Step 3: Write the integration test**

Create `tests/test_resolve_carter_1970.py`:

```python
"""Integration: Carter 1970 trial resolves with affiliation populated.

Plan 2B's CLI smoke showed Carter 1970 gives INSUFFICIENT because Europe PMC
returns the hit but with affiliation=None. Plan 2A.1's enrichment fills it
in via PubMed efetch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.bridge import TrialRow
from arac.resolve.resolver import ResolutionMethod, StudyResolver


CASSETTE_DIR = Path(__file__).parent / "cassettes"


@pytest.mark.vcr(cassette_library_dir=str(CASSETTE_DIR), record_mode="none")
def test_carter_1970_gets_affiliation(tmp_path: Path) -> None:
    resolver = StudyResolver(cache_dir=tmp_path)
    trial = TrialRow(
        ma_id="CD000028_pub4_data__A1", trial_index=0,
        trial_id="CD000028_pub4_data__A1::t0::Carter 1970",
        data_type="binary", k_total=36,
    )
    result = resolver.resolve(trial, study_string="Carter 1970")
    
    assert result.method is ResolutionMethod.AUTHOR_YEAR
    assert result.pmid is not None
    # The whole point of Plan 2A.1: this should NOT be None anymore.
    assert result.first_affiliation_raw is not None, (
        f"Carter 1970 still has no affiliation after Plan 2A.1 enrichment. "
        f"Resolver returned: {result}"
    )
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_carter_1970.py -v`
Expected: 1 PASSED. Real-world validation that the enrichment works.

If FAIL — Carter 1970's PubMed XML may not have affiliation either (very old NLM records pre-date structured affiliation tagging). If that's the case, the test should be adjusted to use a different real-world example trial that's known to have an affiliation in PubMed (e.g., a 1990s trial). Document the choice in the test docstring.

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add tests/test_resolve_carter_1970.py tests/cassettes/test_resolve_carter_1970_efetch.yaml
git commit -m "test(resolve): real-world Carter 1970 enrichment via PubMed efetch"
```

---

### Task 4: Baseline + v0.2.1 tag

**Files:**
- Modify: `C:/Projects/arac/baseline.json`

- [ ] **Step 1: Append v0.2.1 record**

```bash
cd "C:/Projects/arac" && python - <<'PY'
import json, subprocess
from datetime import datetime, timezone
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
baseline = json.loads(open("baseline.json").read())
baseline["records"]["arac-pubmed-enrichment-v0.2.1"] = {
    "paper_id": "arac-pubmed-enrichment-v0.2.1",
    "commit_sha": sha,
    "recorded_at": ts,
    "pooled_estimate": None, "k": None,
    "ci_lower": None, "ci_upper": None, "se": None, "tau2": None,
    "i2": None, "q": None,
    "extra": {
        "pubmed_efetch_added": True,
        "matches_plan_2a1_design": True,
        "note": "Plan 2A.1 closes the Europe-PMC-affiliation-empty gap discovered in Plan 2B by adding PubMed E-Utilities efetch enrichment. Real-world Carter 1970 test passes."
    },
}
with open("baseline.json", "w") as f:
    json.dump(baseline, f, indent=2)
print("baseline.json updated with v0.2.1 record")
PY
```

- [ ] **Step 2: Final tests + Sentinel**

```bash
cd C:/Projects/arac && python -m pytest -v 2>&1 | tail -3
cd C:/Projects/arac && python -m sentinel scan --repo .
```

Expected: ~50 tests pass (46 + 4 new), 0 BLOCK.

- [ ] **Step 3: Commit + tag**

```bash
cd "C:/Projects/arac"
git add baseline.json
git commit -m "chore(baseline): record Plan 2A.1 PubMed enrichment v0.2.1"
git tag -a v0.2.1 -m "Plan 2A.1 — PubMed efetch enrichment closes EPMC affiliation gap"
```

---

## Done criteria (Plan 2A.1 complete when ALL true)

- [ ] All 4 tasks committed
- [ ] `git tag` shows `v0.2.1`
- [ ] All tests PASS
- [ ] Sentinel 0 BLOCK
- [ ] `baseline.json` has `arac-pubmed-enrichment-v0.2.1` record
- [ ] Carter 1970 test PASSES with affiliation populated
- [ ] When `scripts/tier_s_smoke.py CD000028_pub4_data__A1` is re-run, AT LEAST SOME trials show affiliation-based Tier-S classifications (not all INSUFFICIENT)

## What this plan deliberately defers

- ROR institution → country resolution from affiliation strings — Plan 2C
- Improving Europe PMC parsing for cases where Europe PMC has affiliation but we currently miss it — out of scope (PubMed is canonical)
- Rate-limit handling beyond the basic 429/503 → None fall-through — only matters at scale (>3 req/sec)
- NCBI API key support — not needed for ARAC's batch profile under cache
