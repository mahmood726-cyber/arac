# ARAC — Plan 2D of Plan 2: Tier-P (Participant-Geography) Classifier

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify each Pairwise70 trial on Tier-P — does the trial's participant population have **≥50% African participants**? Returns a per-trial `TierP` label (`AFRICAN_MAJORITY` / `NOT_AFRICAN_MAJORITY` / `INSUFFICIENT_DATA`) plus a confidence score, the extracted percentage, and the source text quote. This is the third of three Tier classifiers and completes the spec's S/A/P triad.

**Architecture:** LLM-based structured extraction. For each trial with a resolved abstract (from PubMed efetch via Plan 2A.1), we ask Claude Opus 4.7 to extract participant-geography data into a Pydantic schema using `client.messages.parse()`. The system prompt is **stable across all trials** (it describes the extraction task) and gets `cache_control: ephemeral` for ~10× cost savings on input tokens. The variable part is the trial's title + abstract, sent as the user message. Responses are cached on disk with the same `HttpCache` pattern used by Plan 2A's HTTP wrappers, keyed by `(model, system_prompt_hash, abstract_hash)`.

**Tier-P logic:**
- `african_participant_pct ≥ 50` → AFRICAN_MAJORITY (confidence ∝ extractor confidence)
- `african_participant_pct < 50` AND `extractor_confidence != "insufficient"` → NOT_AFRICAN_MAJORITY
- LLM returns `confidence: "insufficient"` OR no abstract available → INSUFFICIENT_DATA

**Tech Stack:** Python 3.13 (existing), `anthropic` SDK (new), `pydantic` (new). Reuses Plan 2A's `HttpCache` (renamed for clarity to support non-HTTP responses, OR a new `LLMCache` is fine). Default model: `claude-opus-4-7` (per the claude-api skill's "ALWAYS use Opus 4.7 unless user explicitly chooses otherwise"). Configurable via env var `ARAC_TIER_P_MODEL` for users who prefer Haiku 4.5 for cost (high-volume extraction = 60K trials × ~500 input tokens; Opus is ~5× the cost of Haiku).

**Out of scope for Plan 2D:**
- 50-trial human gold-standard cohort + IRR validation — separate Plan 2E (needs the cohort assembled by Mahmood + the PhD students, not by code)
- Cochrane JATS reference-list scrape for pre-1995 trials missing PubMed abstracts — Plan 2F
- The atlas dashboard + RGS engine (Plan 3)
- Verification UI (Plan 3)

**Cost note:** Real production extraction of all ~60,000 Pairwise70 trials × Opus 4.7 ≈ ~$200 raw, with prompt caching ≈ ~$30 amortized. The user can defer that run to a dedicated batch session; Plan 2D ships the *capability* with pre-cached test fixtures, not the full atlas extraction.

**Companion files (read-only inputs):**
- `C:/Projects/arac/src/arac/resolve/pubmed.py` — provides abstract via `efetch` (will be extended in Task 2 to expose `Abstract` element)
- `C:/Projects/arac/src/arac/classify/african_countries.py` — `is_african_country` reused for sanity checks
- `C:/Projects/arac/baseline.json` — append v0.4.0 record at end

---

### Task 1: Anthropic SDK + pre-flight gate

**Files:**
- Modify: `C:/Projects/arac/pyproject.toml`
- Create: `C:/Projects/arac/src/arac/classify/_anthropic_pre.py`
- Create: `C:/Projects/arac/tests/test_classify_anthropic_preflight.py`

- [ ] **Step 1: Add deps to `pyproject.toml`**

Add `anthropic>=0.40` and `pydantic>=2.5` to `dependencies`. Final shape:

```toml
dependencies = [
    "numpy>=1.26",
    "pyreadr>=0.5",
    "scipy>=1.11",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "psycopg2-binary>=2.9",
    "anthropic>=0.40",
    "pydantic>=2.5",
]
```

Run: `cd C:/Projects/arac && pip install -e ".[dev]"`

- [ ] **Step 2: Write `src/arac/classify/_anthropic_pre.py`**

```python
"""Pre-flight gate for Anthropic API access.

Plan 2D's Tier-P classifier requires the Anthropic API. The pre-flight checks:
1. ANTHROPIC_API_KEY env var is set (or ARAC_ANTHROPIC_API_KEY for project-scoped)
2. Resolved model name from ARAC_TIER_P_MODEL env var (default: claude-opus-4-7)
3. Optionally — if `live=True` — issue a 1-token validation call to confirm the
   key actually works (catches typo'd keys without surprising users mid-batch)

Per the claude-api skill: default model is claude-opus-4-7. Users can override
via ARAC_TIER_P_MODEL for cost-sensitivity (e.g. claude-haiku-4-5 for ~5x
cheaper extraction at lower accuracy).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


_DEFAULT_MODEL = "claude-opus-4-7"


@dataclass(frozen=True)
class AnthropicConfig:
    api_key: str
    model: str


def resolve_anthropic_config() -> AnthropicConfig:
    """Resolve API key + model. Raises RuntimeError if no key is set."""
    api_key = (
        os.environ.get("ARAC_ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    if not api_key:
        raise RuntimeError(
            "Anthropic API key not set. Set ARAC_ANTHROPIC_API_KEY (preferred) "
            "or ANTHROPIC_API_KEY. Plan 2D Tier-P classifier requires LLM access "
            "for participant-geography extraction."
        )
    model = os.environ.get("ARAC_TIER_P_MODEL", _DEFAULT_MODEL)
    return AnthropicConfig(api_key=api_key, model=model)


def validate_live(config: Optional[AnthropicConfig] = None) -> bool:
    """Issue a tiny test call to validate the key actually works.

    Returns True on success. Raises if the key is rejected (401) or model is
    unavailable (404). Caller should wrap in try/except.
    """
    import anthropic
    cfg = config or resolve_anthropic_config()
    client = anthropic.Anthropic(api_key=cfg.api_key)
    response = client.messages.create(
        model=cfg.model,
        max_tokens=8,
        messages=[{"role": "user", "content": "Say 'ok' and nothing else."}],
    )
    return any(b.type == "text" for b in response.content)
```

- [ ] **Step 3: Write `tests/test_classify_anthropic_preflight.py`**

```python
"""Pre-flight: ANTHROPIC_API_KEY (or ARAC_ANTHROPIC_API_KEY) is reachable."""

from __future__ import annotations

import os

import pytest

from arac.classify._anthropic_pre import (
    AnthropicConfig,
    resolve_anthropic_config,
    validate_live,
)


def test_resolve_config_with_env(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
    monkeypatch.delenv("ARAC_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ARAC_TIER_P_MODEL", raising=False)
    cfg = resolve_anthropic_config()
    assert isinstance(cfg, AnthropicConfig)
    assert cfg.api_key == "sk-ant-test-fake-key"
    assert cfg.model == "claude-opus-4-7"


def test_resolve_config_prefers_arac_var(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fallback-key")
    monkeypatch.setenv("ARAC_ANTHROPIC_API_KEY", "preferred-key")
    cfg = resolve_anthropic_config()
    assert cfg.api_key == "preferred-key"


def test_resolve_config_model_override(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ARAC_TIER_P_MODEL", "claude-haiku-4-5")
    cfg = resolve_anthropic_config()
    assert cfg.model == "claude-haiku-4-5"


def test_resolve_config_missing_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ARAC_ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Anthropic API key not set"):
        resolve_anthropic_config()


def test_validate_live() -> None:
    """Live validation — only runs if ANTHROPIC_API_KEY is actually set in env.
    Skipped on machines without API access (CI, dev machines without the key).
    """
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ARAC_ANTHROPIC_API_KEY")):
        pytest.skip("No Anthropic API key in env; live validation skipped")
    assert validate_live() is True
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_classify_anthropic_preflight.py -v`
Expected: 4 PASSED + 1 SKIPPED (live validation skips without API key on this machine).

If `validate_live` runs and FAILS with 401 — the API key is wrong; surface to user. If it fails with 404 — the model name is wrong (typo in `ARAC_TIER_P_MODEL`).

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add pyproject.toml src/arac/classify/_anthropic_pre.py tests/test_classify_anthropic_preflight.py
git commit -m "feat(classify-tier-p): Anthropic pre-flight gate (key resolution + optional live validation)"
```

---

### Task 2: Extend `PubMedClient` to expose abstract text

**Files:**
- Modify: `C:/Projects/arac/src/arac/resolve/pubmed.py`
- Modify: `C:/Projects/arac/tests/test_resolve_pubmed.py`

**Backwards-compat constraint:** Plan 2A.1's resolver and Plan 2C's classifier rely on existing `PubMedRecord` fields. Add `abstract_text: Optional[str]` without removing or renaming any existing field.

- [ ] **Step 1: Append failing test**

```python
def test_efetch_extracts_abstract(tmp_path: Path) -> None:
    """PubMedRecord now carries abstract_text from the NLM XML's <AbstractText>."""
    from arac.resolve.http_cache import HttpCache
    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    client = PubMedClient(cache_dir=tmp_path)
    url = client._build_url("99999")
    pubmed_xml = (
        '<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        '<PMID>99999</PMID><Article><AuthorList>'
        '<Author><LastName>Test</LastName></Author>'
        '</AuthorList>'
        '<Abstract>'
        '<AbstractText Label="BACKGROUND">Background paragraph.</AbstractText>'
        '<AbstractText Label="METHODS">Methods paragraph.</AbstractText>'
        '<AbstractText Label="RESULTS">Results paragraph including the cohort: 200 participants in Uganda and 100 in Kenya.</AbstractText>'
        '</Abstract>'
        '</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(url, b"", pubmed_xml.encode())
    rec = client.efetch("99999")
    
    assert rec is not None
    assert rec.abstract_text is not None
    # Multi-section abstracts get joined; should contain all three parts
    assert "Background paragraph" in rec.abstract_text
    assert "Methods paragraph" in rec.abstract_text
    assert "Uganda" in rec.abstract_text
    # Backwards compat: existing fields still populated
    assert rec.first_author_lastname == "Test"


def test_efetch_handles_missing_abstract(tmp_path: Path) -> None:
    from arac.resolve.http_cache import HttpCache
    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    client = PubMedClient(cache_dir=tmp_path)
    url = client._build_url("11111")
    # NO <Abstract> element — old NLM records often lack one
    pubmed_xml = (
        '<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        '<PMID>11111</PMID><Article><AuthorList>'
        '<Author><LastName>Old</LastName></Author>'
        '</AuthorList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(url, b"", pubmed_xml.encode())
    rec = client.efetch("11111")
    
    assert rec is not None
    assert rec.abstract_text is None
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL — `PubMedRecord` doesn't have `abstract_text` field yet.

- [ ] **Step 3: Modify `pubmed.py`**

Add `abstract_text: Optional[str] = None` to `PubMedRecord`. Modify `efetch()` to extract:

```python
# Inside efetch(), after parsing authors:

# Extract abstract — concatenate all <AbstractText> elements (some PubMed
# records have multi-section structured abstracts: BACKGROUND/METHODS/RESULTS).
abstract_els = article.findall(".//Abstract/AbstractText")
abstract_parts: list[str] = []
for el in abstract_els:
    label = el.attrib.get("Label")
    text = (el.text or "").strip()
    if not text:
        continue
    if label:
        abstract_parts.append(f"{label}: {text}")
    else:
        abstract_parts.append(text)
abstract_text = "\n\n".join(abstract_parts) if abstract_parts else None

return PubMedRecord(
    pmid=pmid,
    first_author_lastname=first.lastname if first else None,
    first_author_affiliation=first.affiliation if first else None,
    authors=authors,
    abstract_text=abstract_text,
)
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_resolve_pubmed.py -v`
Expected: 5 PASSED (3 existing + 2 new).

Run: `cd C:/Projects/arac && python -m pytest -v` — must still report all green (no regression).

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/resolve/pubmed.py tests/test_resolve_pubmed.py
git commit -m "feat(resolve): PubMedRecord exposes abstract_text from <AbstractText> elements"
```

---

### Task 3: LLM extractor — `ParticipantGeography` schema + extraction module

**Files:**
- Create: `C:/Projects/arac/src/arac/classify/llm_cache.py`
- Create: `C:/Projects/arac/src/arac/classify/tier_p_extractor.py`
- Create: `C:/Projects/arac/tests/test_classify_tier_p_extractor.py`

- [ ] **Step 1: Write `llm_cache.py`** — disk-cache for LLM responses

```python
"""Disk cache for LLM responses, keyed by (model, system_hash, user_hash).

Same shape as resolve/http_cache.py but the key inputs are model + system + user
content (not URL + body). TTL longer (~90 days) since LLM responses are
deterministic enough for our extraction task that we can reuse aggressively.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class LLMCache:
    root: Path
    ttl_seconds: int = 90 * 24 * 3600  # 90 days

    def _key_path(self, model: str, system_prompt: str, user_input: str) -> Path:
        h = hashlib.sha256()
        h.update(model.encode("utf-8"))
        h.update(b"\x00")
        h.update(system_prompt.encode("utf-8"))
        h.update(b"\x00")
        h.update(user_input.encode("utf-8"))
        return self.root / f"{h.hexdigest()}.json"

    def get(self, model: str, system_prompt: str, user_input: str) -> Optional[str]:
        path = self._key_path(model, system_prompt, user_input)
        if not path.is_file():
            return None
        age = time.time() - path.stat().st_mtime
        if age > self.ttl_seconds:
            return None
        return path.read_text(encoding="utf-8")

    def set(self, model: str, system_prompt: str, user_input: str, response: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._key_path(model, system_prompt, user_input).write_text(response, encoding="utf-8")
```

- [ ] **Step 2: Write `tier_p_extractor.py`**

```python
"""LLM-based extraction of participant geography from trial abstracts.

Uses Anthropic's `messages.parse()` with a Pydantic schema for reliable
structured output. The system prompt is stable across all extractions and
gets prompt-cached (huge cost savings on input tokens). The variable input
is the trial title + abstract.

Default model is claude-opus-4-7 (per the claude-api skill's recommendation).
Users can override via ARAC_TIER_P_MODEL env var for cost reasons.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from arac.classify._anthropic_pre import AnthropicConfig, resolve_anthropic_config
from arac.classify.llm_cache import LLMCache


_SYSTEM_PROMPT = """You are extracting participant-geography data from clinical trial reports for a meta-research project (ARAC — African Representation Atlas of Cochrane).

Given a trial's title and abstract, identify what fraction of participants were enrolled in African countries vs non-African countries.

Definitions:
- "African" means the participant was enrolled at a site in any of the 54 African Union member states (Algeria, Angola, Benin, Botswana, Burkina Faso, Burundi, Cabo Verde, Cameroon, Central African Republic, Chad, Comoros, Congo, Democratic Republic of the Congo, Cote d'Ivoire, Djibouti, Egypt, Equatorial Guinea, Eritrea, Eswatini, Ethiopia, Gabon, Gambia, Ghana, Guinea, Guinea-Bissau, Kenya, Lesotho, Liberia, Libya, Madagascar, Malawi, Mali, Mauritania, Mauritius, Morocco, Mozambique, Namibia, Niger, Nigeria, Rwanda, Sao Tome and Principe, Senegal, Seychelles, Sierra Leone, Somalia, South Africa, South Sudan, Sudan, Tanzania, Togo, Tunisia, Uganda, Zambia, Zimbabwe).

Rules:
1. Only count participants explicitly described in the abstract. Do not infer from author affiliations or sponsor location.
2. If exact percentages are given, use them. If only counts are given (e.g., "200 in Uganda, 100 in Kenya, 700 in USA"), compute the percentage.
3. If geography is not mentioned in the abstract at all, set confidence to "insufficient" and leave percentages null.
4. If the abstract mentions a multi-country trial without specifying counts (e.g., "conducted in 14 countries including Uganda and South Africa"), set confidence to "low" and estimate based on country count if possible.
5. Always quote the exact source text you used as evidence.
6. Be conservative: if you're not sure, set confidence to "insufficient" rather than guessing.

Return a structured ParticipantGeography record. Set null values when the abstract doesn't support extraction; do not fabricate."""


class ParticipantGeography(BaseModel):
    african_participant_pct: Optional[float] = Field(
        None,
        description="Percentage of participants enrolled in African countries (0-100), or null if not extractable.",
        ge=0,
        le=100,
    )
    non_african_participant_pct: Optional[float] = Field(
        None,
        description="Percentage of participants enrolled in non-African countries (0-100), or null if not extractable.",
        ge=0,
        le=100,
    )
    countries_mentioned: list[str] = Field(
        default_factory=list,
        description="List of country names mentioned in the abstract as enrollment sites.",
    )
    evidence_source: Optional[str] = Field(
        None,
        description="Exact quote from the abstract that supports the percentage extraction.",
    )
    confidence: Literal["high", "medium", "low", "insufficient"] = Field(
        ...,
        description="high = exact percentages given; medium = counts → computed pct; low = country list only; insufficient = no geography in abstract.",
    )
    reasoning: str = Field(
        ...,
        description="Brief one-paragraph explanation of how the extraction was performed.",
    )


@dataclass(frozen=True)
class ExtractionInput:
    pmid: str
    title: str
    abstract: str


class TierPExtractor:
    def __init__(
        self,
        cache_dir: Path,
        config: Optional[AnthropicConfig] = None,
    ) -> None:
        self._cache = LLMCache(root=cache_dir / "tier_p_llm")
        self._config = config or resolve_anthropic_config()

    def _user_input(self, item: ExtractionInput) -> str:
        return (
            f"PMID: {item.pmid}\n\n"
            f"Title: {item.title}\n\n"
            f"Abstract:\n{item.abstract}"
        )

    def extract(self, item: ExtractionInput) -> ParticipantGeography:
        user_text = self._user_input(item)
        cached = self._cache.get(self._config.model, _SYSTEM_PROMPT, user_text)
        if cached is not None:
            return ParticipantGeography.model_validate_json(cached)

        # Lazy-import anthropic so tests that pre-seed the cache don't need the SDK loaded.
        import anthropic
        client = anthropic.Anthropic(api_key=self._config.api_key)
        response = client.messages.parse(
            model=self._config.model,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_text}],
            output_format=ParticipantGeography,
        )
        result: ParticipantGeography = response.parsed_output
        self._cache.set(self._config.model, _SYSTEM_PROMPT, user_text, result.model_dump_json())
        return result
```

- [ ] **Step 3: Write tests using pre-seeded cache (no live API calls)**

Create `tests/test_classify_tier_p_extractor.py`:

```python
"""Tier-P extractor tests — all use pre-seeded LLM cache, no live API calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.classify._anthropic_pre import AnthropicConfig
from arac.classify.llm_cache import LLMCache
from arac.classify.tier_p_extractor import (
    ExtractionInput,
    ParticipantGeography,
    TierPExtractor,
    _SYSTEM_PROMPT,
)


def _config() -> AnthropicConfig:
    return AnthropicConfig(api_key="sk-test-fake", model="claude-opus-4-7")


def _seed(tmp_path: Path, item: ExtractionInput, geo: ParticipantGeography) -> None:
    cache = LLMCache(root=tmp_path / "tier_p_llm")
    user_text = (
        f"PMID: {item.pmid}\n\nTitle: {item.title}\n\nAbstract:\n{item.abstract}"
    )
    cache.set("claude-opus-4-7", _SYSTEM_PROMPT, user_text, geo.model_dump_json())


def test_extract_african_majority(tmp_path: Path) -> None:
    item = ExtractionInput(
        pmid="100",
        title="Trial in East Africa",
        abstract="700 participants enrolled in Uganda and 300 in Kenya.",
    )
    expected = ParticipantGeography(
        african_participant_pct=100.0,
        non_african_participant_pct=0.0,
        countries_mentioned=["Uganda", "Kenya"],
        evidence_source="700 participants enrolled in Uganda and 300 in Kenya.",
        confidence="high",
        reasoning="All 1000 participants are in African countries.",
    )
    _seed(tmp_path, item, expected)
    extractor = TierPExtractor(cache_dir=tmp_path, config=_config())
    result = extractor.extract(item)
    assert result.african_participant_pct == 100.0
    assert result.confidence == "high"


def test_extract_no_geography_insufficient(tmp_path: Path) -> None:
    item = ExtractionInput(
        pmid="200",
        title="A double-blind RCT of drug X",
        abstract="500 participants randomised to drug X or placebo. Primary outcome was reduction in HbA1c.",
    )
    expected = ParticipantGeography(
        african_participant_pct=None,
        non_african_participant_pct=None,
        countries_mentioned=[],
        evidence_source=None,
        confidence="insufficient",
        reasoning="The abstract does not mention any country or geographic information.",
    )
    _seed(tmp_path, item, expected)
    extractor = TierPExtractor(cache_dir=tmp_path, config=_config())
    result = extractor.extract(item)
    assert result.confidence == "insufficient"
    assert result.african_participant_pct is None


def test_extract_uses_cache_no_api_call(tmp_path: Path) -> None:
    """Once cached, no API call is made — proves cache hit."""
    item = ExtractionInput(pmid="300", title="t", abstract="a")
    expected = ParticipantGeography(
        african_participant_pct=50.0,
        non_african_participant_pct=50.0,
        countries_mentioned=["Nigeria", "USA"],
        evidence_source="evidence",
        confidence="medium",
        reasoning="50/50 split.",
    )
    _seed(tmp_path, item, expected)
    extractor = TierPExtractor(cache_dir=tmp_path, config=_config())
    result1 = extractor.extract(item)
    result2 = extractor.extract(item)
    assert result1 == result2
    assert result1.african_participant_pct == 50.0


def test_extract_no_cache_attempts_live_call_with_fake_key(tmp_path: Path) -> None:
    """When cache is empty and key is fake, the SDK errors out — surfaces as
    anthropic.AuthenticationError. We don't actually want to make a live call
    in tests, but we want to confirm that *if* the cache is empty, the path
    leads to the SDK.
    """
    item = ExtractionInput(pmid="400", title="t", abstract="a")
    extractor = TierPExtractor(cache_dir=tmp_path, config=_config())
    import anthropic
    with pytest.raises((anthropic.AuthenticationError, anthropic.APIConnectionError, anthropic.APIError)):
        extractor.extract(item)
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_classify_tier_p_extractor.py -v`
Expected: 4 PASSED.

The 4th test (`test_extract_no_cache_attempts_live_call_with_fake_key`) MAY make a live HTTPS request to `api.anthropic.com` and fail with 401. That's the expected outcome — we're proving the path leads to the SDK. If the test environment blocks network entirely, the assertion still passes via `APIConnectionError`.

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/classify/llm_cache.py src/arac/classify/tier_p_extractor.py tests/test_classify_tier_p_extractor.py
git commit -m "feat(classify-tier-p): LLM extractor (Pydantic-validated, prompt-cached, disk-cached)"
```

---

### Task 4: Composite Tier-P classifier

**Files:**
- Create: `C:/Projects/arac/src/arac/classify/tier_p.py`
- Create: `C:/Projects/arac/tests/test_classify_tier_p.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_classify_tier_p.py`:

```python
"""Tier-P classifier: ResolvedMetadata + PubMedRecord → TierPResult."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.classify._anthropic_pre import AnthropicConfig
from arac.classify.llm_cache import LLMCache
from arac.classify.tier_p import (
    TierP, TierPClassifier, TierPResult,
)
from arac.classify.tier_p_extractor import (
    ExtractionInput, ParticipantGeography, TierPExtractor, _SYSTEM_PROMPT,
)
from arac.resolve.pubmed import PubMedClient, PubMedRecord
from arac.resolve.http_cache import HttpCache
from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata


def _meta_with_pmid(pmid: str) -> ResolvedMetadata:
    return ResolvedMetadata(
        trial_id=f"TEST::t0::pmid={pmid}",
        method=ResolutionMethod.AUTHOR_YEAR,
        confidence=0.8,
        pmid=pmid, nct_id=None, title="Test trial",
        first_author=None, first_affiliation_raw=None, country_list=(),
    )


def _seed_pubmed(cache_dir: Path, pmid: str, abstract: str) -> None:
    cache = HttpCache(root=cache_dir / "pubmed", ttl_seconds=3600)
    client = PubMedClient(cache_dir=cache_dir / "pubmed")
    xml = (
        f'<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        f'<PMID>{pmid}</PMID><Article><AuthorList>'
        f'<Author><LastName>X</LastName></Author></AuthorList>'
        f'<Abstract><AbstractText>{abstract}</AbstractText></Abstract>'
        f'</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(client._build_url(pmid), b"", xml.encode())


def _seed_llm(cache_dir: Path, pmid: str, title: str, abstract: str, geo: ParticipantGeography) -> None:
    cache = LLMCache(root=cache_dir / "tier_p_llm")
    user_text = f"PMID: {pmid}\n\nTitle: {title}\n\nAbstract:\n{abstract}"
    cache.set("claude-opus-4-7", _SYSTEM_PROMPT, user_text, geo.model_dump_json())


def _config() -> AnthropicConfig:
    return AnthropicConfig(api_key="sk-test-fake", model="claude-opus-4-7")


def test_african_majority(tmp_path: Path) -> None:
    abstract = "700 participants enrolled in Uganda and 300 in Kenya."
    _seed_pubmed(tmp_path, "100", abstract)
    _seed_llm(tmp_path, "100", "Test trial", abstract, ParticipantGeography(
        african_participant_pct=100.0, non_african_participant_pct=0.0,
        countries_mentioned=["Uganda", "Kenya"], evidence_source=abstract,
        confidence="high", reasoning="All 1000 in African countries.",
    ))
    classifier = TierPClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"),
        extractor=TierPExtractor(cache_dir=tmp_path, config=_config()),
    )
    result = classifier.classify(_meta_with_pmid("100"))
    assert result.tier_p is TierP.AFRICAN_MAJORITY
    assert result.african_pct == 100.0
    assert result.confidence >= 0.8


def test_not_african_majority(tmp_path: Path) -> None:
    abstract = "1000 participants from USA and Germany."
    _seed_pubmed(tmp_path, "200", abstract)
    _seed_llm(tmp_path, "200", "Test trial", abstract, ParticipantGeography(
        african_participant_pct=0.0, non_african_participant_pct=100.0,
        countries_mentioned=["USA", "Germany"], evidence_source=abstract,
        confidence="high", reasoning="No African participants.",
    ))
    classifier = TierPClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"),
        extractor=TierPExtractor(cache_dir=tmp_path, config=_config()),
    )
    result = classifier.classify(_meta_with_pmid("200"))
    assert result.tier_p is TierP.NOT_AFRICAN_MAJORITY


def test_insufficient_no_abstract(tmp_path: Path) -> None:
    """Trial has no abstract in PubMed → INSUFFICIENT."""
    cache = HttpCache(root=tmp_path / "pubmed", ttl_seconds=3600)
    client = PubMedClient(cache_dir=tmp_path / "pubmed")
    # PubMed XML with no <Abstract>
    xml = (
        '<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>'
        '<PMID>300</PMID><Article><AuthorList>'
        '<Author><LastName>X</LastName></Author></AuthorList>'
        '</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    )
    cache.set(client._build_url("300"), b"", xml.encode())
    classifier = TierPClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"),
        extractor=TierPExtractor(cache_dir=tmp_path, config=_config()),
    )
    result = classifier.classify(_meta_with_pmid("300"))
    assert result.tier_p is TierP.INSUFFICIENT_DATA
    assert result.confidence == 0.0


def test_insufficient_llm_says_insufficient(tmp_path: Path) -> None:
    """Abstract present but LLM determines geography not extractable."""
    abstract = "500 participants in a double-blind RCT of drug X."
    _seed_pubmed(tmp_path, "400", abstract)
    _seed_llm(tmp_path, "400", "Test trial", abstract, ParticipantGeography(
        african_participant_pct=None, non_african_participant_pct=None,
        countries_mentioned=[], evidence_source=None,
        confidence="insufficient", reasoning="No geography mentioned.",
    ))
    classifier = TierPClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"),
        extractor=TierPExtractor(cache_dir=tmp_path, config=_config()),
    )
    result = classifier.classify(_meta_with_pmid("400"))
    assert result.tier_p is TierP.INSUFFICIENT_DATA


def test_no_pmid_insufficient(tmp_path: Path) -> None:
    classifier = TierPClassifier(
        pubmed_client=PubMedClient(cache_dir=tmp_path / "pubmed"),
        extractor=TierPExtractor(cache_dir=tmp_path, config=_config()),
    )
    meta = ResolvedMetadata(
        trial_id="x", method=ResolutionMethod.FAILED, confidence=0.0,
        pmid=None, nct_id=None, title=None, first_author=None,
        first_affiliation_raw=None, country_list=(),
    )
    result = classifier.classify(meta)
    assert result.tier_p is TierP.INSUFFICIENT_DATA
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL on import.

- [ ] **Step 3: Implement `tier_p.py`**

```python
"""Tier-P (Participant geography) classifier — does this trial have ≥50% African
participants?

Source: PubMed efetch for the trial's abstract → LLM-based extraction →
threshold check on african_participant_pct.

Confidence levels (output):
- 0.95 — extractor returned "high" confidence with explicit percentages
- 0.80 — extractor returned "medium" confidence (counts → computed pct)
- 0.55 — extractor returned "low" confidence (country list only, estimated)
- 0.00 — INSUFFICIENT (no abstract, or extractor said "insufficient")
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arac.classify.tier_p_extractor import ExtractionInput, TierPExtractor
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import ResolvedMetadata


_THRESHOLD_PCT = 50.0


class TierP(Enum):
    AFRICAN_MAJORITY = "african_majority"
    NOT_AFRICAN_MAJORITY = "not_african_majority"
    INSUFFICIENT_DATA = "insufficient_data"


_CONFIDENCE_BY_LEVEL = {
    "high": 0.95,
    "medium": 0.80,
    "low": 0.55,
    "insufficient": 0.0,
}


@dataclass(frozen=True)
class TierPResult:
    trial_id: str
    tier_p: TierP
    confidence: float
    african_pct: Optional[float]
    countries_mentioned: tuple[str, ...]
    evidence_source: Optional[str]


class TierPClassifier:
    def __init__(
        self,
        pubmed_client: PubMedClient,
        extractor: TierPExtractor,
    ) -> None:
        self._pubmed = pubmed_client
        self._extractor = extractor

    def classify(self, meta: ResolvedMetadata) -> TierPResult:
        if not meta.pmid:
            return self._insufficient(meta.trial_id)

        record = self._pubmed.efetch(meta.pmid)
        if record is None or not record.abstract_text:
            return self._insufficient(meta.trial_id)

        item = ExtractionInput(
            pmid=record.pmid,
            title=meta.title or "",
            abstract=record.abstract_text,
        )
        geo = self._extractor.extract(item)

        if geo.confidence == "insufficient" or geo.african_participant_pct is None:
            return TierPResult(
                trial_id=meta.trial_id,
                tier_p=TierP.INSUFFICIENT_DATA,
                confidence=0.0,
                african_pct=None,
                countries_mentioned=tuple(geo.countries_mentioned),
                evidence_source=geo.evidence_source,
            )

        confidence = _CONFIDENCE_BY_LEVEL.get(geo.confidence, 0.0)
        if geo.african_participant_pct >= _THRESHOLD_PCT:
            return TierPResult(
                trial_id=meta.trial_id,
                tier_p=TierP.AFRICAN_MAJORITY,
                confidence=confidence,
                african_pct=geo.african_participant_pct,
                countries_mentioned=tuple(geo.countries_mentioned),
                evidence_source=geo.evidence_source,
            )
        return TierPResult(
            trial_id=meta.trial_id,
            tier_p=TierP.NOT_AFRICAN_MAJORITY,
            confidence=confidence,
            african_pct=geo.african_participant_pct,
            countries_mentioned=tuple(geo.countries_mentioned),
            evidence_source=geo.evidence_source,
        )

    def _insufficient(self, trial_id: str) -> TierPResult:
        return TierPResult(
            trial_id=trial_id,
            tier_p=TierP.INSUFFICIENT_DATA,
            confidence=0.0,
            african_pct=None,
            countries_mentioned=(),
            evidence_source=None,
        )
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_classify_tier_p.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Full suite + Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m pytest -v 2>&1 | tail -3
python -m sentinel scan --repo .
git add src/arac/classify/tier_p.py tests/test_classify_tier_p.py
git commit -m "feat(classify-tier-p): composite Tier-P classifier (LLM-extracted, ≥50% threshold)"
```

---

### Task 5: CLI smoke runner — Tier-P per MA

**Files:**
- Create: `C:/Projects/arac/scripts/tier_p_smoke.py`

- [ ] **Step 1: Write the script**

```python
"""Resolve every trial in one Pairwise70 MA AND run Tier-P classification.

Usage:
    ARAC_ANTHROPIC_API_KEY=sk-ant-... python scripts/tier_p_smoke.py <ma_id>

Combines Plan 2A resolver + Plan 2A.1 PubMed enrichment + Plan 2D Tier-P.
LLM responses cached to outputs/cache/resolve/tier_p_llm/. First run on a
new MA will take longer (live API calls); re-runs are cache-served.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyreadr

from arac.bridge import load_all_mas
from arac.classify._anthropic_pre import resolve_anthropic_config
from arac.classify.tier_p import TierPClassifier
from arac.classify.tier_p_extractor import TierPExtractor
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
    ap.add_argument("ma_id")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from inspect_rda import _data_dir  # type: ignore
    pairwise70_dir = _data_dir()
    sys.path.pop(0)

    try:
        config = resolve_anthropic_config()
    except RuntimeError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    cache_dir = Path("outputs/cache/resolve")
    cache_dir.mkdir(parents=True, exist_ok=True)

    mas = load_all_mas(pairwise70_dir, max_reviews=None)
    ma = next((m for m in mas if m.ma_id == args.ma_id), None)
    if ma is None:
        raise SystemExit(f"ma_id not found in Pairwise70: {args.ma_id}")

    study_strings = _load_study_strings_for_ma(args.ma_id, pairwise70_dir)
    resolver = StudyResolver(cache_dir=cache_dir)
    pubmed = PubMedClient(cache_dir=cache_dir / "pubmed")
    extractor = TierPExtractor(cache_dir=cache_dir, config=config)
    classifier = TierPClassifier(pubmed_client=pubmed, extractor=extractor)

    print(f"Tier-P for {len(ma.trials)} trials in {ma.ma_id} (model={config.model}):")
    for trial in ma.trials:
        s = study_strings.get(trial.trial_index, "<MISSING>")
        meta = resolver.resolve(trial, study_string=s)
        if meta.pmid is None:
            print(f"  [{trial.trial_index}] '{s}' -> resolve=FAILED -> tier_p=INSUFFICIENT")
            continue
        result = classifier.classify(meta)
        print(
            f"  [{trial.trial_index}] '{s}' -> "
            f"resolve={meta.method.value} (pmid={meta.pmid}) -> "
            f"tier_p={result.tier_p.value} (conf={result.confidence:.2f}, "
            f"african_pct={result.african_pct}, countries={list(result.countries_mentioned)[:3]})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke-run if API key is available**

If `ANTHROPIC_API_KEY` (or `ARAC_ANTHROPIC_API_KEY`) is set in the environment:

```bash
cd "C:/Projects/arac" && python scripts/tier_p_smoke.py CD000028_pub4_data__A1
```

Expected: prints one line per trial. Most pre-1995 trials INSUFFICIENT (Plan 2A.1 NLM gap; some abstracts may exist). Modern trials with abstracts get real LLM-extracted classifications.

If API key is NOT set: skip this step. The script will print the actionable error message from `resolve_anthropic_config()` and exit 1 — that's expected.

- [ ] **Step 3: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add scripts/tier_p_smoke.py
git commit -m "feat(classify-tier-p): CLI smoke runner — per-trial Tier-P over a Pairwise70 MA"
```

---

### Task 6: Baseline + v0.4.0 tag

**Files:**
- Modify: `C:/Projects/arac/baseline.json`

- [ ] **Step 1: Append v0.4.0 record**

```bash
cd "C:/Projects/arac" && python - <<'PY'
import json, subprocess
from datetime import datetime, timezone
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
baseline = json.loads(open("baseline.json").read())
baseline["records"]["arac-tier-p-v0.4.0"] = {
    "paper_id": "arac-tier-p-v0.4.0",
    "commit_sha": sha,
    "recorded_at": ts,
    "pooled_estimate": None, "k": None,
    "ci_lower": None, "ci_upper": None, "se": None, "tau2": None,
    "i2": None, "q": None,
    "extra": {
        "approach": "LLM-based structured extraction via Anthropic SDK messages.parse() with Pydantic ParticipantGeography schema; 50% African-participant threshold.",
        "default_model": "claude-opus-4-7",
        "model_override_env": "ARAC_TIER_P_MODEL",
        "prompt_caching": "ephemeral cache_control on stable system prompt for ~10x cost savings",
        "disk_caching": "LLMCache keyed by (model, system_hash, user_hash); 90-day TTL",
        "spec_triad_complete": "S/A/P all three classifiers shipped (Plans 2B + 2C + 2D)",
        "note": "Plan 2D ships Tier-P capability with mock-tested code paths; full Pairwise70 atlas extraction (~60K trials × Opus 4.7 ~$30 amortized with caching) deferred to dedicated batch session. IRR validation against 50-trial human gold standard is Plan 2E (requires Mahmood + PhD-cohort cohort-assembly first)."
    },
}
with open("baseline.json", "w") as f:
    json.dump(baseline, f, indent=2)
print("baseline.json updated with v0.4.0 record")
PY
```

- [ ] **Step 2: Final tests + Sentinel**

```bash
cd C:/Projects/arac && python -m pytest -v 2>&1 | tail -3
cd C:/Projects/arac && python -m sentinel scan --repo .
```

Expected: all tests PASS (~70 total: Plan 2C.1's 61 + Plan 2D's ~12-15), 0 BLOCK.

- [ ] **Step 3: Commit + tag**

```bash
cd "C:/Projects/arac"
git add baseline.json
git commit -m "chore(baseline): record Plan 2D Tier-P classifier v0.4.0"
git tag -a v0.4.0 -m "Plan 2D complete — Tier-P classifier (LLM-extracted ≥50% African); S/A/P triad shipped"
```

---

## Done criteria

- [ ] All 6 tasks committed
- [ ] `git tag` shows `v0.4.0`
- [ ] All tests PASS
- [ ] Sentinel 0 BLOCK
- [ ] `baseline.json` has 7 records (foundation, resolve, tier-s, pubmed-enrichment, tier-a, word-boundary, tier-p)
- [ ] Tier-P classifier callable via the CLI runner (live API call requires user's API key — that's expected; `resolve_anthropic_config()` surfaces a clear error if missing)
- [ ] Spec's S/A/P triad is now fully implemented
