"""African-country canonicalisation. Loads `data/african_countries.yaml`
into a frozenset of all known aliases (case-insensitive), and a compiled
word-boundary regex for affiliation scanning.

Plan 2C.1 fix: switched from substring matching (e.g. `alias in text`) to
word-boundary regex matching (`re.search(rf'\\b{alias}\\b', text, re.I)`).
This eliminates false positives where alias 'car' (Central African Republic)
matched inside 'Caribbean' / 'cardiology' / 'cardiovascular'.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml


_YAML_PATH = Path(__file__).resolve().parents[3] / "data" / "african_countries.yaml"


@lru_cache(maxsize=1)
def _load_aliases() -> frozenset[str]:
    if not _YAML_PATH.is_file():
        raise RuntimeError(f"african_countries YAML missing: {_YAML_PATH}")
    raw = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))
    out: set[str] = set()
    for canonical, aliases in raw.items():
        out.add(canonical.lower().strip())
        for a in aliases:
            out.add(str(a).lower().strip())
    return frozenset(out)


@lru_cache(maxsize=1)
def _load_canonical_names() -> frozenset[str]:
    if not _YAML_PATH.is_file():
        raise RuntimeError(f"african_countries YAML missing: {_YAML_PATH}")
    raw = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))
    return frozenset(raw.keys())


@lru_cache(maxsize=1)
def _build_combined_regex() -> re.Pattern[str]:
    """Compile a single regex matching any African-country alias at word
    boundaries. Aliases are sorted longest-first so 'South Africa' wins over
    a hypothetical 'south'-suffix alias."""
    aliases = sorted(_load_aliases(), key=len, reverse=True)
    # re.escape each alias to handle apostrophes (Cote d'Ivoire), hyphens,
    # and spaces. Use \b boundaries on either side.
    escaped = [re.escape(a) for a in aliases]
    pattern = r"\b(?:" + "|".join(escaped) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


# Public: canonical names only (for table-size assertions).
AFRICAN_COUNTRIES = _load_canonical_names()


def is_african_country(name: str) -> bool:
    """True if `name` is an African country (case-insensitive, word-boundary).

    Used for single-token checks. For full affiliation-string scanning, prefer
    `scan_for_african_country` which returns the matched alias.
    """
    if not name:
        return False
    return bool(_build_combined_regex().fullmatch(name.strip()))


def scan_for_african_country(text: str) -> Optional[str]:
    """Scan a freeform affiliation string for the first word-boundary match
    against any African-country alias. Returns the matched alias (lowercase,
    as it appears in the alias table), or None.

    This is the production matcher for tier_s and tier_a.
    """
    if not text:
        return None
    m = _build_combined_regex().search(text)
    if m is None:
        return None
    return m.group(0).lower()
