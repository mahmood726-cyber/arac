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


def test_substring_false_positives_rejected() -> None:
    """Aliases must word-boundary-match, not substring-match.

    Plan 2C smoke discovered HYVET classified as african_led because alias 'car'
    (Central African Republic abbreviation) matched inside 'Caribbean' /
    'cardiology' / 'cardiovascular'. These should now reject.
    """
    # All these strings contain alias substrings but should NOT match an
    # African country at the word-boundary level.
    rejecting = [
        "Caribbean Cardiovascular Health Initiative, Bridgetown, Barbados",
        "Department of Cardiology, Cleveland Clinic, OH, USA",
        "Cardiovascular Research Centre, University of Glasgow, UK",
        "Carbon Capture and Storage Group, MIT, MA, USA",
        # 'CHAD' could appear in non-African contexts
        "Chadwick Library, University of Liverpool, UK",
        # 'NIGER' could appear inside other words
        "Negotiated agreement, Geneva, Switzerland",  # avoid false-positives on 'NIGER' substring
        # 'BENIN' inside 'beni' / 'beneath' etc.
        "Beneath the surface lab, ETH Zurich, Switzerland",
        # Single-word matches that should still REJECT
        "United States of America",
        "United Kingdom",
        "Stanford, California, USA",
    ]
    for s in rejecting:
        for token in s.split():
            assert not is_african_country(token), (
                f"Token {token!r} from {s!r} should NOT be classified African"
            )
        # Also test the full string — none of these should contain a
        # word-boundary match for any African country alias.
        # (We test the full-string scan via tier_s/tier_a in their own tests;
        # here we only assert individual tokens don't match.)


def test_real_country_names_still_match() -> None:
    """Sanity: legitimate African country names continue to match."""
    matching = [
        "Uganda", "South Africa", "Nigeria", "Kenya", "Egypt", "Morocco",
        "Tanzania", "Ghana", "Senegal", "Ethiopia",
    ]
    for c in matching:
        assert is_african_country(c), f"{c!r} should still match"


def test_country_inside_full_affiliation_string() -> None:
    """A full affiliation string containing an African country name should
    word-boundary-match. This is the production usage pattern (tier_s /
    tier_a scan a freeform affiliation string)."""
    from arac.classify.african_countries import scan_for_african_country

    cases_match = [
        ("Department of Medicine, Makerere University, Kampala, Uganda.", "uganda"),
        ("BHF Glasgow Cardiovascular Research Centre, Glasgow, Scotland.", None),  # no match
        ("Caribbean Cardiology Centre, Bridgetown, Barbados.", None),  # no match (false-positive guard)
        ("University of Cape Town, Cape Town, South Africa.", "south africa"),
    ]
    for affiliation, expected in cases_match:
        result = scan_for_african_country(affiliation)
        if expected is None:
            assert result is None, (
                f"Expected no match in {affiliation!r}; got {result!r}"
            )
        else:
            assert result is not None, f"Expected match {expected!r} in {affiliation!r}; got None"
            assert result.lower() == expected, (
                f"Expected match {expected!r} in {affiliation!r}; got {result!r}"
            )
