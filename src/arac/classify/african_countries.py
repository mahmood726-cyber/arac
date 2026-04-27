"""African-country canonicalisation. Loads `data/african_countries.yaml`
into a frozenset of all known aliases (case-insensitive).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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


# Public: canonical names only (for table-size assertions).
AFRICAN_COUNTRIES = _load_canonical_names()


def is_african_country(name: str) -> bool:
    """Case-insensitive match of a country name against the African-aliases set."""
    return name.strip().lower() in _load_aliases()
