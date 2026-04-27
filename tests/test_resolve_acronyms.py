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
