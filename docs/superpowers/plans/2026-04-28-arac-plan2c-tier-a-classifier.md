# ARAC — Plan 2C of Plan 2: Tier-A (Authorship) Classifier

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify each Pairwise70 trial on Tier-A — is the **first OR senior** author affiliated with an African institution? Returns a per-trial `TierA` label (`AFRICAN_LED` / `NOT_AFRICAN_LED` / `INSUFFICIENT_DATA`) plus a confidence score, source attribution, and which author position matched.

**Architecture:** Reuses Plan 2B's pattern. The `african_countries` substring-alias table that already powers Tier-S's affiliation fallback is the same instrument used here — applied separately to first-author and last-author affiliations. Implementation steps:
1. **Extend** `PubMedRecord` to carry the full author list (currently only first-author fields). Add a `PubMedAuthor` dataclass with `lastname`, `forename`, `affiliation`. Keep `first_author_lastname` and `first_author_affiliation` populated for backwards compatibility with Plan 2A.1's resolver enrichment hook.
2. **Composite Tier-A classifier** (`tier_a.py`) takes a `ResolvedMetadata` record. If `pmid` is present, fetch the full PubMed record. Run `is_african_country` substring scan against first-author affiliation AND last-author (= senior author) affiliation. AFRICAN_LED if either matches; NOT_AFRICAN_LED if both have data and neither matches; INSUFFICIENT if data missing.
3. **Confidence levels:** 0.85 if first-author matches (most direct signal); 0.75 if only senior-author matches; 0.85 if first-author has data and isn't African (negative match); 0.75 if only senior-author has data and isn't African; 0.0 if no data.

**Tech Stack:** Python 3.13 (existing). No new dependencies. Stdlib XML parsing already used by Plan 2A.1.

**Out of scope for Plan 2C:**
- ROR-based institution canonicalisation (Plan 2C extension if substring-match accuracy is poor on Plan 4 IRR)
- ORCID author identifier resolution (Plan 4 if needed)
- Tier-P (participant geography) — Plan 2D
- IRR validation against 50-trial human gold standard — Plan 2D
- The pre-1995 NLM affiliation gap from Plan 2A.1 — same constraint applies here

**Companion files (read-only inputs):**
- `C:/Projects/arac/src/arac/resolve/pubmed.py` — to be EXTENDED with full author list
- `C:/Projects/arac/src/arac/classify/african_countries.py` — `is_african_country` reused
- `C:/Projects/arac/src/arac/resolve/resolver.py` — Plan 2A.1's enrichment still works
- `C:/Projects/arac/baseline.json` — v0.3.0 record appended at end

---

### Task 1: Extend `PubMedRecord` with full author list

**Files:**
- Modify: `C:/Projects/arac/src/arac/resolve/pubmed.py`
- Modify: `C:/Projects/arac/tests/test_resolve_pubmed.py`

**Backwards-compat constraint:** Plan 2A.1's resolver calls `record.first_author_lastname` and `record.first_author_affiliation`. These fields MUST stay populated post-extension; Plan 2A.1's tests must still pass.

- [ ] **Step 1: Append the failing test**

Append to `tests/test_resolve_pubmed.py`:

```python
def test_efetch_returns_full_author_list(tmp_path: Path) -> None:
    """PubMedRecord now carries authors: list[PubMedAuthor]. authors[0] should
    match the legacy first_author_* fields for backwards compat."""
    from arac.resolve.http_cache import HttpCache
    from arac.resolve.pubmed import PubMedAuthor

    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    client = PubMedClient(cache_dir=tmp_path)
    url = client._build_url("12345")
    pubmed_xml = (
        '<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        '<PMID>12345</PMID><Article><AuthorList>'
        '<Author><LastName>Smith</LastName><ForeName>J</ForeName>'
        '<AffiliationInfo><Affiliation>Stanford University, USA.</Affiliation></AffiliationInfo></Author>'
        '<Author><LastName>Mukasa</LastName><ForeName>R</ForeName>'
        '<AffiliationInfo><Affiliation>Makerere University, Kampala, Uganda.</Affiliation></AffiliationInfo></Author>'
        '<Author><LastName>Doe</LastName><ForeName>A</ForeName></Author>'
        '</AuthorList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(url, b"", pubmed_xml.encode())
    rec = client.efetch("12345")

    assert rec is not None
    # Backwards compat
    assert rec.first_author_lastname == "Smith"
    assert rec.first_author_affiliation is not None
    assert "Stanford" in rec.first_author_affiliation

    # New: full author list
    assert isinstance(rec.authors, tuple)
    assert len(rec.authors) == 3
    assert all(isinstance(a, PubMedAuthor) for a in rec.authors)
    assert rec.authors[0].lastname == "Smith"
    assert rec.authors[1].lastname == "Mukasa"
    assert rec.authors[1].affiliation is not None
    assert "Uganda" in rec.authors[1].affiliation
    # Author with no affiliation gets affiliation=None.
    assert rec.authors[2].lastname == "Doe"
    assert rec.authors[2].affiliation is None
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL because `PubMedAuthor` doesn't exist yet AND `rec.authors` doesn't exist yet.

- [ ] **Step 3: Modify `src/arac/resolve/pubmed.py`**

Add `PubMedAuthor` dataclass and extend `PubMedRecord` with `authors` field. Modify `efetch` to populate it.

```python
"""(existing module docstring stays.)

PubMedRecord carries:
- pmid (legacy)
- first_author_lastname / first_author_affiliation (legacy, populated from authors[0])
- authors: tuple[PubMedAuthor, ...] (new in Plan 2C — full ordered author list)

The authors tuple is the source of truth; first_author_* fields are derived at
parse time. Last author = authors[-1] when len(authors) >= 1.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

from arac.resolve.http_cache import HttpCache


_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_DEFAULT_TTL_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True)
class PubMedAuthor:
    lastname: Optional[str]
    forename: Optional[str]
    affiliation: Optional[str]


@dataclass(frozen=True)
class PubMedRecord:
    pmid: str
    first_author_lastname: Optional[str]
    first_author_affiliation: Optional[str]
    authors: tuple[PubMedAuthor, ...] = field(default_factory=tuple)


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

    def _parse_author(self, author_el: ET.Element) -> PubMedAuthor:
        lastname_el = author_el.find("LastName")
        forename_el = author_el.find("ForeName")
        affiliation_el = author_el.find("AffiliationInfo/Affiliation")
        return PubMedAuthor(
            lastname=lastname_el.text.strip() if lastname_el is not None and lastname_el.text else None,
            forename=forename_el.text.strip() if forename_el is not None and forename_el.text else None,
            affiliation=affiliation_el.text.strip() if affiliation_el is not None and affiliation_el.text else None,
        )

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

        author_els = article.findall(".//AuthorList/Author")
        authors = tuple(self._parse_author(el) for el in author_els)

        first = authors[0] if authors else None
        return PubMedRecord(
            pmid=pmid,
            first_author_lastname=first.lastname if first else None,
            first_author_affiliation=first.affiliation if first else None,
            authors=authors,
        )
```

- [ ] **Step 4: Run, verify all PubMed tests PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_pubmed.py -v`
Expected: 3 PASSED (2 existing + 1 new).

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_resolver.py -v`
Expected: 3 PASSED (resolver enrichment hook still works because `first_author_affiliation` is still populated).

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/resolve/pubmed.py tests/test_resolve_pubmed.py
git commit -m "feat(resolve): extend PubMedRecord with full author list (backwards-compat preserved)"
```

---

### Task 2: Tier-A composite classifier

**Files:**
- Create: `C:/Projects/arac/src/arac/classify/tier_a.py`
- Create: `C:/Projects/arac/tests/test_classify_tier_a.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_classify_tier_a.py`:

```python
"""Tier-A classifier: ResolvedMetadata → TierAResult."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.classify.tier_a import (
    TierA,
    TierAResult,
    TierAClassifier,
    AuthorPosition,
)
from arac.resolve.http_cache import HttpCache
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata


def _meta_with_pmid(pmid: str) -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id=f"TEST::t0::pmid={pmid}",
        method=ResolutionMethod.AUTHOR_YEAR,
        confidence=0.8,
        pmid=pmid,
        nct_id=None,
        title="test",
        first_author=None,
        first_affiliation_raw=None,
        country_list=(),
    )


def _meta_no_pmid() -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id="TEST::t0::no_pmid",
        method=ResolutionMethod.FAILED,
        confidence=0.0,
        pmid=None, nct_id=None, title=None,
        first_author=None, first_affiliation_raw=None,
        country_list=(),
    )


def _seed_pubmed(cache_dir: Path, pmid: str, xml: str) -> None:
    cache = HttpCache(root=cache_dir / "pubmed", ttl_seconds=3600)
    client = PubMedClient(cache_dir=cache_dir / "pubmed")
    cache.set(client._build_url(pmid), b"", xml.encode())


def _xml_with_authors(pmid: str, authors: list[tuple[str, str | None]]) -> str:
    """Build minimal PubmedArticleSet XML with given (lastname, affiliation) tuples."""
    author_blocks = []
    for lastname, aff in authors:
        aff_block = (
            f"<AffiliationInfo><Affiliation>{aff}</Affiliation></AffiliationInfo>"
            if aff else ""
        )
        author_blocks.append(
            f"<Author><LastName>{lastname}</LastName>{aff_block}</Author>"
        )
    return (
        f'<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        f'<PMID>{pmid}</PMID><Article><AuthorList>'
        f'{"".join(author_blocks)}'
        f'</AuthorList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )


def test_first_author_african(tmp_path: Path) -> None:
    pmid = "10001"
    xml = _xml_with_authors(pmid, [
        ("Mukasa", "Makerere University, Kampala, Uganda."),
        ("Smith", "Stanford University, USA."),
    ])
    _seed_pubmed(tmp_path, pmid, xml)
    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))
    result = classifier.classify(_meta_with_pmid(pmid))
    assert result.tier_a is TierA.AFRICAN_LED
    assert result.matched_position is AuthorPosition.FIRST
    assert result.confidence >= 0.8


def test_senior_author_african(tmp_path: Path) -> None:
    pmid = "10002"
    xml = _xml_with_authors(pmid, [
        ("Smith", "Stanford University, USA."),
        ("Doe", "Yale University, USA."),
        ("Mukasa", "Makerere University, Kampala, Uganda."),
    ])
    _seed_pubmed(tmp_path, pmid, xml)
    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))
    result = classifier.classify(_meta_with_pmid(pmid))
    assert result.tier_a is TierA.AFRICAN_LED
    assert result.matched_position is AuthorPosition.SENIOR


def test_neither_african(tmp_path: Path) -> None:
    pmid = "10003"
    xml = _xml_with_authors(pmid, [
        ("Smith", "Stanford University, USA."),
        ("Doe", "Cambridge University, United Kingdom."),
    ])
    _seed_pubmed(tmp_path, pmid, xml)
    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))
    result = classifier.classify(_meta_with_pmid(pmid))
    assert result.tier_a is TierA.NOT_AFRICAN_LED
    assert result.matched_position is AuthorPosition.NONE


def test_no_pmid_insufficient(tmp_path: Path) -> None:
    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))
    result = classifier.classify(_meta_no_pmid())
    assert result.tier_a is TierA.INSUFFICIENT_DATA
    assert result.confidence == 0.0


def test_no_affiliation_data_insufficient(tmp_path: Path) -> None:
    """PMID present but PubMed has no affiliation data on either author."""
    pmid = "10004"
    xml = _xml_with_authors(pmid, [
        ("Smith", None),
        ("Doe", None),
    ])
    _seed_pubmed(tmp_path, pmid, xml)
    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))
    result = classifier.classify(_meta_with_pmid(pmid))
    assert result.tier_a is TierA.INSUFFICIENT_DATA
    assert result.matched_position is AuthorPosition.NONE
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL on import.

- [ ] **Step 3: Implement `src/arac/classify/tier_a.py`**

```python
"""Tier-A (Authorship) classifier — is the first OR senior author African?

Source priority:
- PubMed efetch first-author affiliation → African substring scan
- PubMed efetch senior-author (= last author) affiliation → African substring scan
- AFRICAN_LED if either matches
- NOT_AFRICAN_LED if both have data and neither matches
- INSUFFICIENT_DATA if neither has affiliation data, or if no PMID

Confidence levels:
- 0.85 — first-author match (positive or negative; first author is the most direct signal)
- 0.75 — only senior-author match (slightly weaker; senior often = group head, not necessarily geographic origin)
- 0.0 — INSUFFICIENT
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arac.classify.african_countries import _load_aliases, is_african_country
from arac.resolve.pubmed import PubMedClient, PubMedRecord
from arac.resolve.resolver import ResolvedMetadata


class TierA(Enum):
    AFRICAN_LED = "african_led"
    NOT_AFRICAN_LED = "not_african_led"
    INSUFFICIENT_DATA = "insufficient_data"


class AuthorPosition(Enum):
    FIRST = "first"
    SENIOR = "senior"
    NONE = "none"


@dataclass(frozen=True)
class TierAResult:
    trial_id: str
    tier_a: TierA
    matched_position: AuthorPosition
    confidence: float
    matched_country: Optional[str]


def _scan_for_african_country(affiliation: str) -> Optional[str]:
    """Return the matched alias (lowercase) if any African country alias is a
    substring of `affiliation`, else None."""
    if not affiliation:
        return None
    aliases = _load_aliases()
    aff_lower = affiliation.lower()
    for alias in aliases:
        # Word-boundary-ish: surround by space, comma, period, or string start/end.
        # For simplicity we just substring-match; precision improvements are Plan 2D's job.
        if alias in aff_lower:
            return alias
    return None


class TierAClassifier:
    def __init__(self, pubmed_client: PubMedClient) -> None:
        self._pubmed = pubmed_client

    def classify(self, meta: ResolvedMetadata) -> TierAResult:
        if not meta.pmid:
            return TierAResult(
                trial_id=meta.trial_id,
                tier_a=TierA.INSUFFICIENT_DATA,
                matched_position=AuthorPosition.NONE,
                confidence=0.0,
                matched_country=None,
            )

        record = self._pubmed.efetch(meta.pmid)
        if record is None or not record.authors:
            return TierAResult(
                trial_id=meta.trial_id,
                tier_a=TierA.INSUFFICIENT_DATA,
                matched_position=AuthorPosition.NONE,
                confidence=0.0,
                matched_country=None,
            )

        first_aff = record.authors[0].affiliation if record.authors else None
        senior_aff = (
            record.authors[-1].affiliation
            if len(record.authors) >= 2 else None
        )

        # Both missing → insufficient
        if not first_aff and not senior_aff:
            return TierAResult(
                trial_id=meta.trial_id,
                tier_a=TierA.INSUFFICIENT_DATA,
                matched_position=AuthorPosition.NONE,
                confidence=0.0,
                matched_country=None,
            )

        first_match = _scan_for_african_country(first_aff) if first_aff else None
        senior_match = _scan_for_african_country(senior_aff) if senior_aff else None

        if first_match:
            return TierAResult(
                trial_id=meta.trial_id,
                tier_a=TierA.AFRICAN_LED,
                matched_position=AuthorPosition.FIRST,
                confidence=0.85,
                matched_country=first_match.title(),
            )
        if senior_match:
            return TierAResult(
                trial_id=meta.trial_id,
                tier_a=TierA.AFRICAN_LED,
                matched_position=AuthorPosition.SENIOR,
                confidence=0.75,
                matched_country=senior_match.title(),
            )

        # At least one had data; neither matched African.
        return TierAResult(
            trial_id=meta.trial_id,
            tier_a=TierA.NOT_AFRICAN_LED,
            matched_position=AuthorPosition.NONE,
            confidence=0.85 if first_aff else 0.75,
            matched_country=None,
        )
```

- [ ] **Step 4: Run, verify all 5 tests PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_classify_tier_a.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/classify/tier_a.py tests/test_classify_tier_a.py
git commit -m "feat(classify-tier-a): composite Tier-A classifier (first or senior author African)"
```

---

### Task 3: Smoke fixture + accuracy regression

**Files:**
- Create: `C:/Projects/arac/tests/fixtures/tier_a_smoke.json`
- Create: `C:/Projects/arac/tests/test_classify_tier_a_accuracy.py`

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/tier_a_smoke.json`:

```json
{
  "trials": [
    {
      "comment": "First author at Makerere",
      "pmid": "20001",
      "authors": [
        ["Mukasa", "Makerere University, Kampala, Uganda."],
        ["Smith", "Stanford University, USA."]
      ],
      "expected_tier_a": "african_led",
      "expected_position": "first"
    },
    {
      "comment": "Senior author at Cape Town (first is US)",
      "pmid": "20002",
      "authors": [
        ["Smith", "Harvard Medical School, Boston, MA, USA."],
        ["Doe", "MIT, Cambridge, MA, USA."],
        ["Naidoo", "University of Cape Town, South Africa."]
      ],
      "expected_tier_a": "african_led",
      "expected_position": "senior"
    },
    {
      "comment": "Both authors non-African",
      "pmid": "20003",
      "authors": [
        ["McMurray", "BHF Glasgow Cardiovascular Research Centre, Glasgow, United Kingdom."],
        ["Solomon", "Brigham and Women's Hospital, Boston, MA, USA."]
      ],
      "expected_tier_a": "not_african_led",
      "expected_position": "none"
    },
    {
      "comment": "Single author, US, not African",
      "pmid": "20004",
      "authors": [
        ["Carter", "Department of Medicine, Vanderbilt University, Nashville, TN, USA."]
      ],
      "expected_tier_a": "not_african_led",
      "expected_position": "none"
    },
    {
      "comment": "PubMed has authors but no affiliation data → INSUFFICIENT",
      "pmid": "20005",
      "authors": [
        ["Smith", null],
        ["Doe", null]
      ],
      "expected_tier_a": "insufficient_data",
      "expected_position": "none"
    }
  ]
}
```

- [ ] **Step 2: Write the accuracy test**

Create `tests/test_classify_tier_a_accuracy.py`:

```python
"""Tier-A accuracy regression on a 5-trial smoke fixture."""

from __future__ import annotations

import json
from pathlib import Path

from arac.classify.tier_a import (
    AuthorPosition, TierA, TierAClassifier,
)
from arac.resolve.http_cache import HttpCache
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tier_a_smoke.json"


def _xml_for_trial(pmid: str, authors: list) -> str:
    blocks = []
    for entry in authors:
        lastname, aff = entry
        aff_block = (
            f"<AffiliationInfo><Affiliation>{aff}</Affiliation></AffiliationInfo>"
            if aff else ""
        )
        blocks.append(f"<Author><LastName>{lastname}</LastName>{aff_block}</Author>")
    return (
        f'<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        f'<PMID>{pmid}</PMID><Article><AuthorList>{"".join(blocks)}</AuthorList>'
        f'</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )


def _seed(cache_dir: Path, pmid: str, xml: str) -> None:
    cache = HttpCache(root=cache_dir / "pubmed", ttl_seconds=3600)
    client = PubMedClient(cache_dir=cache_dir / "pubmed")
    cache.set(client._build_url(pmid), b"", xml.encode())


def _meta(pmid: str | None, idx: int) -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id=f"SMOKE::t{idx}",
        method=ResolutionMethod.AUTHOR_YEAR if pmid else ResolutionMethod.FAILED,
        confidence=0.8 if pmid else 0.0,
        pmid=pmid, nct_id=None, title="test",
        first_author=None, first_affiliation_raw=None,
        country_list=(),
    )


def test_tier_a_smoke_accuracy(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    trials = fixture["trials"]

    # Pre-seed PubMed cache for every fixture trial.
    for t in trials:
        _seed(tmp_path, t["pmid"], _xml_for_trial(t["pmid"], t["authors"]))

    classifier = TierAClassifier(pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"))

    tier_lookup = {
        "african_led": TierA.AFRICAN_LED,
        "not_african_led": TierA.NOT_AFRICAN_LED,
        "insufficient_data": TierA.INSUFFICIENT_DATA,
    }
    pos_lookup = {
        "first": AuthorPosition.FIRST,
        "senior": AuthorPosition.SENIOR,
        "none": AuthorPosition.NONE,
    }

    correct = 0
    mismatches = []
    for i, t in enumerate(trials):
        result = classifier.classify(_meta(t["pmid"], i))
        if result.tier_a is not tier_lookup[t["expected_tier_a"]]:
            mismatches.append(
                f"  [{i}] {t['comment']}: expected {t['expected_tier_a']}, got {result.tier_a.value}"
            )
            continue
        if result.matched_position is not pos_lookup[t["expected_position"]]:
            mismatches.append(
                f"  [{i}] {t['comment']}: expected position {t['expected_position']}, got {result.matched_position.value}"
            )
            continue
        correct += 1

    accuracy = correct / len(trials)
    assert accuracy >= 0.8, (
        f"Tier-A smoke accuracy {accuracy:.0%} below 80% gate "
        f"({correct}/{len(trials)} correct)\n"
        + "\n".join(mismatches)
    )
```

- [ ] **Step 3: Run, verify PASS at 5/5**

Run: `cd C:/Projects/arac && python -m pytest tests/test_classify_tier_a_accuracy.py -v`
Expected: 1 PASSED with accuracy 5/5 = 100%.

- [ ] **Step 4: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add tests/fixtures/tier_a_smoke.json tests/test_classify_tier_a_accuracy.py
git commit -m "test(classify-tier-a): 5-trial smoke fixture + ≥80% accuracy gate"
```

---

### Task 4: CLI smoke runner

**Files:**
- Create: `C:/Projects/arac/scripts/tier_a_smoke.py`

- [ ] **Step 1: Write the script**

Create `scripts/tier_a_smoke.py`:

```python
"""Resolve every trial in one Pairwise70 MA AND run Tier-A classification.

Usage:
    python scripts/tier_a_smoke.py <ma_id>

Combines Plan 2A's resolver, Plan 2A.1's PubMed enrichment, and Plan 2C's
Tier-A classifier into one end-to-end pass. Per-trial output:
study_string -> resolution -> tier_a (with matched-author position).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyreadr

from arac.bridge import load_all_mas
from arac.classify.tier_a import TierAClassifier
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import StudyResolver


def _load_study_strings_for_ma(ma_id: str, pairwise70_dir: Path) -> dict[int, str]:
    review_id = ma_id.split("__")[0]
    rda = pairwise70_dir / f"{review_id}.rda"
    if not rda.is_file():
        raise SystemExit(f"missing rda: {rda}")
    bundle = pyreadr.read_r(str(rda))
    df = next(iter(bundle.values()))
    analysis_n = int(ma_id.split("__A")[-1])
    sub = df[df["Analysis.number"] == analysis_n]
    return {i: str(sub.iloc[i]["Study"]) for i in range(len(sub))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ma_id", help="e.g. CD000028_pub4_data__A1")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from inspect_rda import _data_dir  # type: ignore
    pairwise70_dir = _data_dir()
    sys.path.pop(0)

    cache_dir = Path("outputs/cache/resolve")
    cache_dir.mkdir(parents=True, exist_ok=True)

    mas = load_all_mas(pairwise70_dir, max_reviews=None)
    ma = next((m for m in mas if m.ma_id == args.ma_id), None)
    if ma is None:
        raise SystemExit(f"ma_id not found in Pairwise70: {args.ma_id}")

    study_strings = _load_study_strings_for_ma(args.ma_id, pairwise70_dir)
    resolver = StudyResolver(cache_dir=cache_dir)
    classifier = TierAClassifier(
        pubmed_client=PubMedClient(cache_dir=cache_dir / "pubmed")
    )

    print(f"Tier-A for {len(ma.trials)} trials in {ma.ma_id}:")
    for trial in ma.trials:
        s = study_strings.get(trial.trial_index, "<MISSING>")
        meta = resolver.resolve(trial, study_string=s)
        ta = classifier.classify(meta)
        print(
            f"  [{trial.trial_index}] '{s}' -> "
            f"resolve={meta.method.value} (pmid={meta.pmid}) -> "
            f"tier_a={ta.tier_a.value} (pos={ta.matched_position.value}, conf={ta.confidence:.2f}, country={ta.matched_country})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke-run on a real MA**

Run: `cd C:/Projects/arac && python scripts/tier_a_smoke.py CD000028_pub4_data__A1`
Expected: prints one line per trial. Many will be INSUFFICIENT (pre-1995 NLM affiliation gap from Plan 2A.1 finding); some 1990s-onward trials may classify cleanly.

- [ ] **Step 3: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add scripts/tier_a_smoke.py
git commit -m "feat(classify-tier-a): CLI smoke runner — per-trial Tier-A over a Pairwise70 MA"
```

---

### Task 5: Baseline + v0.3.0 tag

**Files:**
- Modify: `C:/Projects/arac/baseline.json`

- [ ] **Step 1: Append the v0.3.0 record**

```bash
cd "C:/Projects/arac" && python - <<'PY'
import json, subprocess
from datetime import datetime, timezone
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
baseline = json.loads(open("baseline.json").read())
baseline["records"]["arac-tier-a-v0.3.0"] = {
    "paper_id": "arac-tier-a-v0.3.0",
    "commit_sha": sha,
    "recorded_at": ts,
    "pooled_estimate": None, "k": None,
    "ci_lower": None, "ci_upper": None, "se": None, "tau2": None,
    "i2": None, "q": None,
    "extra": {
        "tier_a_smoke_accuracy_pct": 100.0,
        "smoke_fixture_size": 5,
        "matches_plan_2c_design": True,
        "approach": "PubMed efetch full author list + african_countries substring scan on first AND senior author affiliations",
        "note": "Plan 2C reuses Plan 2B's african_countries alias scan applied separately to first-author and senior-author (last) affiliations. AFRICAN_LED if either matches; NOT_AFRICAN_LED if both have data and neither matches; INSUFFICIENT if data missing. Inherits Plan 2A.1's pre-1995 NLM affiliation gap. Tier-P (Plan 2D) is the next classifier."
    },
}
with open("baseline.json", "w") as f:
    json.dump(baseline, f, indent=2)
print("baseline.json updated with v0.3.0 record")
PY
```

- [ ] **Step 2: Final tests + Sentinel**

```bash
cd C:/Projects/arac && python -m pytest -v 2>&1 | tail -3
cd C:/Projects/arac && python -m sentinel scan --repo .
```

Expected: ~61 tests pass (50 + ~11 new from Plan 2C), 0 BLOCK.

- [ ] **Step 3: Commit + tag**

```bash
cd "C:/Projects/arac"
git add baseline.json
git commit -m "chore(baseline): record Plan 2C Tier-A classifier v0.3.0"
git tag -a v0.3.0 -m "Plan 2C complete — Tier-A classifier (first or senior author African); Tier-P next"
```

---

## Done criteria

- [ ] All 5 tasks committed
- [ ] `git tag` shows `v0.3.0`
- [ ] All tests PASS
- [ ] Sentinel 0 BLOCK
- [ ] `baseline.json` has `arac-tier-a-v0.3.0` record
- [ ] Tier-A smoke accuracy = 100% on 5-trial fixture
- [ ] CLI runner produces sensible output on a real Pairwise70 MA
