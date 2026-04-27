# sentinel:skip-file — local-path default is a research fixture locator, not
# shipping code. The canonical override is the PAIRWISE70_DIR env var.
"""Dump the schema of every dataframe inside one or more Pairwise70 .rda files.

Usage:
    python scripts/inspect_rda.py CD000028_pub4_data.rda [more.rda ...]

If a bare filename (no directory) is supplied the script resolves it relative
to the Pairwise70 data directory, determined by:
    1. The PAIRWISE70_DIR environment variable (override for non-default drives)
    2. Candidate-root discovery: C:/Projects/Pairwise70/data or D:/Projects/Pairwise70/data
    3. Fails closed with an actionable error if neither candidate is found.

Prints (rda_name, object_name, rows, columns) per dataframe.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pyreadr

# Candidate roots in priority order (C: then D:) per lessons.md
_CANDIDATE_ROOTS = [
    "C:/Projects/Pairwise70/data",
    "D:/Projects/Pairwise70/data",
]


def _data_dir() -> Path:
    env_override = os.environ.get("PAIRWISE70_DIR")
    if env_override:
        return Path(env_override)
    for candidate in _CANDIDATE_ROOTS:
        p = Path(candidate)
        if p.is_dir():
            return p
    raise RuntimeError(
        "Pairwise70 data directory not found. Set PAIRWISE70_DIR env var "
        f"or place data at one of: {_CANDIDATE_ROOTS}"
    )


def main(paths: list[str]) -> int:
    base = _data_dir()
    for raw in paths:
        p = Path(raw)
        if not p.is_absolute():
            p = base / raw
        if not p.is_file():
            print(f"MISSING: {p}", file=sys.stderr)
            continue
        bundle = pyreadr.read_r(str(p))
        for obj_name, df in bundle.items():
            print(
                f"{p.name} :: {obj_name} :: rows={len(df)} :: cols={list(df.columns)}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["CD000028_pub4_data.rda"]))
