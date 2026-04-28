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
