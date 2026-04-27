"""Parser: Study-string → StudyRef enum + payload."""

from __future__ import annotations

from arac.resolve.parser import (
    StudyForm,
    StudyRef,
    parse_study_string,
)


def test_parse_author_year() -> None:
    ref = parse_study_string("Smith 2010")
    assert ref.form is StudyForm.AUTHOR_YEAR
    assert ref.author_lastname == "Smith"
    assert ref.year == 2010
    assert ref.acronym is None
    assert ref.nct_id is None


def test_parse_author_year_with_initials() -> None:
    ref = parse_study_string("van der Berg 2018")
    # Multi-word lastnames preserved verbatim.
    assert ref.form is StudyForm.AUTHOR_YEAR
    assert ref.author_lastname == "van der Berg"
    assert ref.year == 2018


def test_parse_nct_direct() -> None:
    ref = parse_study_string("NCT02918409")
    assert ref.form is StudyForm.NCT_DIRECT
    assert ref.nct_id == "NCT02918409"
    assert ref.author_lastname is None


def test_parse_acronym() -> None:
    ref = parse_study_string("HYVET 2008")
    assert ref.form is StudyForm.ACRONYM
    assert ref.acronym == "HYVET"
    assert ref.year == 2008


def test_parse_acronym_no_year() -> None:
    ref = parse_study_string("SUMMIT")
    assert ref.form is StudyForm.ACRONYM
    assert ref.acronym == "SUMMIT"
    assert ref.year is None


def test_parse_unknown() -> None:
    ref = parse_study_string("???")
    assert ref.form is StudyForm.UNKNOWN
    assert ref.author_lastname is None
    assert ref.acronym is None
    assert ref.nct_id is None


def test_parse_strips_whitespace() -> None:
    ref = parse_study_string("  Smith 2010  ")
    assert ref.form is StudyForm.AUTHOR_YEAR
    assert ref.author_lastname == "Smith"
