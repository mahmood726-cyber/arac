"""Pre-flight: AACT is reachable AND has the tables/columns we need for
Plan 2B's Tier-S classifier.

Primary path: countries.txt (id|nct_id|name|removed) — AACT's per-trial
country aggregate view. Simpler than joining facilities; filter removed='f'.

Fallback check: facilities.txt must also have nct_id + country so the
facilities-based fallback path in aact.py works if countries is unavailable.

If this test FAILS (not SKIPs), Plan 2B's Tier-S classifier cannot proceed.
STOP and escalate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.classify._aact_path import AACTBackend, resolve_aact_location


# Columns required in each table by the Tier-S classifier.
REQUIRED_COUNTRIES_COLS = {"nct_id", "name", "removed"}
REQUIRED_FACILITIES_COLS = {"nct_id", "country"}
REQUIRED_STUDIES_COLS = {"nct_id"}


def _columns_for_table(loc, table: str) -> set[str]:
    """Return the set of column names present in *table* for the given backend."""
    if loc.backend is AACTBackend.POSTGRES:
        import psycopg2
        conn = psycopg2.connect(loc.dsn_or_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s",
                (table,),
            )
            return {row[0] for row in cur.fetchall()}
        finally:
            conn.close()

    if loc.backend is AACTBackend.SQLITE:
        import sqlite3
        conn = sqlite3.connect(loc.dsn_or_path)
        try:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table})")
            return {row[1] for row in cur.fetchall()}
        finally:
            conn.close()

    if loc.backend is AACTBackend.TSV_DIR:
        p = Path(loc.dsn_or_path) / f"{table}.txt"
        if not p.is_file():
            return set()
        with p.open(encoding="utf-8", errors="replace") as f:
            header = f.readline().strip()
        return set(header.split("|"))

    if loc.backend is AACTBackend.CSV_DIR:
        p = Path(loc.dsn_or_path) / f"{table}.csv"
        if not p.is_file():
            return set()
        with p.open(encoding="utf-8", errors="replace") as f:
            header = f.readline().strip()
        return set(header.split(","))

    return set()


def test_aact_reachable_and_schema_valid() -> None:
    """AACT resolves AND countries/facilities/studies have required columns."""
    try:
        loc = resolve_aact_location()
    except RuntimeError as e:
        pytest.skip(f"AACT not configured (test environment): {e}")

    # --- countries table (primary Tier-S source) ---
    countries_cols = _columns_for_table(loc, "countries")
    missing_countries = REQUIRED_COUNTRIES_COLS - countries_cols
    assert not missing_countries, (
        f"AACT countries table missing columns: {missing_countries}. "
        f"Backend={loc.backend.value}, location={loc.dsn_or_path}. "
        f"Found columns: {sorted(countries_cols)}"
    )

    # --- facilities table (fallback source) ---
    facilities_cols = _columns_for_table(loc, "facilities")
    missing_fac = REQUIRED_FACILITIES_COLS - facilities_cols
    assert not missing_fac, (
        f"AACT facilities table missing columns: {missing_fac}. "
        f"Backend={loc.backend.value}, location={loc.dsn_or_path}. "
        f"Found columns: {sorted(facilities_cols)}"
    )

    # --- studies table ---
    studies_cols = _columns_for_table(loc, "studies")
    missing_stu = REQUIRED_STUDIES_COLS - studies_cols
    assert not missing_stu, (
        f"AACT studies table missing columns: {missing_stu}. "
        f"Backend={loc.backend.value}, location={loc.dsn_or_path}"
    )
