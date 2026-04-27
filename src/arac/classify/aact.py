"""AACT query module — read-only access to countries / facilities tables.

Returns deduplicated, sorted country lists per NCT. Supports four backends:
- POSTGRES (preferred for production at scale)
- SQLITE (single-file snapshot)
- TSV_DIR (pipe-delimited bulk download — what AACT ships canonically)
- CSV_DIR (comma-delimited; for users who run a CSV export script)

For Tier-S we read `countries.txt` (or the equivalent table) filtered by
`removed='f'` so we only count active country sites. The countries.txt
aggregate is preferred over facilities.txt because facilities has many rows
per country (one per investigator site) and would need a DISTINCT.

Per lessons.md "Validate >0 rows": empty results return [] (not None / not raise).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from arac.classify._aact_path import AACTBackend, AACTLocation


@dataclass(frozen=True)
class AACTClient:
    location: AACTLocation

    def get_countries(self, nct_id: str) -> list[str]:
        """Return deduplicated, sorted active-country list for the given NCT.
        Empty list when NCT not found or has no active country rows."""
        if self.location.backend is AACTBackend.POSTGRES:
            return self._postgres_get_countries(nct_id)
        if self.location.backend is AACTBackend.SQLITE:
            return self._sqlite_get_countries(nct_id)
        if self.location.backend is AACTBackend.TSV_DIR:
            return self._tsv_get_countries(nct_id)
        if self.location.backend is AACTBackend.CSV_DIR:
            return self._csv_get_countries(nct_id)
        return []

    def _postgres_get_countries(self, nct_id: str) -> list[str]:
        import psycopg2
        conn = psycopg2.connect(self.location.dsn_or_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT name FROM countries "
                "WHERE nct_id = %s AND removed = false "
                "ORDER BY name",
                (nct_id,),
            )
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def _sqlite_get_countries(self, nct_id: str) -> list[str]:
        import sqlite3
        conn = sqlite3.connect(self.location.dsn_or_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT name FROM countries "
                "WHERE nct_id = ? AND removed IN ('f', 'false', 0) "
                "ORDER BY name",
                (nct_id,),
            )
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def _tsv_get_countries(self, nct_id: str) -> list[str]:
        """Pipe-delimited countries.txt: id|nct_id|name|removed."""
        return self._delim_get_countries(nct_id, delimiter="|", filename="countries.txt")

    def _csv_get_countries(self, nct_id: str) -> list[str]:
        """Comma-delimited countries.csv (alternate AACT export format)."""
        return self._delim_get_countries(nct_id, delimiter=",", filename="countries.csv")

    def _delim_get_countries(
        self, nct_id: str, delimiter: str, filename: str
    ) -> list[str]:
        import csv
        path = Path(self.location.dsn_or_path) / filename
        if not path.is_file():
            return []
        countries: set[str] = set()
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                if row.get("nct_id") != nct_id:
                    continue
                # AACT 'removed' values: 't' or 'f' (string). Skip removed rows.
                if (row.get("removed") or "").lower() in ("t", "true", "1"):
                    continue
                name = (row.get("name") or "").strip()
                if name:
                    countries.add(name)
        return sorted(countries)
