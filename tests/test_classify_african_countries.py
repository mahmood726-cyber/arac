"""African-country canonicalisation: is this country name African?"""

from __future__ import annotations

import pytest

from arac.classify.african_countries import is_african_country, AFRICAN_COUNTRIES


def test_known_african_countries() -> None:
    for c in ("Uganda", "South Africa", "Egypt", "Nigeria", "Kenya", "Morocco"):
        assert is_african_country(c), f"{c} should be African"


def test_known_non_african() -> None:
    for c in ("United States", "United Kingdom", "China", "India", "Brazil"):
        assert not is_african_country(c), f"{c} should NOT be African"


def test_case_insensitive() -> None:
    assert is_african_country("south africa")
    assert is_african_country("SOUTH AFRICA")
    assert is_african_country("South Africa")


def test_handles_known_aliases() -> None:
    # CT.gov sometimes uses 'Côte d'Ivoire' (with diacritics) or 'Ivory Coast'.
    assert is_african_country("Côte d'Ivoire") or is_african_country("Ivory Coast")
    # Tanzania may appear as 'Tanzania' or 'Tanzania, United Republic of'.
    assert is_african_country("Tanzania")
    # DRC variations.
    assert (
        is_african_country("Congo, The Democratic Republic of the")
        or is_african_country("Democratic Republic of the Congo")
        or is_african_country("DRC")
    )


def test_table_size() -> None:
    # The UN recognises 54 African states. Allow ±2 for territory edge cases.
    assert 50 <= len(AFRICAN_COUNTRIES) <= 60
