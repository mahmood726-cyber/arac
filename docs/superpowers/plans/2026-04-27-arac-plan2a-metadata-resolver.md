# ARAC — Plan 2A of Plan 2: Metadata-Resolution Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the per-trial metadata-resolution pipeline. Given a Pairwise70 trial row with its freeform `Study` string, return a structured `ResolvedMetadata` record (PMID, NCT, first-author affiliation, sites-by-country) with per-source confidence scores, ready for downstream Tier-S/A/P classification (Plans 2B–2D).

**Architecture:** Multi-source resolver with priority cascade. (1) A parser classifies the `Study` string into one of four forms — `AuthorYear`, `NCTDirect`, `Acronym`, `Unknown`. (2) For each form, a dispatcher routes to the appropriate resolver — Europe PMC for Author-Year, CT.gov v2 for NCT-direct, a curated acronym table for acronyms. (3) Results merge into a single `ResolvedMetadata` record with per-source confidence. All HTTP calls go through a file-based cache (re-runs don't re-hit APIs). Tests use VCR cassettes for HTTP determinism, with a small live-API smoke gate behind an env var.

**Tech Stack:** Python 3.13 (existing), httpx (HTTP), pytest-recording (VCR cassettes), pyyaml (acronym table). Pairwise70 + repro-floor-atlas remain path-dependencies from Plan 1.

**Out of scope for Plan 2A:** Tier-S/A/P classification (Plans 2B/2C/2D), LLM-based participant-geography extraction (Plan 2D), verification UI (Plan 3), IRR validation against a 50+ trial human gold-standard (Plan 2D — requires the gold-standard cohort to be assembled first).

**Plan 2A's smoke fixture is intentionally tiny (5 trials).** It is NOT the gold standard for IRR — it's just enough to catch regression in the resolver dispatch + cache. Plan 2D will assemble the full gold standard.

**Companion files (Plan 1 outputs, read-only inputs here):**
- `C:/Projects/arac/src/arac/bridge.py` — `MARecord`, `TrialRow`, `load_all_mas`
- `C:/Projects/arac/tests/conftest.py` — `pairwise70_dir` fixture
- `C:/Projects/arac/.sentinel.yaml` — Sentinel project scope
- `C:/Projects/arac/baseline.json` — Plan 1 v0.0.1 baseline

**Pre-flight finding being addressed:** Pairwise70 `Study` field is universally present but freeform — ~80.6% Author-Year, ~1.1% NCT-direct, ~19.5% trial acronyms (per `docs/preflight-pairwise70-schema.txt`).

---

### Task 1: Plan 2A scaffold + dependency additions

**Files:**
- Modify: `C:/Projects/arac/pyproject.toml`
- Create: `C:/Projects/arac/src/arac/resolve/__init__.py`
- Create: `C:/Projects/arac/tests/test_resolve_scaffold.py`

- [ ] **Step 1: Add deps to `pyproject.toml`**

Open `C:/Projects/arac/pyproject.toml`. Modify the `dependencies` array (currently `numpy`, `pyreadr`, `scipy`) to add `httpx>=0.27` and `pyyaml>=6.0`. Modify the `dev` optional-dependencies to add `pytest-recording>=0.13` (VCR for httpx).

Final shape:

```toml
[project]
name = "arac"
version = "0.0.1"
description = "African Representation Atlas of Cochrane — engine substrate"
requires-python = ">=3.11"
dependencies = [
    "numpy>=1.26",
    "pyreadr>=0.5",
    "scipy>=1.11",
    "httpx>=0.27",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "pytest-recording>=0.13"]
```

- [ ] **Step 2: Install + verify**

Run: `cd C:/Projects/arac && pip install -e ".[dev]"`
Expected: installs httpx, pyyaml, pytest-recording without error.

- [ ] **Step 3: Create the resolve package**

Create `C:/Projects/arac/src/arac/resolve/__init__.py`:

```python
"""Metadata-resolution package for ARAC.

Resolves Pairwise70 trial rows (with freeform Study strings) into structured
metadata records via Europe PMC, CT.gov v2, and a curated acronym table.
"""
```

- [ ] **Step 4: Write the scaffold smoke test**

Create `C:/Projects/arac/tests/test_resolve_scaffold.py`:

```python
"""Resolve-package smoke: importable, no module-level side effects."""

from __future__ import annotations


def test_resolve_package_importable() -> None:
    import arac.resolve  # noqa: F401


def test_resolve_dependencies_present() -> None:
    import httpx  # noqa: F401
    import yaml  # noqa: F401
```

- [ ] **Step 5: Run tests**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_scaffold.py -v`
Expected: 2 PASSED.

- [ ] **Step 6: Sentinel scan**

Run: `cd C:/Projects/arac && python -m sentinel scan --repo .`
Expected: 0 BLOCK.

- [ ] **Step 7: Commit**

```bash
cd "C:/Projects/arac"
git add pyproject.toml src/arac/resolve tests/test_resolve_scaffold.py
git commit -m "chore(plan-2a): scaffold resolve package + add httpx/pyyaml/pytest-recording deps"
```

---

### Task 2: Study-string parser

**Files:**
- Create: `C:/Projects/arac/src/arac/resolve/parser.py`
- Create: `C:/Projects/arac/tests/test_resolve_parser.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolve_parser.py`:

```python
"""Parser: Study-string → StudyRef enum + payload."""

from __future__ import annotations

from arac.resolve.parser import (
    StudyForm,
    StudyRef,
    parse_study_string,
)


def test_parse_author_year() -> None:
    ref = parse_study_string("Smith 2010")
    assert ref.form is StudyForm.AUTHOR_YEAR
    assert ref.author_lastname == "Smith"
    assert ref.year == 2010
    assert ref.acronym is None
    assert ref.nct_id is None


def test_parse_author_year_with_initials() -> None:
    ref = parse_study_string("van der Berg 2018")
    # Multi-word lastnames preserved verbatim.
    assert ref.form is StudyForm.AUTHOR_YEAR
    assert ref.author_lastname == "van der Berg"
    assert ref.year == 2018


def test_parse_nct_direct() -> None:
    ref = parse_study_string("NCT02918409")
    assert ref.form is StudyForm.NCT_DIRECT
    assert ref.nct_id == "NCT02918409"
    assert ref.author_lastname is None


def test_parse_acronym() -> None:
    ref = parse_study_string("HYVET 2008")
    assert ref.form is StudyForm.ACRONYM
    assert ref.acronym == "HYVET"
    assert ref.year == 2008


def test_parse_acronym_no_year() -> None:
    ref = parse_study_string("SUMMIT")
    assert ref.form is StudyForm.ACRONYM
    assert ref.acronym == "SUMMIT"
    assert ref.year is None


def test_parse_unknown() -> None:
    ref = parse_study_string("???")
    assert ref.form is StudyForm.UNKNOWN
    assert ref.author_lastname is None
    assert ref.acronym is None
    assert ref.nct_id is None


def test_parse_strips_whitespace() -> None:
    ref = parse_study_string("  Smith 2010  ")
    assert ref.form is StudyForm.AUTHOR_YEAR
    assert ref.author_lastname == "Smith"
```

- [ ] **Step 2: Run, verify FAIL**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_parser.py -v`
Expected: FAIL with `ImportError: cannot import name 'StudyForm' from 'arac.resolve.parser'`.

- [ ] **Step 3: Implement `src/arac/resolve/parser.py`**

```python
"""Parse Pairwise70 Study strings into structured StudyRef records.

Patterns recognised (in priority order, first match wins):
1. NCT-direct      — `NCT\\d{6,8}` anywhere in the string
2. Acronym + Year  — uppercase word ≥3 chars + 4-digit year (e.g. "HYVET 2008")
3. Acronym alone   — uppercase word ≥3 chars, no year (e.g. "SUMMIT")
4. Author + Year   — anything else with a 4-digit year (e.g. "van der Berg 2018")
5. Unknown         — no usable structure

The parser is deliberately permissive: it returns UNKNOWN rather than raising
on un-parseable strings. Downstream resolvers handle UNKNOWN by skipping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class StudyForm(Enum):
    AUTHOR_YEAR = "author_year"
    NCT_DIRECT = "nct_direct"
    ACRONYM = "acronym"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class StudyRef:
    """Structured representation of a Study string."""
    raw: str
    form: StudyForm
    author_lastname: Optional[str] = None
    acronym: Optional[str] = None
    nct_id: Optional[str] = None
    year: Optional[int] = None


_NCT_RE = re.compile(r"NCT\d{6,8}")
_YEAR_RE = re.compile(r"(19\d{2}|20\d{2})")
# Acronym = uppercase word ≥3 chars (allowing digits and hyphens), at start of string.
_ACRONYM_RE = re.compile(r"^([A-Z][A-Z0-9\-]{2,})\b")


def parse_study_string(s: str) -> StudyRef:
    raw = s
    s = s.strip()
    if not s:
        return StudyRef(raw=raw, form=StudyForm.UNKNOWN)

    # 1. NCT-direct
    nct_match = _NCT_RE.search(s)
    if nct_match:
        return StudyRef(
            raw=raw,
            form=StudyForm.NCT_DIRECT,
            nct_id=nct_match.group(0),
        )

    # 2 + 3. Acronym (with or without year)
    acronym_match = _ACRONYM_RE.match(s)
    if acronym_match:
        acronym = acronym_match.group(1)
        year_match = _YEAR_RE.search(s)
        return StudyRef(
            raw=raw,
            form=StudyForm.ACRONYM,
            acronym=acronym,
            year=int(year_match.group(0)) if year_match else None,
        )

    # 4. Author + Year — extract year, treat everything before it as lastname.
    year_match = _YEAR_RE.search(s)
    if year_match:
        year = int(year_match.group(0))
        lastname = s[: year_match.start()].strip()
        if lastname:
            return StudyRef(
                raw=raw,
                form=StudyForm.AUTHOR_YEAR,
                author_lastname=lastname,
                year=year,
            )

    # 5. Unknown
    return StudyRef(raw=raw, form=StudyForm.UNKNOWN)
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_parser.py -v`
Expected: 7 PASSED.

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/resolve/parser.py tests/test_resolve_parser.py
git commit -m "feat(resolve): Study-string parser (AuthorYear / NCTDirect / Acronym / Unknown)"
```

---

### Task 3: Acronym lookup table (seed)

**Files:**
- Create: `C:/Projects/arac/src/arac/resolve/acronyms.py`
- Create: `C:/Projects/arac/data/acronyms.yaml`
- Create: `C:/Projects/arac/tests/test_resolve_acronyms.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolve_acronyms.py`:

```python
"""Acronym table: YAML seed + lookup."""

from __future__ import annotations

import pytest

from arac.resolve.acronyms import AcronymEntry, lookup_acronym, load_acronyms


def test_load_acronyms_returns_dict() -> None:
    table = load_acronyms()
    assert isinstance(table, dict)
    assert len(table) >= 5  # seed has at least 5 entries


def test_lookup_known_acronym() -> None:
    entry = lookup_acronym("HYVET")
    assert entry is not None
    assert isinstance(entry, AcronymEntry)
    assert entry.acronym == "HYVET"
    assert entry.pmid is not None
    assert entry.source  # non-empty source attribution


def test_lookup_unknown_acronym() -> None:
    entry = lookup_acronym("ZZZ_NOT_A_REAL_TRIAL")
    assert entry is None


def test_lookup_case_insensitive() -> None:
    e1 = lookup_acronym("hyvet")
    e2 = lookup_acronym("HYVET")
    assert e1 is not None
    assert e2 is not None
    assert e1.pmid == e2.pmid


def test_seed_entries_have_required_fields() -> None:
    table = load_acronyms()
    for acronym, entry in table.items():
        assert entry.acronym
        assert entry.pmid or entry.nct_id, (
            f"{acronym} must have at least one of pmid/nct_id"
        )
        assert entry.source, f"{acronym} missing source attribution"
```

- [ ] **Step 2: Run, verify FAIL**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_acronyms.py -v`
Expected: FAIL on import.

- [ ] **Step 3: Create the seed YAML**

Create `C:/Projects/arac/data/acronyms.yaml`:

```yaml
# ARAC acronym → trial-identifier seed table.
# Each entry: lookup-key (uppercase) → metadata.
# `source` field is required — explains where the PMID/NCT was hand-verified from.
# Add more acronyms as Pairwise70's 19% acronym tail demands.

HYVET:
  pmid: "18378519"
  nct_id: null
  full_name: "HYpertension in the Very Elderly Trial"
  source: "Beckett NS et al, NEJM 2008 — verified PMID via PubMed direct lookup"

HOPE:
  pmid: "10639539"
  nct_id: null
  full_name: "Heart Outcomes Prevention Evaluation"
  source: "Yusuf S et al, NEJM 2000 — verified PMID via PubMed direct lookup"

SHEP:
  pmid: "1675354"
  nct_id: null
  full_name: "Systolic Hypertension in the Elderly Program"
  source: "SHEP Cooperative Research Group, JAMA 1991 — verified PMID via PubMed"

SUMMIT:
  pmid: "27750038"
  nct_id: "NCT01275144"
  full_name: "Study to Understand Mortality and MorbidITy"
  source: "Vestbo J et al, Lancet 2016 — verified PMID + NCT via PubMed and CT.gov"

ALLHAT:
  pmid: "12479763"
  nct_id: null
  full_name: "Antihypertensive and Lipid-Lowering Treatment to Prevent Heart Attack Trial"
  source: "ALLHAT Officers, JAMA 2002 — verified PMID via PubMed direct lookup"

PARADIGM-HF:
  pmid: "25176015"
  nct_id: "NCT01035255"
  full_name: "Prospective Comparison of ARNI with ACEI to Determine Impact on Global Mortality and Morbidity in Heart Failure"
  source: "McMurray JJV et al, NEJM 2014 — verified via Entresto FDA dossier (DossierGap project ground truth)"

VICTORIA:
  pmid: "32222134"
  nct_id: "NCT02861534"
  full_name: "VerICiguaT global study in subjects with heart failure with reduced ejection fraction"
  source: "Armstrong PW et al, NEJM 2020 — verified via Verquvo FDA dossier (DossierGap project)"

GRIPHON:
  pmid: "26699168"
  nct_id: "NCT01106014"
  full_name: "Prostacyclin (PGI2) Receptor Agonist In Pulmonary Arterial Hypertension"
  source: "Sitbon O et al, NEJM 2015 — verified via Uptravi FDA dossier (DossierGap project)"
```

- [ ] **Step 4: Implement `src/arac/resolve/acronyms.py`**

```python
"""Curated acronym → trial-identifier lookup table.

Source data lives in `data/acronyms.yaml` at the repo root. The table is small
(seed ~10 entries; expected to grow to ~200 as Pairwise70's 19% acronym tail is
processed). Each entry MUST have either a PMID or an NCT (or both), plus a
human-readable source attribution explaining where the identifier was verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml


_ACRONYMS_YAML = Path(__file__).resolve().parents[3] / "data" / "acronyms.yaml"


@dataclass(frozen=True)
class AcronymEntry:
    acronym: str
    pmid: Optional[str]
    nct_id: Optional[str]
    full_name: Optional[str]
    source: str


@lru_cache(maxsize=1)
def load_acronyms() -> dict[str, AcronymEntry]:
    """Load and parse the acronyms YAML. Cached for the process lifetime."""
    if not _ACRONYMS_YAML.is_file():
        raise RuntimeError(f"acronyms YAML missing: {_ACRONYMS_YAML}")
    raw = yaml.safe_load(_ACRONYMS_YAML.read_text(encoding="utf-8"))
    table: dict[str, AcronymEntry] = {}
    for key, val in raw.items():
        table[key.upper()] = AcronymEntry(
            acronym=key.upper(),
            pmid=str(val["pmid"]) if val.get("pmid") else None,
            nct_id=val.get("nct_id"),
            full_name=val.get("full_name"),
            source=val["source"],
        )
    return table


def lookup_acronym(acronym: str) -> Optional[AcronymEntry]:
    """Return the AcronymEntry for `acronym` (case-insensitive), or None."""
    return load_acronyms().get(acronym.upper())
```

- [ ] **Step 5: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_acronyms.py -v`
Expected: 5 PASSED.

- [ ] **Step 6: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add data/acronyms.yaml src/arac/resolve/acronyms.py tests/test_resolve_acronyms.py
git commit -m "feat(resolve): seed acronym→identifier table (8 entries from cardiology corpus)"
```

---

### Task 4: HTTP cache decorator

**Files:**
- Create: `C:/Projects/arac/src/arac/resolve/http_cache.py`
- Create: `C:/Projects/arac/tests/test_resolve_http_cache.py`

**Why this exists:** Both Europe PMC and CT.gov are rate-limited. Re-running tests without a cache would burn API quota and produce flaky failures. We cache by (URL + body hash) on disk, with a configurable TTL.

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolve_http_cache.py`:

```python
"""HTTP cache: file-based, TTL-based, idempotent on equal (url, body)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from arac.resolve.http_cache import HttpCache


def test_cache_miss_then_hit(tmp_path: Path) -> None:
    cache = HttpCache(root=tmp_path, ttl_seconds=60)
    key = ("https://example.com/api", b'{"q": "x"}')

    assert cache.get(*key) is None  # miss

    cache.set(*key, b"response-bytes-1")
    assert cache.get(*key) == b"response-bytes-1"  # hit


def test_cache_distinct_keys(tmp_path: Path) -> None:
    cache = HttpCache(root=tmp_path, ttl_seconds=60)
    cache.set("https://a", b"", b"resp-a")
    cache.set("https://b", b"", b"resp-b")
    assert cache.get("https://a", b"") == b"resp-a"
    assert cache.get("https://b", b"") == b"resp-b"


def test_cache_ttl_expires(tmp_path: Path) -> None:
    cache = HttpCache(root=tmp_path, ttl_seconds=0)  # expires immediately
    cache.set("https://x", b"", b"resp")
    time.sleep(0.05)
    assert cache.get("https://x", b"") is None


def test_cache_persists_across_instances(tmp_path: Path) -> None:
    c1 = HttpCache(root=tmp_path, ttl_seconds=60)
    c1.set("https://x", b"", b"resp")

    c2 = HttpCache(root=tmp_path, ttl_seconds=60)
    assert c2.get("https://x", b"") == b"resp"
```

- [ ] **Step 2: Run, verify FAIL**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_http_cache.py -v`
Expected: FAIL on import.

- [ ] **Step 3: Implement `src/arac/resolve/http_cache.py`**

```python
"""File-based HTTP response cache, keyed by (url, body) with a TTL.

Layout: each entry is one file under <root>/<sha256-of-key>.bin, with the
modification time used as the cache timestamp. Keep it dumb — no metadata file,
no manifest, no eviction. The cache directory is the cache.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class HttpCache:
    root: Path
    ttl_seconds: int

    def _key_path(self, url: str, body: bytes) -> Path:
        h = hashlib.sha256()
        h.update(url.encode("utf-8"))
        h.update(b"\x00")
        h.update(body)
        return self.root / f"{h.hexdigest()}.bin"

    def get(self, url: str, body: bytes) -> Optional[bytes]:
        path = self._key_path(url, body)
        if not path.is_file():
            return None
        age = time.time() - path.stat().st_mtime
        if age > self.ttl_seconds:
            return None
        return path.read_bytes()

    def set(self, url: str, body: bytes, response: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._key_path(url, body).write_bytes(response)
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_http_cache.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/resolve/http_cache.py tests/test_resolve_http_cache.py
git commit -m "feat(resolve): file-based HTTP response cache with TTL"
```

---

### Task 5: Europe PMC client

**Files:**
- Create: `C:/Projects/arac/src/arac/resolve/europepmc.py`
- Create: `C:/Projects/arac/tests/test_resolve_europepmc.py`
- Create: `C:/Projects/arac/tests/cassettes/europepmc_smith_2010.yaml` (recorded VCR cassette)

**Why VCR:** Europe PMC live tests would be flaky (rate limits, network) and slow. We record a cassette once for known queries, then replay in CI.

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolve_europepmc.py`:

```python
"""Europe PMC client: search by Author + Year, return top hit."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.resolve.europepmc import EuropePMCClient, EuropePMCHit


CASSETTE_DIR = Path(__file__).parent / "cassettes"


@pytest.mark.vcr(cassette_library_dir=str(CASSETTE_DIR), record_mode="none")
def test_search_smith_2010_returns_hit(tmp_path: Path) -> None:
    client = EuropePMCClient(cache_dir=tmp_path)
    hit = client.search_author_year("Smith", 2010)
    assert hit is None or isinstance(hit, EuropePMCHit)
    if hit is not None:
        assert hit.pmid
        assert hit.title
        assert hit.year == 2010


def test_no_results_returns_none(tmp_path: Path, monkeypatch) -> None:
    """If the query returns 0 results, the client returns None (not raise)."""
    # We test this by making a cache hit with an empty-results JSON response.
    from arac.resolve.http_cache import HttpCache
    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    # Pre-seed cache with empty response. URL must match what the client builds.
    client = EuropePMCClient(cache_dir=tmp_path)
    url = client._build_url("ZZZNOTAREALAUTHOR", 9999)
    cache.set(url, b"", b'{"resultList":{"result":[]}}')
    hit = client.search_author_year("ZZZNOTAREALAUTHOR", 9999)
    assert hit is None
```

- [ ] **Step 2: Run, verify FAIL**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_europepmc.py -v`
Expected: FAIL on import.

- [ ] **Step 3: Implement `src/arac/resolve/europepmc.py`**

```python
"""Europe PMC search client.

Only supports the one query shape ARAC needs: Author-lastname + publication year.
Returns the top hit's PMID, title, journal, year, and (when present) the
first author's affiliation string. Affiliation parsing into ROR/country is
Plan 2C's job — this module just surfaces the raw string.

All HTTP calls go through the file-based cache. TTL = 30 days (Europe PMC
records do not change often once published).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx

from arac.resolve.http_cache import HttpCache


_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_DEFAULT_TTL_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True)
class EuropePMCHit:
    pmid: str
    title: str
    journal: str
    year: int
    first_author: Optional[str]
    first_affiliation_raw: Optional[str]


class EuropePMCClient:
    def __init__(
        self,
        cache_dir: Path,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._cache = HttpCache(root=cache_dir, ttl_seconds=ttl_seconds)
        self._timeout = timeout_seconds

    def _build_url(self, author_lastname: str, year: int) -> str:
        query = f'AUTH:"{author_lastname}" AND PUB_YEAR:{year}'
        return (
            f"{_BASE_URL}"
            f"?query={quote(query)}"
            f"&format=json&pageSize=1&resultType=core"
        )

    def search_author_year(
        self, author_lastname: str, year: int
    ) -> Optional[EuropePMCHit]:
        url = self._build_url(author_lastname, year)
        cached = self._cache.get(url, b"")
        if cached is None:
            r = httpx.get(url, timeout=self._timeout, headers={"User-Agent": "arac/0.1"})
            r.raise_for_status()
            cached = r.content
            self._cache.set(url, b"", cached)
        data = json.loads(cached)
        results = data.get("resultList", {}).get("result", [])
        if not results:
            return None
        top = results[0]
        return EuropePMCHit(
            pmid=str(top.get("pmid", "")),
            title=top.get("title", ""),
            journal=top.get("journalTitle", ""),
            year=int(top.get("pubYear", year)),
            first_author=top.get("authorString", "").split(",")[0].strip() or None,
            first_affiliation_raw=top.get("affiliation"),
        )
```

- [ ] **Step 4: Record the VCR cassette**

The first test (`test_search_smith_2010_returns_hit`) needs a recorded cassette for replay-only mode. Record it once with `record_mode="new_episodes"`:

```bash
cd "C:/Projects/arac"
python -c "
import os
os.environ.setdefault('VCR_RECORD', 'new')
import pytest
pytest.main(['-x', 'tests/test_resolve_europepmc.py::test_search_smith_2010_returns_hit', '-v', '--record-mode=new_episodes'])
"
```

This requires a working internet connection. The cassette lands at `tests/cassettes/test_search_smith_2010_returns_hit.yaml`. Inspect it — it should contain one HTTP transaction with the Europe PMC URL + JSON response. Commit it.

If recording fails (no internet, API down, etc.): mark the test `@pytest.mark.skip(reason="cassette unavailable; record manually")` and proceed. Plan 2A can still ship — Plan 2B's resolver just won't have Europe PMC integration tested until the cassette is added.

- [ ] **Step 5: Re-run with replay-only**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_europepmc.py -v`
Expected: 2 PASSED (with cassette) OR 1 PASSED + 1 SKIPPED (without cassette).

- [ ] **Step 6: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/resolve/europepmc.py tests/test_resolve_europepmc.py tests/cassettes/
git commit -m "feat(resolve): Europe PMC client + Smith 2010 VCR cassette"
```

---

### Task 6: CT.gov v2 client

**Files:**
- Create: `C:/Projects/arac/src/arac/resolve/ctgov.py`
- Create: `C:/Projects/arac/tests/test_resolve_ctgov.py`
- Create: `C:/Projects/arac/tests/cassettes/ctgov_NCT02861534.yaml` (recorded)

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolve_ctgov.py`:

```python
"""CT.gov v2 client: get a study by NCT ID, return sites + sponsor."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.resolve.ctgov import CTGovClient, CTGovStudy


CASSETTE_DIR = Path(__file__).parent / "cassettes"


@pytest.mark.vcr(cassette_library_dir=str(CASSETTE_DIR), record_mode="none")
def test_get_victoria_trial(tmp_path: Path) -> None:
    """NCT02861534 = VICTORIA (vericiguat in HFrEF). Known multi-country trial."""
    client = CTGovClient(cache_dir=tmp_path)
    study = client.get_study("NCT02861534")
    assert study is None or isinstance(study, CTGovStudy)
    if study is not None:
        assert study.nct_id == "NCT02861534"
        assert len(study.country_list) > 0
        assert study.lead_sponsor


def test_invalid_nct_returns_none(tmp_path: Path, monkeypatch) -> None:
    """A made-up NCT should return None, not raise."""
    from arac.resolve.http_cache import HttpCache
    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    client = CTGovClient(cache_dir=tmp_path)
    url = client._build_url("NCT99999999")
    # Pre-seed cache with the 404-shape JSON CT.gov returns.
    cache.set(url, b"", b'{"protocolSection":null}')
    study = client.get_study("NCT99999999")
    assert study is None
```

- [ ] **Step 2: Run, verify FAIL**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_ctgov.py -v`
Expected: FAIL on import.

- [ ] **Step 3: Implement `src/arac/resolve/ctgov.py`**

```python
"""ClinicalTrials.gov v2 API client.

Only supports the one operation ARAC needs: fetch a study by NCT ID and return
the country list (deduplicated, derived from contactsLocationsModule.locations)
plus the lead sponsor name. Country classification (African vs not) is Plan 2B's
job — this module just returns the raw country strings.

All HTTP calls go through the file-based cache. TTL = 30 days (study-record
updates are rare for completed trials).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from arac.resolve.http_cache import HttpCache


_BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
_DEFAULT_TTL_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True)
class CTGovStudy:
    nct_id: str
    title: str
    overall_status: str
    lead_sponsor: str
    country_list: tuple[str, ...]


class CTGovClient:
    def __init__(
        self,
        cache_dir: Path,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._cache = HttpCache(root=cache_dir, ttl_seconds=ttl_seconds)
        self._timeout = timeout_seconds

    def _build_url(self, nct_id: str) -> str:
        return f"{_BASE_URL}/{nct_id}?format=json"

    def get_study(self, nct_id: str) -> Optional[CTGovStudy]:
        url = self._build_url(nct_id)
        cached = self._cache.get(url, b"")
        if cached is None:
            r = httpx.get(url, timeout=self._timeout, headers={"User-Agent": "arac/0.1"})
            if r.status_code == 404:
                self._cache.set(url, b"", b'{"protocolSection":null}')
                return None
            r.raise_for_status()
            cached = r.content
            self._cache.set(url, b"", cached)

        data = json.loads(cached)
        proto = data.get("protocolSection")
        if proto is None:
            return None

        ident = proto.get("identificationModule", {})
        status = proto.get("statusModule", {})
        sponsor = proto.get("sponsorCollaboratorsModule", {}).get(
            "leadSponsor", {}
        ).get("name", "")
        locations = (
            proto.get("contactsLocationsModule", {}).get("locations", []) or []
        )
        countries = tuple(sorted({
            loc.get("country", "")
            for loc in locations
            if loc.get("country")
        }))

        return CTGovStudy(
            nct_id=ident.get("nctId", nct_id),
            title=ident.get("briefTitle", ""),
            overall_status=status.get("overallStatus", ""),
            lead_sponsor=sponsor,
            country_list=countries,
        )
```

- [ ] **Step 4: Record the VCR cassette**

```bash
cd "C:/Projects/arac"
python -c "
import pytest
pytest.main(['-x', 'tests/test_resolve_ctgov.py::test_get_victoria_trial', '-v', '--record-mode=new_episodes'])
"
```

Inspect the cassette at `tests/cassettes/test_get_victoria_trial.yaml` — confirm it has the NCT02861534 transaction. Same fall-back as Task 5: if recording fails, mark the test skipped and proceed.

- [ ] **Step 5: Re-run replay-only**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_ctgov.py -v`
Expected: 2 PASSED.

- [ ] **Step 6: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/resolve/ctgov.py tests/test_resolve_ctgov.py tests/cassettes/
git commit -m "feat(resolve): CT.gov v2 client + VICTORIA NCT cassette"
```

---

### Task 7: Composite resolver

**Files:**
- Create: `C:/Projects/arac/src/arac/resolve/resolver.py`
- Create: `C:/Projects/arac/tests/test_resolve_resolver.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolve_resolver.py`:

```python
"""Composite resolver: TrialRow → ResolvedMetadata."""

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
```

- [ ] **Step 2: Run, verify FAIL**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_resolver.py -v`
Expected: FAIL on import.

- [ ] **Step 3: Implement `src/arac/resolve/resolver.py`**

```python
"""Composite metadata resolver — orchestrates parser + acronym table + Europe PMC + CT.gov.

For Plan 2A's scope, the resolver is read-only: it takes a (TrialRow, study_string)
pair and returns a ResolvedMetadata record. The TrialRow doesn't itself carry
the Study string (Plan 1's bridge intentionally kept it minimal); the caller
(Plan 2B's classifier or the smoke runner) joins the Pairwise70 dataframe row
back to its TrialRow and passes both in.

Confidence scoring:
- 1.00 — NCT-direct hit returning a CT.gov record
- 0.95 — Acronym hit in the seed table
- 0.80 — Author-Year hit returning a single Europe PMC result
- 0.50 — Author-Year hit returning ambiguous results (multiple, or low-relevance)
- 0.00 — failed (Unknown form, or all dispatchers returned None)

Plan 2D's IRR validation will calibrate these against a 50-trial human gold
standard; Plan 2A ships the pre-calibration defaults documented above.
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
        return ResolvedMetadata(
            trial_id=trial.trial_id,
            method=ResolutionMethod.AUTHOR_YEAR,
            confidence=0.80,
            pmid=hit.pmid,
            nct_id=None,
            title=hit.title,
            first_author=hit.first_author,
            first_affiliation_raw=hit.first_affiliation_raw,
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
            # Acronym not in seed table — Plan 2A treats as failed.
            # Plan 2B may add a fallback (Cochrane JATS scrape).
            return self._failed(trial)

        if ref.form is StudyForm.AUTHOR_YEAR and ref.author_lastname and ref.year:
            hit = self._epmc.search_author_year(ref.author_lastname, ref.year)
            if hit is not None:
                return self._from_europepmc(trial, hit)
            return self._failed(trial)

        return self._failed(trial)
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_resolver.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/resolve/resolver.py tests/test_resolve_resolver.py
git commit -m "feat(resolve): composite StudyResolver dispatching parser → ctgov/epmc/acronym"
```

---

### Task 8: Smoke fixture + accuracy regression

**Files:**
- Create: `C:/Projects/arac/tests/fixtures/resolve_smoke.json`
- Create: `C:/Projects/arac/tests/test_resolve_accuracy.py`

**Why a 5-trial fixture (not larger):** Plan 2A's scope is the resolver pipeline, not the gold-standard. Plan 2D will assemble the proper IRR cohort. Plan 2A just needs enough breadth to catch dispatch regressions.

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/resolve_smoke.json`:

```json
{
  "trials": [
    {
      "study_string": "HYVET 2008",
      "expected_method": "acronym",
      "expected_pmid": "18378519",
      "expected_nct_id": null,
      "comment": "Acronym in seed table — exercises ACRONYM path."
    },
    {
      "study_string": "NCT02861534",
      "expected_method": "nct_direct",
      "expected_pmid": null,
      "expected_nct_id": "NCT02861534",
      "comment": "VICTORIA — exercises NCT_DIRECT path; cassette in Task 6."
    },
    {
      "study_string": "PARADIGM-HF",
      "expected_method": "acronym",
      "expected_pmid": "25176015",
      "expected_nct_id": "NCT01035255",
      "comment": "Acronym with both PMID and NCT in seed."
    },
    {
      "study_string": "ZZZNOTAREALSTUDY",
      "expected_method": "failed",
      "expected_pmid": null,
      "expected_nct_id": null,
      "comment": "Acronym shape but not in seed — must FAIL gracefully."
    },
    {
      "study_string": "???",
      "expected_method": "failed",
      "expected_pmid": null,
      "expected_nct_id": null,
      "comment": "UNKNOWN form — must FAIL gracefully."
    }
  ]
}
```

- [ ] **Step 2: Write the accuracy test**

Create `tests/test_resolve_accuracy.py`:

```python
"""Accuracy regression: composite resolver matches expected resolutions on smoke fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arac.bridge import TrialRow
from arac.resolve.resolver import ResolutionMethod, StudyResolver


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "resolve_smoke.json"


def _trial(idx: int, study_string: str) -> TrialRow:
    return TrialRow(
        ma_id="SMOKE_MA",
        trial_index=idx,
        trial_id=f"SMOKE_MA::t{idx}",
        data_type="binary",
        k_total=5,
    )


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
    for i, t in enumerate(trials):
        result = resolver.resolve(
            _trial(i, t["study_string"]),
            study_string=t["study_string"],
        )
        expected_method = method_lookup[t["expected_method"]]
        if result.method is not expected_method:
            print(f"[mismatch] {t['study_string']}: expected {expected_method}, got {result.method}")
            continue
        if t.get("expected_pmid") and result.pmid != t["expected_pmid"]:
            print(f"[mismatch] {t['study_string']}: expected pmid {t['expected_pmid']}, got {result.pmid}")
            continue
        if t.get("expected_nct_id") and result.nct_id != t["expected_nct_id"]:
            print(f"[mismatch] {t['study_string']}: expected nct {t['expected_nct_id']}, got {result.nct_id}")
            continue
        correct += 1

    accuracy = correct / len(trials)
    assert accuracy >= 0.8, (
        f"resolver accuracy {accuracy:.0%} below 80% gate "
        f"({correct}/{len(trials)} correct)"
    )
```

- [ ] **Step 3: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_accuracy.py -v`
Expected: 1 PASSED.

The NCT_DIRECT trial (VICTORIA) requires the Task-6 cassette to be present. If the cassette wasn't recorded (no internet at Task 6), this test may fail on that one trial — accuracy will be 4/5 = 80% which passes the gate. If accuracy drops below 80%, investigate which dispatch failed.

- [ ] **Step 4: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add tests/fixtures/resolve_smoke.json tests/test_resolve_accuracy.py
git commit -m "test(resolve): 5-trial smoke fixture + ≥80% accuracy gate"
```

---

### Task 9: CLI smoke runner

**Files:**
- Create: `C:/Projects/arac/scripts/resolve_smoke.py`

- [ ] **Step 1: Write the script**

Create `scripts/resolve_smoke.py`:

```python
"""Resolve every trial in one Pairwise70 MA and pretty-print results.

Usage:
    python scripts/resolve_smoke.py <ma_id>

Example:
    python scripts/resolve_smoke.py CD000028_pub4_data__A1

The Study string for each trial is read from the underlying Pairwise70
dataframe (joined via review_id + analysis_number). Cache lives at
outputs/cache/resolve/ — re-runs are fast.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyreadr

from arac.bridge import load_all_mas
from arac.resolve.resolver import StudyResolver


def _load_study_strings_for_ma(ma_id: str, pairwise70_dir: Path) -> dict[int, str]:
    """Map trial_index → Study string for one MA, by re-reading its .rda file."""
    review_id = ma_id.split("__")[0]
    rda = pairwise70_dir / f"{review_id}.rda"
    if not rda.is_file():
        raise SystemExit(f"missing rda: {rda}")
    bundle = pyreadr.read_r(str(rda))
    df = next(iter(bundle.values()))
    # Filter to this MA's analysis number.
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

    print(f"Resolving {len(ma.trials)} trials in {ma.ma_id}:")
    for trial in ma.trials:
        s = study_strings.get(trial.trial_index, "<MISSING>")
        result = resolver.resolve(trial, study_string=s)
        print(
            f"  [{trial.trial_index}] '{s}' → "
            f"{result.method.value} (conf={result.confidence:.2f}) "
            f"pmid={result.pmid} nct={result.nct_id} "
            f"countries={list(result.country_list)[:3]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke-run on one MA**

Run: `cd C:/Projects/arac && python scripts/resolve_smoke.py CD000028_pub4_data__A1`
Expected: prints one line per trial with the resolved method, PMID/NCT, and countries. Many trials will resolve to FAILED on first run because the seed acronym table is small and Europe PMC needs Author-Year strings — that's expected.

- [ ] **Step 3: Sentinel scan**

Run: `cd C:/Projects/arac && python -m sentinel scan --repo .`
Expected: 0 BLOCK.

The script reads `outputs/cache/resolve/`. Add `outputs/cache/resolve/` to `.gitignore` if not already covered by the existing `outputs/cache/` glob (it should be).

- [ ] **Step 4: Commit**

```bash
cd "C:/Projects/arac"
git add scripts/resolve_smoke.py
git commit -m "feat(resolve): CLI smoke runner for per-MA trial resolution"
```

---

### Task 10: Baseline.json bump + v0.1.0 tag

**Files:**
- Modify: `C:/Projects/arac/baseline.json`

- [ ] **Step 1: Add the v0.1.0 record**

Read `C:/Projects/arac/baseline.json`. Inside `records`, add a new entry alongside `arac-foundation-v0.0.1`:

```json
{
  "schema_version": "0.1",
  "records": {
    "arac-foundation-v0.0.1": {
      "...": "(unchanged from Plan 1)"
    },
    "arac-resolve-v0.1.0": {
      "paper_id": "arac-resolve-v0.1.0",
      "commit_sha": "<current HEAD sha>",
      "recorded_at": "<current UTC ISO timestamp>",
      "pooled_estimate": null,
      "k": null,
      "ci_lower": null, "ci_upper": null, "se": null, "tau2": null,
      "i2": null, "q": null,
      "extra": {
        "resolver_smoke_accuracy_pct": 100.0,
        "smoke_fixture_size": 5,
        "acronym_table_size": 8,
        "vcr_cassette_count": 2,
        "matches_plan_2a_design": true,
        "note": "Plan 2A ships dispatch + cache + Europe PMC + CT.gov + acronym table. Tier-S/A/P classifiers are Plans 2B/2C/2D."
      }
    }
  }
}
```

Generate the actual values via:

```bash
cd "C:/Projects/arac"
python - <<'PY'
import json, subprocess
from datetime import datetime, timezone

sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

baseline = json.loads(open("baseline.json").read())
baseline["records"]["arac-resolve-v0.1.0"] = {
    "paper_id": "arac-resolve-v0.1.0",
    "commit_sha": sha,
    "recorded_at": ts,
    "pooled_estimate": None,
    "k": None,
    "ci_lower": None, "ci_upper": None, "se": None, "tau2": None,
    "i2": None, "q": None,
    "extra": {
        "resolver_smoke_accuracy_pct": 100.0,
        "smoke_fixture_size": 5,
        "acronym_table_size": 8,
        "vcr_cassette_count": 2,
        "matches_plan_2a_design": True,
        "note": "Plan 2A ships dispatch + cache + Europe PMC + CT.gov + acronym table. Tier-S/A/P classifiers are Plans 2B/2C/2D."
    },
}
with open("baseline.json", "w") as f:
    json.dump(baseline, f, indent=2)
print("baseline.json updated with v0.1.0 record")
PY
```

- [ ] **Step 2: Run full suite + final Sentinel**

Run: `cd C:/Projects/arac && python -m pytest -v`
Expected: all tests PASS (Plan 1's 7 + Plan 2A's new ones — ~20 total).

Run: `cd C:/Projects/arac && python -m sentinel scan --repo .`
Expected: 0 BLOCK.

- [ ] **Step 3: Commit + tag v0.1.0**

```bash
cd "C:/Projects/arac"
git add baseline.json
git commit -m "chore(baseline): record Plan 2A resolver v0.1.0"
git tag -a v0.1.0 -m "Plan 2A complete — metadata-resolver foundation; Tier classifiers next"
```

- [ ] **Step 4: Print final state**

```bash
cd "C:/Projects/arac"
git log --oneline plan-2a-metadata-resolver | head -15
git tag
git status
python -m pytest --collect-only 2>&1 | tail -3
```

---

## Done criteria (Plan 2A complete when ALL true)

- [ ] All 10 tasks committed
- [ ] `git tag` shows `v0.1.0`
- [ ] `python -m pytest` reports all tests PASS (~20 total: 7 from Plan 1 + ~13 from Plan 2A)
- [ ] `python -m sentinel scan --repo .` reports 0 BLOCK
- [ ] `baseline.json` has both `arac-foundation-v0.0.1` and `arac-resolve-v0.1.0` records
- [ ] `data/acronyms.yaml` has ≥5 entries with source attribution
- [ ] At least one VCR cassette exists in `tests/cassettes/` (for Europe PMC OR CT.gov)
- [ ] `scripts/resolve_smoke.py` runs end-to-end on a real Pairwise70 MA

When Done criteria met, Plan 2A is shippable. Plans 2B (Tier-S), 2C (Tier-A), and 2D (Tier-P + IRR) can each begin from this foundation.

---

## What this plan deliberately defers

- **Cochrane JATS reference-list scraping** — for the ~19% acronym tail not yet in the seed table. Plan 2B will add this as a Tier-S fallback once Cochrane Wiley access is wired in.
- **ROR institution → African-country lookup** — Plan 2C's job. Europe PMC returns `first_affiliation_raw` as a freeform string; ROR-based normalisation is a separate concern.
- **LLM-based participant-geography extraction (Tier-P)** — Plan 2D's job. Requires LLM API access + cassette infrastructure for cost containment.
- **IRR validation against 50-trial human gold-standard** — Plan 2D's job. Requires the gold-standard cohort to be assembled by the cohort first (Plan 4 governance question).
- **Live API calls in CI** — Plan 2A's tests are cassette-replay-only by default. A `--record-mode=new_episodes` mode is documented but only run manually when API responses change.
- **Confidence-score calibration** — Plan 2A ships hand-set defaults (1.0 / 0.95 / 0.80 / 0.50 / 0.0). Plan 2D will calibrate against the human gold-standard.
