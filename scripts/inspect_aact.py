"""Dump the schema of AACT's studies, facilities, and countries tables
(or TSV/CSV equivalents).

Usage:
    python scripts/inspect_aact.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from arac.classify._aact_path import AACTBackend, resolve_aact_location


def _tsv_columns(root: Path, table: str) -> list[str]:
    """Read the header line of a pipe-delimited .txt file and return column names."""
    p = root / f"{table}.txt"
    if not p.is_file():
        return []
    with p.open(encoding="utf-8", errors="replace") as f:
        header = f.readline().strip()
    return header.split("|")


def _csv_columns(root: Path, table: str) -> list[str]:
    """Read the header line of a comma-delimited .csv file and return column names."""
    p = root / f"{table}.csv"
    if not p.is_file():
        return []
    with p.open(encoding="utf-8", errors="replace") as f:
        header = f.readline().strip()
    return header.split(",")


def main() -> int:
    try:
        loc = resolve_aact_location()
    except RuntimeError as e:
        print(f"PRE-FLIGHT FAIL: {e}", file=sys.stderr)
        return 1

    print(f"AACT backend : {loc.backend.value}")
    print(f"AACT location: {loc.dsn_or_path}")
    print()

    if loc.backend is AACTBackend.POSTGRES:
        try:
            import psycopg2
        except ImportError:
            print("psycopg2 not installed; re-run after `pip install psycopg2-binary`")
            return 1
        conn = psycopg2.connect(loc.dsn_or_path)
        cur = conn.cursor()
        for table in ("studies", "facilities", "countries"):
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = %s ORDER BY ordinal_position",
                (table,),
            )
            cols = cur.fetchall()
            if not cols:
                print(f"WARN: table '{table}' has no columns (or doesn't exist)")
                continue
            print(f"--- {table} ({len(cols)} columns) ---")
            for c, t in cols:
                print(f"  {c}: {t}")
        cur.close()
        conn.close()

    elif loc.backend is AACTBackend.SQLITE:
        import sqlite3
        conn = sqlite3.connect(loc.dsn_or_path)
        cur = conn.cursor()
        for table in ("studies", "facilities", "countries"):
            cur.execute(f"PRAGMA table_info({table})")
            cols = cur.fetchall()
            if not cols:
                print(f"WARN: table '{table}' has no columns (or doesn't exist)")
                continue
            print(f"--- {table} ({len(cols)} columns) ---")
            for row in cols:
                print(f"  {row[1]}: {row[2]}")
        conn.close()

    elif loc.backend is AACTBackend.TSV_DIR:
        tsv_root = Path(loc.dsn_or_path)
        for table in ("studies", "facilities", "countries"):
            cols = _tsv_columns(tsv_root, table)
            if not cols:
                print(f"WARN: {tsv_root / (table + '.txt')} not present or empty")
                continue
            print(f"--- {table} ({len(cols)} columns) ---")
            for c in cols:
                print(f"  {c}")
            print()

    else:  # CSV_DIR
        csv_root = Path(loc.dsn_or_path)
        for table in ("studies", "facilities", "countries"):
            cols = _csv_columns(csv_root, table)
            if not cols:
                print(f"WARN: {csv_root / (table + '.csv')} not present or empty")
                continue
            print(f"--- {table} ({len(cols)} columns) ---")
            for c in cols:
                print(f"  {c}")
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
