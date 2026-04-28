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
    """Live validation -- only runs if ANTHROPIC_API_KEY is actually set in env.
    Skipped on machines without API access (CI, dev machines without the key).
    """
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ARAC_ANTHROPIC_API_KEY")):
        pytest.skip("No Anthropic API key in env; live validation skipped")
    assert validate_live() is True
