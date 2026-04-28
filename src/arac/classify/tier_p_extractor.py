"""LLM-based extraction of participant geography from trial abstracts.

Uses Anthropic's structured tool-use pattern with a Pydantic schema for reliable
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

        # Use tool_use with the Pydantic JSON schema for structured output.
        # This is the messages.parse() equivalent for SDK versions that expose
        # structured outputs via tool_choice={"type": "tool"} forcing.
        tool_schema = ParticipantGeography.model_json_schema()
        response = client.messages.create(
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
            tools=[
                {
                    "name": "extract_participant_geography",
                    "description": "Extract participant geography data from a clinical trial abstract.",
                    "input_schema": tool_schema,
                }
            ],
            tool_choice={"type": "tool", "name": "extract_participant_geography"},
        )
        # Extract the tool_use block from the response
        tool_block = next(
            b for b in response.content if b.type == "tool_use"
        )
        result = ParticipantGeography.model_validate(tool_block.input)
        self._cache.set(self._config.model, _SYSTEM_PROMPT, user_text, result.model_dump_json())
        return result
