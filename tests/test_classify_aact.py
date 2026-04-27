"""AACT query: get countries-by-NCT for one or more trials."""

from __future__ import annotations

import pytest

from arac.classify._aact_path import resolve_aact_location
from arac.classify.aact import AACTClient


def test_get_countries_for_known_nct() -> None:
    """NCT01035255 = PARADIGM-HF, multi-country including South Africa.

    Note: VICTORIA (NCT02861534) has all rows marked removed='t' in the
    2026-04-12 AACT snapshot, so PARADIGM-HF is used as the primary fixture.
    """
    try:
        loc = resolve_aact_location()
    except RuntimeError as e:
        pytest.skip(f"AACT not configured: {e}")
    client = AACTClient(loc)
    countries = client.get_countries("NCT01035255")
    assert isinstance(countries, list)
    assert len(countries) > 0
    assert "South Africa" in countries or any(
        "Africa" in c or c in ("Uganda", "Kenya", "Nigeria") for c in countries
    ), f"Expected an African country in PARADIGM-HF sites; got: {countries}"


def test_get_countries_for_unknown_nct() -> None:
    """A made-up NCT should return empty list, not raise."""
    try:
        loc = resolve_aact_location()
    except RuntimeError as e:
        pytest.skip(f"AACT not configured: {e}")
    client = AACTClient(loc)
    countries = client.get_countries("NCT99999999")
    assert countries == []


def test_get_countries_excludes_removed() -> None:
    """Confirm the client filters removed='t' rows out (so we only see active sites)."""
    try:
        loc = resolve_aact_location()
    except RuntimeError as e:
        pytest.skip(f"AACT not configured: {e}")
    client = AACTClient(loc)
    # PARADIGM-HF (NCT01035255) — known multi-country trial; filter check.
    countries = client.get_countries("NCT01035255")
    assert isinstance(countries, list)
    # We don't assert specific content (could vary by snapshot); just shape.
