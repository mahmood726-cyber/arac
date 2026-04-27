"""Resolve AACT connection details — env var first, then candidate paths.

Per lessons.md "Do not hardcode one drive" and "CT.gov / AACT Queries:
verify columns exist." If no working AACT is found, fail closed with an
actionable error pointing the user at where to install/download AACT.

AACT can be one of four backends:
1. A local PostgreSQL instance (env var: AACT_DSN, e.g. "postgresql://user@host/aact")
2. A SQLite snapshot file (env var: AACT_SQLITE, e.g. "C:/AACT/aact.sqlite3")
3. A directory containing pipe-delimited .txt files from the AACT bulk download
   (env var: AACT_TSV_DIR; e.g. "C:/Users/user/AACT/2026-04-12")  # sentinel:skip-line P0-hardcoded-local-path
   This is the canonical local format: 49 .txt files, delimiter='|'.
4. A directory containing comma-delimited .csv files from the AACT CSV export
   (env var: AACT_CSV_DIR; for users who ran the CSV export variant)

Resolution order:
1. AACT_DSN env var  -> POSTGRES
2. AACT_SQLITE env var -> SQLITE
3. AACT_TSV_DIR env var -> TSV_DIR
4. AACT_CSV_DIR env var -> CSV_DIR
5. Auto-discover under C:/Users/user/AACT/ (most recent YYYY-MM-DD subdir) -> TSV_DIR  # sentinel:skip-line P0-hardcoded-local-path
6. Auto-discover under D:/AACT-storage/AACT/ (most recent YYYY-MM-DD subdir) -> TSV_DIR
7. Fail closed with actionable error

AACT bulk downloads: https://aact.ctti-clinicaltrials.org/snapshots
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class AACTBackend(Enum):
    POSTGRES = "postgres"
    SQLITE = "sqlite"
    TSV_DIR = "tsv_dir"   # pipe-delimited .txt files (AACT canonical local format)
    CSV_DIR = "csv_dir"   # comma-delimited .csv files (AACT CSV export variant)


@dataclass(frozen=True)
class AACTLocation:
    backend: AACTBackend
    dsn_or_path: str  # DSN string for postgres; file/dir path for sqlite/tsv/csv


# Candidate parent directories for auto-discovery of YYYY-MM-DD snapshots.
_CANDIDATE_PARENTS = [
    "C:/Users/user/AACT",         # sentinel:skip-line P0-hardcoded-local-path
    "D:/AACT-storage/AACT",       # sentinel:skip-line P0-hardcoded-local-path
]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _latest_dated_subdir(parent: str) -> Optional[Path]:
    """Return the most-recent YYYY-MM-DD subdirectory under *parent*, or None."""
    p = Path(parent)
    if not p.is_dir():
        return None
    dated = sorted(
        (d for d in p.iterdir() if d.is_dir() and _DATE_RE.match(d.name)),
        key=lambda d: d.name,
        reverse=True,
    )
    return dated[0] if dated else None


def resolve_aact_location() -> AACTLocation:
    """Resolve AACT location using env vars, then candidate path auto-discovery.

    Raises RuntimeError with an actionable message if AACT is not found.
    """
    # 1. Postgres DSN
    dsn = os.environ.get("AACT_DSN")
    if dsn:
        return AACTLocation(backend=AACTBackend.POSTGRES, dsn_or_path=dsn)

    # 2. SQLite snapshot file
    sqlite_env = os.environ.get("AACT_SQLITE")
    if sqlite_env:
        p = Path(sqlite_env)
        if not p.is_file():
            raise RuntimeError(
                f"AACT_SQLITE={sqlite_env!r} is set but file does not exist."
            )
        return AACTLocation(backend=AACTBackend.SQLITE, dsn_or_path=str(p))

    # 3. TSV directory (pipe-delimited .txt files — canonical AACT local format)
    tsv_dir_env = os.environ.get("AACT_TSV_DIR")
    if tsv_dir_env:
        p = Path(tsv_dir_env)
        if not p.is_dir():
            raise RuntimeError(
                f"AACT_TSV_DIR={tsv_dir_env!r} is set but directory does not exist."
            )
        return AACTLocation(backend=AACTBackend.TSV_DIR, dsn_or_path=str(p))

    # 4. CSV directory (comma-delimited .csv files)
    csv_dir_env = os.environ.get("AACT_CSV_DIR")
    if csv_dir_env:
        p = Path(csv_dir_env)
        if not p.is_dir():
            raise RuntimeError(
                f"AACT_CSV_DIR={csv_dir_env!r} is set but directory does not exist."
            )
        return AACTLocation(backend=AACTBackend.CSV_DIR, dsn_or_path=str(p))

    # 5-6. Auto-discover under candidate parent directories.
    for parent in _CANDIDATE_PARENTS:
        subdir = _latest_dated_subdir(parent)
        if subdir is not None:
            return AACTLocation(backend=AACTBackend.TSV_DIR, dsn_or_path=str(subdir))

    raise RuntimeError(
        "AACT not found. Set one of:\n"
        "  AACT_DSN      — postgres DSN (e.g. postgresql://user@localhost/aact)\n"
        "  AACT_SQLITE   — path to a SQLite snapshot file\n"
        "  AACT_TSV_DIR  — path to a directory of pipe-delimited .txt files\n"
        "  AACT_CSV_DIR  — path to a directory of comma-delimited .csv files\n"
        "Or place an AACT snapshot under C:/Users/user/AACT/YYYY-MM-DD/ "  # sentinel:skip-line P0-hardcoded-local-path
        "or D:/AACT-storage/AACT/YYYY-MM-DD/ (auto-discovered).\n"
        "AACT bulk downloads: https://aact.ctti-clinicaltrials.org/snapshots"
    )
