"""Curated acronym -> trial-identifier lookup table.

Source data lives in `data/acronyms.yaml` at the repo root. The table is small
(seed ~10 entries; expected to grow to ~200 as Pairwise70's 19% acronym tail is
processed). Each entry MUST have either a PMID or an NCT (or both), plus a
human-readable source attribution explaining where the identifier was verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml


_ACRONYMS_YAML = Path(__file__).resolve().parents[3] / "data" / "acronyms.yaml"


@dataclass(frozen=True)
class AcronymEntry:
    acronym: str
    pmid: Optional[str]
    nct_id: Optional[str]
    full_name: Optional[str]
    source: str


@lru_cache(maxsize=1)
def load_acronyms() -> dict[str, AcronymEntry]:
    """Load and parse the acronyms YAML. Cached for the process lifetime."""
    if not _ACRONYMS_YAML.is_file():
        raise RuntimeError(f"acronyms YAML missing: {_ACRONYMS_YAML}")
    raw = yaml.safe_load(_ACRONYMS_YAML.read_text(encoding="utf-8"))
    table: dict[str, AcronymEntry] = {}
    for key, val in raw.items():
        table[key.upper()] = AcronymEntry(
            acronym=key.upper(),
            pmid=str(val["pmid"]) if val.get("pmid") else None,
            nct_id=val.get("nct_id"),
            full_name=val.get("full_name"),
            source=val["source"],
        )
    return table


def lookup_acronym(acronym: str) -> Optional[AcronymEntry]:
    """Return the AcronymEntry for `acronym` (case-insensitive), or None."""
    return load_acronyms().get(acronym.upper())
