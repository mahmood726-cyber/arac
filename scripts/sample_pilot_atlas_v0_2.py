# sentinel:skip-file — local-path defaults are research fixture locators (Pairwise70
# data dir), not shipping code. The canonical override is the PAIRWISE70_DIR env var.
"""Deterministic MA-level sampler for ARAC v0.2 pilot atlas.

Pre-registration spec: docs/superpowers/specs/2026-05-06-v0.2-pilot-atlas.md

Usage:
    cd <arac repo root>
    python scripts/sample_pilot_atlas_v0_2.py

Output: data/v0.2/sample_list_pilot.json

Discipline:
- Enriched stratum: census of all 45 eligible Africa-endemic-disease MAs (k>=3).
- Random stratum: 55 MAs drawn with seed=42 from non-enriched eligible pool.
- Total: 100 MAs.
- Idempotent: if sample_list_pilot.json already exists, STOP.
- Deterministic: two runs produce identical JSON (modulo generated_at).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyreadr

# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# ---------------------------------------------------------------------------
# Spec-locked constants (DO NOT CHANGE)
# ---------------------------------------------------------------------------
_SPEC_VERSION = "v0.2"
_SPEC_PATH = "docs/superpowers/specs/2026-05-06-v0.2-pilot-atlas.md"
_SAMPLING_SEED = 42
_N_RANDOM = 55
_N_TOTAL = 100  # 45 enriched (census) + 55 random

# ---------------------------------------------------------------------------
# Enrichment keywords (spec §3.2)
# ---------------------------------------------------------------------------
_ENRICHMENT_KEYWORDS: list[str] = [
    # Country / region names
    "Uganda", "Kenya", "South Africa", "Nigeria", "Tanzania", "Ghana",
    "Malawi", "Ethiopia", "Zimbabwe", "Zambia", "Mozambique", "Rwanda",
    "Cameroon", "Senegal", "Mali", "Gambia", "Burkina Faso", "Botswana",
    "Cote d Ivoire", "Democratic Republic", "Sudan",
    # Disease keywords
    "malaria", "HIV", "AIDS", "tuberculosis", "bednet",
    "trypanosomiasis", "onchocerciasis", "leishmaniasis", "schistosomiasis",
    "helminth", "sleeping sickness", "yellow fever", "cholera",
]

_ENRICHMENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    (kw, re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE))
    for kw in _ENRICHMENT_KEYWORDS
]

# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
_OUT_DIR = _REPO_ROOT / "data" / "v0.2"
_OUT_JSON = _OUT_DIR / "sample_list_pilot.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    """Discover Pairwise70 data directory (env var then candidate fallback)."""
    env_override = os.environ.get("PAIRWISE70_DIR")
    if env_override:
        p = Path(env_override)
        if not p.is_dir():
            raise SystemExit(
                f"PAIRWISE70_DIR={env_override!r} is set but is not a directory."
            )
        return p
    for candidate in [
        "C:/Projects/Pairwise70/data",  # sentinel:skip-line P0-hardcoded-local-path
        "D:/Projects/Pairwise70/data",  # sentinel:skip-line P0-hardcoded-local-path
    ]:
        p = Path(candidate)
        if p.is_dir():
            return p
    raise SystemExit(
        "Pairwise70 data directory not found. Set PAIRWISE70_DIR env var "
        "or place data at C:/Projects/Pairwise70/data or D:/Projects/Pairwise70/data."
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _matched_keyword(search_text: str) -> str | None:
    """Return the first matching keyword, or None."""
    for kw, pat in _ENRICHMENT_PATTERNS:
        if pat.search(search_text):
            return kw
    return None


def _scan_pairwise70(pairwise70_dir: Path) -> tuple[list[dict], list[dict]]:
    """Scan all 595 .rda files.

    Returns (enriched_mas, random_mas) — two flat lists of dicts with keys:
        ma_id, rda_filename, k_total, matched_keyword | None

    Eligibility: k_total >= 3 (INVISIBILITY_THRESHOLD_K from spec).
    Enrichment: any keyword match in Study strings OR Analysis.name field.
    """
    enriched_mas: list[dict] = []
    random_mas: list[dict] = []

    rda_files = sorted(pairwise70_dir.glob("*.rda"))
    print(f"Scanning {len(rda_files)} .rda files for eligible MAs...", flush=True)

    for rda_path in rda_files:
        try:
            bundle = pyreadr.read_r(str(rda_path))
        except Exception as exc:
            print(f"  WARN: could not read {rda_path.name}: {exc}", file=sys.stderr)
            continue

        df = next(iter(bundle.values()))

        if "Study" not in df.columns or "Analysis.number" not in df.columns:
            continue

        an_name_col = "Analysis.name" if "Analysis.name" in df.columns else None

        for an in sorted(df["Analysis.number"].dropna().unique().tolist()):
            sub = df[df["Analysis.number"] == an]
            k = len(sub)
            if k < 3:
                continue  # below INVISIBILITY_THRESHOLD_K

            studies = sub["Study"].astype(str).tolist()
            an_name = (
                str(sub[an_name_col].iloc[0])
                if an_name_col and not sub.empty
                else ""
            )
            search_text = " ".join(studies) + " " + an_name

            ma_id = f"{rda_path.stem}__A{int(an)}"
            kw = _matched_keyword(search_text)
            entry = {
                "ma_id": ma_id,
                "rda_filename": rda_path.name,
                "k_total": k,
                "matched_keyword": kw,
                "analysis_name": an_name[:120],
            }

            if kw is not None:
                enriched_mas.append(entry)
            else:
                random_mas.append(entry)

    return enriched_mas, random_mas


def main() -> int:
    # Idempotency guard
    if _OUT_JSON.is_file():
        print(
            f"ERROR: {_OUT_JSON} already exists. "
            "Do NOT overwrite a pre-registered artefact. Exiting.",
            file=sys.stderr,
        )
        return 1

    pairwise70_dir = _data_dir()
    print(f"Pairwise70 dir: {pairwise70_dir}")

    # Step 1: Scan all RDAs
    enriched_mas, random_mas = _scan_pairwise70(pairwise70_dir)
    print(f"\nEnriched eligible MAs (k>=3): {len(enriched_mas)}")
    print(f"Random eligible MAs (k>=3):   {len(random_mas)}")

    # Step 2: Build enriched stratum (census of all 45)
    enriched_stratum = [
        {**e, "stratum": "enriched"} for e in enriched_mas
    ]
    n_enriched_actual = len(enriched_stratum)
    print(f"\nEnriched stratum: census of all {n_enriched_actual} eligible enriched MAs")

    # Step 3: Draw random stratum (seed=42)
    n_random_needed = _N_TOTAL - n_enriched_actual
    if n_random_needed < 1:
        print(
            f"ERROR: enriched census ({n_enriched_actual}) already exceeds target ({_N_TOTAL}). "
            "Increase _N_TOTAL or reduce enriched eligibility criteria.",
            file=sys.stderr,
        )
        return 1

    rng = random.Random(_SAMPLING_SEED)
    pool = list(random_mas)
    rng.shuffle(pool)
    random_stratum = [
        {**e, "stratum": "random"} for e in pool[:n_random_needed]
    ]
    print(f"Random stratum: drew {len(random_stratum)} from {len(random_mas)} eligible")

    # Combine
    ma_list = enriched_stratum + random_stratum
    assert len(ma_list) == n_enriched_actual + n_random_needed

    # Step 4: sha256 for sampled RDAs (tamper detection)
    rda_filenames_used = sorted({m["rda_filename"] for m in ma_list})
    rda_sha256: dict[str, str] = {}
    print(f"\nComputing sha256 for {len(rda_filenames_used)} sampled .rda files...")
    for fn in rda_filenames_used:
        rda_path = pairwise70_dir / fn
        rda_sha256[fn] = _sha256_file(rda_path)
        print(f"  {fn}: {rda_sha256[fn][:16]}...", flush=True)

    # Step 5: Assemble output JSON
    output = {
        "spec_version": _SPEC_VERSION,
        "spec_path": _SPEC_PATH,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sampling_seed": _SAMPLING_SEED,
        "n_enriched": n_enriched_actual,
        "n_random": n_random_needed,
        "n_total": len(ma_list),
        "enrichment_note": (
            f"Enriched stratum is a census of all {n_enriched_actual} eligible enriched MAs "
            f"(k>=3) matching Africa-endemic-disease keywords. "
            f"Random stratum drew {n_random_needed} from {len(random_mas)} non-enriched eligible MAs."
        ),
        "enrichment_keywords": _ENRICHMENT_KEYWORDS,
        "metadata_field_used": "Study strings + Analysis.name (concatenated)",
        "rda_sha256": rda_sha256,
        "ma_list": [
            {
                "ma_id": m["ma_id"],
                "stratum": m["stratum"],
                "k_total": m["k_total"],
                "matched_keyword": m["matched_keyword"],
                "rda_filename": m["rda_filename"],
                "analysis_name": m["analysis_name"],
            }
            for m in ma_list
        ],
    }

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _OUT_JSON.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nWrote {_OUT_JSON}")
    print(f"  n_enriched={n_enriched_actual}, n_random={n_random_needed}, total={len(ma_list)}")
    print("OTS-stamp this file BEFORE running the sonnet pilot batch.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
