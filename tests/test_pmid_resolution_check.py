"""Tests for scripts/pmid_resolution_check.py — ARAC v0.1.2 R9 mitigation.

All tests use synthetic in-memory inputs; no real abstracts_cache.json or
live PubMed API calls are made.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the scripts directory is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from pmid_resolution_check import (
    classify_trial,
    parse_study_string,
    _extract_title_and_year_from_text,
    _extract_first_author_surname_from_text,
)


# ---------------------------------------------------------------------------
# Test 1: parse_study_string — "Sagara 2018 (Bougoula, Mali)"
# ---------------------------------------------------------------------------

def test_parse_study_string_sagara_2018():
    """'Sagara 2018 (Bougoula, Mali)' -> ('Sagara', 2018)."""
    surname, year = parse_study_string("Sagara 2018 (Bougoula, Mali)")
    assert surname == "Sagara"
    assert year == 2018


# ---------------------------------------------------------------------------
# Test 2: parse_study_string — compound "de Thurah 2018"
# ---------------------------------------------------------------------------

def test_parse_study_string_de_thurah_2018():
    """'de Thurah 2018' -> ('de Thurah', 2018).

    The regex captures the full compound lowercase prefix + capitalised word.
    The last part ('Thurah') is used as fallback in surname matching.
    """
    surname, year = parse_study_string("de Thurah 2018")
    # Regex choice documented: returns full compound "de Thurah"
    assert year == 2018
    assert "Thurah" in surname  # compound may include "de" prefix


# ---------------------------------------------------------------------------
# Test 3: parse_study_string — "De La Roque 2011"
# ---------------------------------------------------------------------------

def test_parse_study_string_de_la_roque_2011():
    """'De La Roque 2011' -> compound surname containing 'Roque', year 2011."""
    surname, year = parse_study_string("De La Roque 2011")
    assert year == 2011
    assert "Roque" in surname


# ---------------------------------------------------------------------------
# Test 4: classification — match
# ---------------------------------------------------------------------------

def test_classification_match():
    """Parsed surname IS in PubMed title and year matches -> 'match'."""
    classification, explanation = classify_trial(
        parsed_surname="Kayentao",
        parsed_year=2012,
        pubmed_title=(
            "Pyronaridine-artesunate granules versus artemether-lumefantrine "
            "crushed tablets in children: Kayentao et al."
        ),
        pubmed_first_author="Kayentao",
        pubmed_year=2012,
    )
    assert classification == "match"


# ---------------------------------------------------------------------------
# Test 5: classification — surname_mismatch (the R9 Sagara case)
# ---------------------------------------------------------------------------

def test_classification_surname_mismatch():
    """Sagara parsed but PubMed title is about panniculitis -> 'surname_mismatch'.

    This replicates the exact R9 defect: PMID 30587844 is a Japanese case-report
    on panniculitis after peptide vaccine therapy, not the Sagara malaria trial.
    The PubMed first-author is 'Uchida', not 'Sagara'.
    """
    classification, explanation = classify_trial(
        parsed_surname="Sagara",
        parsed_year=2018,
        pubmed_title=(
            "Development of Lobular Panniculitis Long After Completing "
            "the Personalized Peptide Vaccine Therapy"
        ),
        pubmed_first_author="Uchida",
        pubmed_year=2018,
    )
    assert classification == "surname_mismatch"
    assert "Sagara" in explanation


# ---------------------------------------------------------------------------
# Test 6: classification — year_mismatch (same surname, year off by 2)
# ---------------------------------------------------------------------------

def test_classification_year_off_by_2():
    """Surname matches but year is off by 2 -> 'year_mismatch'.

    A year difference of exactly 1 is tolerated (online-first grace).
    A difference of 2 must be flagged.
    """
    classification, explanation = classify_trial(
        parsed_surname="Rueangweerayut",
        parsed_year=2012,
        pubmed_title=(
            "Pyronaridine-artesunate versus mefloquine plus artesunate: "
            "Rueangweerayut et al."
        ),
        pubmed_first_author="Rueangweerayut",
        pubmed_year=2010,  # |2012 - 2010| = 2 > 1 -> mismatch
    )
    assert classification == "year_mismatch"


# ---------------------------------------------------------------------------
# Test 7: classification — no_pubmed_data
# ---------------------------------------------------------------------------

def test_no_pubmed_data():
    """PMID not in cache and live fetch disabled -> 'no_pubmed_data'."""
    classification, explanation = classify_trial(
        parsed_surname="Smith",
        parsed_year=2002,
        pubmed_title=None,
        pubmed_first_author=None,
        pubmed_year=None,
    )
    assert classification == "no_pubmed_data"


# ---------------------------------------------------------------------------
# Test 8: classification — both_mismatch
# ---------------------------------------------------------------------------

def test_classification_both_mismatch():
    """Surname not found AND year off by 2 -> 'both_mismatch'."""
    classification, explanation = classify_trial(
        parsed_surname="Ringwald",
        parsed_year=1998,
        pubmed_title="A totally unrelated paper on tropical plant biology",
        pubmed_first_author="Johnson",
        pubmed_year=2005,
    )
    assert classification == "both_mismatch"


# ---------------------------------------------------------------------------
# Test 9: classification — year off by exactly 1 is tolerated (boundary)
# ---------------------------------------------------------------------------

def test_classification_year_off_by_1_is_match():
    """Online-first publication: year off by exactly 1 -> still 'match'."""
    classification, _ = classify_trial(
        parsed_surname="Goldberg",
        parsed_year=2013,
        pubmed_title="Epidemiology of Fusobacterium bacteraemia: Goldberg report",
        pubmed_first_author="Goldberg",
        pubmed_year=2012,  # |2013 - 2012| = 1 -> within grace window
    )
    assert classification == "match"


# ---------------------------------------------------------------------------
# Test 10: parse_study_string — parse_failed on garbage input
# ---------------------------------------------------------------------------

def test_parse_study_string_parse_failed():
    """Non-matching string -> (None, None); classify returns 'parse_failed'."""
    surname, year = parse_study_string("no author info here")
    assert surname is None
    assert year is None
    classification, _ = classify_trial(
        parsed_surname=None,
        parsed_year=None,
        pubmed_title="Some title",
        pubmed_first_author="Author",
        pubmed_year=2010,
    )
    assert classification == "parse_failed"


# ---------------------------------------------------------------------------
# Test 11: _extract_title_and_year_from_text — raw PubMed format
# ---------------------------------------------------------------------------

_SAMPLE_PUBMED_TEXT = """\
1. Malar J. 2012 Oct 31;11:364. doi: 10.1186/1475-2875-11-364.

Pyronaridine-artesunate granules versus artemether-lumefantrine crushed tablets \
in children with Plasmodium falciparum malaria: a randomized controlled trial.

Kayentao K(1), Doumbo OK, Pénali LK.
"""


def test_extract_title_and_year_from_text():
    """Title and year are correctly parsed from a raw PubMed text record."""
    title, year = _extract_title_and_year_from_text(_SAMPLE_PUBMED_TEXT)
    assert year == 2012
    assert title is not None
    assert "Pyronaridine" in title or "Kayentao" in title or "malaria" in title.lower()


# ---------------------------------------------------------------------------
# Test 12: _extract_first_author_surname_from_text
# ---------------------------------------------------------------------------

def test_extract_first_author_surname_from_text():
    """First author 'Kayentao' extracted from the synthetic PubMed record."""
    surname = _extract_first_author_surname_from_text(_SAMPLE_PUBMED_TEXT)
    assert surname is not None
    assert "Kayentao" in surname
