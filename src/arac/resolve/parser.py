"""Parse Pairwise70 Study strings into structured StudyRef records.

Patterns recognised (in priority order, first match wins):
1. NCT-direct      — `NCT\\d{6,8}` anywhere in the string
2. Acronym + Year  — uppercase word ≥3 chars + 4-digit year (e.g. "HYVET 2008")
3. Acronym alone   — uppercase word ≥3 chars, no year (e.g. "SUMMIT")
4. Author + Year   — anything else with a 4-digit year (e.g. "van der Berg 2018")
5. Unknown         — no usable structure

The parser is deliberately permissive: it returns UNKNOWN rather than raising
on un-parseable strings. Downstream resolvers handle UNKNOWN by skipping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class StudyForm(Enum):
    AUTHOR_YEAR = "author_year"
    NCT_DIRECT = "nct_direct"
    ACRONYM = "acronym"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class StudyRef:
    """Structured representation of a Study string."""
    raw: str
    form: StudyForm
    author_lastname: Optional[str] = None
    acronym: Optional[str] = None
    nct_id: Optional[str] = None
    year: Optional[int] = None


_NCT_RE = re.compile(r"NCT\d{6,8}")
_YEAR_RE = re.compile(r"(19\d{2}|20\d{2})")
# Acronym = uppercase word ≥3 chars (allowing digits and hyphens), at start of string.
_ACRONYM_RE = re.compile(r"^([A-Z][A-Z0-9\-]{2,})\b")


def parse_study_string(s: str) -> StudyRef:
    raw = s
    s = s.strip()
    if not s:
        return StudyRef(raw=raw, form=StudyForm.UNKNOWN)

    # 1. NCT-direct
    nct_match = _NCT_RE.search(s)
    if nct_match:
        return StudyRef(
            raw=raw,
            form=StudyForm.NCT_DIRECT,
            nct_id=nct_match.group(0),
        )

    # 2 + 3. Acronym (with or without year)
    acronym_match = _ACRONYM_RE.match(s)
    if acronym_match:
        acronym = acronym_match.group(1)
        year_match = _YEAR_RE.search(s)
        return StudyRef(
            raw=raw,
            form=StudyForm.ACRONYM,
            acronym=acronym,
            year=int(year_match.group(0)) if year_match else None,
        )

    # 4. Author + Year — extract year, treat everything before it as lastname.
    year_match = _YEAR_RE.search(s)
    if year_match:
        year = int(year_match.group(0))
        lastname = s[: year_match.start()].strip()
        if lastname:
            return StudyRef(
                raw=raw,
                form=StudyForm.AUTHOR_YEAR,
                author_lastname=lastname,
                year=year,
            )

    # 5. Unknown
    return StudyRef(raw=raw, form=StudyForm.UNKNOWN)
