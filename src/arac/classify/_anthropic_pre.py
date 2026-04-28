"""Pre-flight gate for Anthropic API access.

Plan 2D's Tier-P classifier requires the Anthropic API. The pre-flight checks:
1. ANTHROPIC_API_KEY env var is set (or ARAC_ANTHROPIC_API_KEY for project-scoped)
2. Resolved model name from ARAC_TIER_P_MODEL env var (default: claude-opus-4-7)
3. Optionally -- if `live=True` -- issue a 1-token validation call to confirm the
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
