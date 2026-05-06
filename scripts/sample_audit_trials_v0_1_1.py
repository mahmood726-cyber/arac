#!/usr/bin/env python
"""
Deterministic stratified sampler for ARAC v0.1.1 blinded-audit calibration.

Pre-registration spec: docs/superpowers/specs/2026-05-06-rgs-blinded-audit.md
Spec commit: ebc8c13
OTS: data/audit_v0.1.1/sample_list.json.ots

Usage:
    cd C:/Projects/arac
    python scripts/sample_audit_trials_v0_1_1.py

Output: data/audit_v0.1.1/sample_list.json

Discipline:
- N=30 is locked (spec §2). No --n override.
- Seed 42 is locked (spec §2). No --seed override.
- Idempotent: if sample_list.json already exists, STOP.
- Deterministic: two runs produce identical JSON (modulo generated_at).
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pyreadr

# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# Now import ARAC modules
from arac.bridge import TrialRow  # noqa: E402
from arac.resolve.pubmed import PubMedClient  # noqa: E402
from arac.resolve.resolver import StudyResolver  # noqa: E402

# ---------------------------------------------------------------------------
# Spec-locked constants (DO NOT CHANGE)
# ---------------------------------------------------------------------------
_SPEC_VERSION = "v0.1.1"
_SPEC_COMMIT = "ebc8c13"
_SPEC_PATH = "docs/superpowers/specs/2026-05-06-rgs-blinded-audit.md"
_SAMPLING_SEED = 42
_N_ENRICHED = 15
_N_RANDOM = 15
_N_TOTAL = _N_ENRICHED + _N_RANDOM

# African keywords as listed in spec §2 (case-insensitive substring match)
_AFRICAN_KEYWORDS: list[str] = [
    "Uganda", "Kenya", "South Africa", "Nigeria", "Tanzania", "Ghana",
    "Malawi", "Ethiopia", "Zimbabwe", "Zambia", "Mozambique", "Rwanda",
    "Cameroon", "Senegal", "Mali", "Gambia", "Burkina Faso", "Botswana",
    "Côte d'Ivoire", "Democratic Republic", "Sudan",
]

# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
_OUT_DIR = _REPO_ROOT / "data" / "audit_v0.1.1"
_OUT_JSON = _OUT_DIR / "sample_list.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    """Discover Pairwise70 data directory (mirrors inspect_rda._data_dir)."""
    import os
    env_override = os.environ.get("PAIRWISE70_DIR")
    if env_override:
        p = Path(env_override)
        if not p.is_dir():
            raise RuntimeError(
                f"PAIRWISE70_DIR={env_override!r} is set but is not a directory."
            )
        return p
    candidates = [
        "C:/Projects/Pairwise70/data",
        "D:/Projects/Pairwise70/data",
    ]
    for c in candidates:
        p = Path(c)
        if p.is_dir():
            return p
    raise RuntimeError(
        f"Pairwise70 data directory not found. Set PAIRWISE70_DIR env var "
        f"or place data at one of: {candidates}"
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _has_african_keyword(study_string: str) -> bool:
    """Case-insensitive substring check against spec African keyword list."""
    sl = study_string.lower()
    return any(kw.lower() in sl for kw in _AFRICAN_KEYWORDS)


def _load_all_trials(
    pairwise70_dir: Path,
) -> tuple[list[tuple[str, int, str, str]], list[tuple[str, int, str, str]]]:
    """
    Scan all 595 .rda files and build two flat lists of
    (ma_id, trial_index, study_string, rda_filename):
      - enriched_trials: from MAs that contain >=1 African-keyword study string
      - random_trials: from all other MAs
    """
    enriched_trials: list[tuple[str, int, str, str]] = []
    random_trials: list[tuple[str, int, str, str]] = []

    rda_files = sorted(pairwise70_dir.glob("*.rda"))
    print(f"Scanning {len(rda_files)} .rda files...", flush=True)

    for rda_path in rda_files:
        try:
            bundle = pyreadr.read_r(str(rda_path))
        except Exception as exc:
            print(f"  WARN: could not read {rda_path.name}: {exc}", file=sys.stderr)
            continue

        df = next(iter(bundle.values()))
        if "Study" not in df.columns or "Analysis.number" not in df.columns:
            continue

        analyses = sorted(df["Analysis.number"].dropna().unique().tolist())
        for an in analyses:
            sub = df[df["Analysis.number"] == an]
            if sub.empty:
                continue
            studies = sub["Study"].astype(str).tolist()
            ma_id = f"{rda_path.stem}__A{int(an)}"
            rda_fn = rda_path.name

            # Determine stratum: if ANY study string contains an African keyword
            is_enriched = any(_has_african_keyword(s) for s in studies)

            flat = [(ma_id, i, studies[i], rda_fn) for i in range(len(studies))]
            if is_enriched:
                enriched_trials.extend(flat)
            else:
                random_trials.extend(flat)

    return enriched_trials, random_trials


def _resolve_trial(
    resolver: StudyResolver,
    pubmed: PubMedClient,
    ma_id: str,
    trial_index: int,
    study_string: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Attempt to resolve a trial to a PMID and fetch its abstract.
    Returns (pmid, abstract_text) or (None, None) on failure.
    """
    trial_row = TrialRow(
        ma_id=ma_id,
        trial_index=trial_index,
        trial_id=f"{ma_id}::t{trial_index}",
        data_type="unknown",  # data_type not used by resolver
        k_total=1,
    )
    try:
        meta = resolver.resolve(trial_row, study_string)
    except Exception as exc:
        print(f"    resolver error for {ma_id}::t{trial_index}: {exc}", file=sys.stderr)
        return None, None

    if meta.pmid is None:
        return None, None

    # Fetch abstract
    try:
        rec = pubmed.efetch(meta.pmid)
    except Exception as exc:
        print(f"    pubmed error for pmid={meta.pmid}: {exc}", file=sys.stderr)
        return None, None

    if rec is None or not rec.abstract_text:
        return None, None

    return meta.pmid, rec.abstract_text


def _draw_stratum(
    stratum_name: str,
    candidate_pool: list[tuple[str, int, str, str]],
    n_draw: int,
    resolver: StudyResolver,
    pubmed: PubMedClient,
    rng: random.Random,
    draw_order_start: int,
) -> tuple[list[dict], list[dict]]:
    """
    Draw n_draw eligible trials from candidate_pool (flat list).
    Eligibility: resolves to PMID AND has non-empty abstract.
    On failure, draw next candidate (without replacement from shuffled pool).
    Returns (sampled_trials, replacements_log).
    """
    # Shuffle pool deterministically
    pool = list(candidate_pool)
    rng.shuffle(pool)

    sampled: list[dict] = []
    replacements_log: list[dict] = []
    pool_iter = iter(pool)
    draw_order = draw_order_start

    while len(sampled) < n_draw:
        try:
            ma_id, trial_index, study_string, rda_fn = next(pool_iter)
        except StopIteration:
            raise RuntimeError(
                f"Exhausted candidate pool for stratum='{stratum_name}' "
                f"after {len(sampled)}/{n_draw} draws. "
                f"Pool had {len(pool)} candidates."
            )

        trial_id = f"{ma_id}::t{trial_index}"
        print(f"  [{stratum_name}] draw {draw_order}: {trial_id} ({study_string[:50]})", flush=True)

        pmid, abstract_text = _resolve_trial(
            resolver, pubmed, ma_id, trial_index, study_string
        )

        if pmid is None:
            reason = "no_pmid"
            print(f"    -> REJECT ({reason})", flush=True)
            replacements_log.append({
                "stratum": stratum_name,
                "rejected_trial": trial_id,
                "reason": reason,
                "replaced_by_draw_order": draw_order + 1,  # next accepted draw
            })
            continue

        if not abstract_text:
            reason = "no_abstract"
            print(f"    -> REJECT ({reason}) pmid={pmid}", flush=True)
            replacements_log.append({
                "stratum": stratum_name,
                "rejected_trial": trial_id,
                "reason": reason,
                "replaced_by_draw_order": draw_order + 1,
            })
            continue

        print(f"    -> ACCEPT pmid={pmid}", flush=True)
        sampled.append({
            "stratum": stratum_name,
            "trial_id": trial_id,
            "ma_id": ma_id,
            "rda_filename": rda_fn,
            "study_string": study_string,
            "pmid": pmid,
            "abstract_first_120_chars": abstract_text[:120],
            "draw_order": draw_order,
        })
        draw_order += 1

    # Fix up the replaced_by_draw_order for entries pointing past the end —
    # they reference the draw_order of the replacement that actually succeeded.
    # The log entries were set to draw_order+1 at rejection time; those in
    # a sequence of consecutive rejections need their replaced_by_draw_order
    # updated to the next accepted draw_order in sampled.
    # Simple approach: for each rejection, find the first accepted draw with
    # draw_order > rejection.draw_order_placeholder and use that.
    accepted_orders = [e["draw_order"] for e in sampled]
    for log_entry in replacements_log:
        # The placeholder is draw_order+1 where draw_order was the loop counter
        # at rejection time. We stored draw_order+1 as the replacement hint.
        # Replace with the real first accepted draw >= placeholder:
        placeholder = log_entry["replaced_by_draw_order"]
        real = next((o for o in accepted_orders if o >= placeholder), placeholder)
        log_entry["replaced_by_draw_order"] = real

    return sampled, replacements_log


def main() -> int:
    # Idempotency guard — never overwrite a pre-registered artefact
    if _OUT_JSON.is_file():
        print(
            f"ERROR: {_OUT_JSON} already exists. "
            "Do NOT overwrite a pre-registered artefact. Exiting.",
            file=sys.stderr,
        )
        return 1

    pairwise70_dir = _data_dir()
    print(f"Pairwise70 dir: {pairwise70_dir}")

    # Cache directory (use same path as build_atlas.py for cache reuse)
    cache_dir = _REPO_ROOT / "outputs" / "cache" / "resolve"
    cache_dir.mkdir(parents=True, exist_ok=True)

    resolver = StudyResolver(cache_dir=cache_dir)
    pubmed = PubMedClient(cache_dir=cache_dir / "pubmed")

    # Step 1: build enriched and random trial pools
    enriched_pool, random_pool = _load_all_trials(pairwise70_dir)
    print(f"Enriched pool: {len(enriched_pool)} trials across enriched MAs")
    print(f"Random pool:   {len(random_pool)} trials across non-enriched MAs")

    # Step 2: seed RNG ONCE before any draws (spec: random.seed(42))
    rng = random.Random(_SAMPLING_SEED)

    # Step 3: draw enriched stratum (15 trials)
    print(f"\n--- Stratum 1 (enriched): drawing {_N_ENRICHED} trials ---")
    enriched_sampled, enriched_log = _draw_stratum(
        stratum_name="enriched",
        candidate_pool=enriched_pool,
        n_draw=_N_ENRICHED,
        resolver=resolver,
        pubmed=pubmed,
        rng=rng,
        draw_order_start=1,
    )

    # Step 4: draw random stratum (15 trials), draw_order continues from enriched
    next_draw_order = enriched_sampled[-1]["draw_order"] + 1 if enriched_sampled else 16
    print(f"\n--- Stratum 2 (random): drawing {_N_RANDOM} trials ---")
    random_sampled, random_log = _draw_stratum(
        stratum_name="random",
        candidate_pool=random_pool,
        n_draw=_N_RANDOM,
        resolver=resolver,
        pubmed=pubmed,
        rng=rng,
        draw_order_start=next_draw_order,
    )

    all_trials = enriched_sampled + random_sampled
    all_replacements = enriched_log + random_log

    assert len(all_trials) == _N_TOTAL, f"Expected {_N_TOTAL} trials, got {len(all_trials)}"

    # Step 5: sha256 of sampled .rda files only (R5 mitigation)
    rda_filenames_used = sorted({t["rda_filename"] for t in all_trials})
    pairwise70_rda_sha256: dict[str, str] = {}
    print(f"\nComputing sha256 for {len(rda_filenames_used)} sampled .rda files...")
    for fn in rda_filenames_used:
        rda_path = pairwise70_dir / fn
        pairwise70_rda_sha256[fn] = _sha256_file(rda_path)
        print(f"  {fn}: {pairwise70_rda_sha256[fn][:16]}...")

    # Step 6: assemble output JSON
    output = {
        "spec_version": _SPEC_VERSION,
        "spec_commit": _SPEC_COMMIT,
        "spec_path": _SPEC_PATH,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sampling_seed": _SAMPLING_SEED,
        "n_total": _N_TOTAL,
        "n_enriched": _N_ENRICHED,
        "n_random": _N_RANDOM,
        "pairwise70_dir": str(pairwise70_dir),
        "pairwise70_rda_sha256": pairwise70_rda_sha256,
        "trials": all_trials,
        "replacements_log": all_replacements,
    }

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _OUT_JSON.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    n_enriched_out = sum(1 for t in all_trials if t["stratum"] == "enriched")
    n_random_out = sum(1 for t in all_trials if t["stratum"] == "random")
    print(
        f"\nWrote {_OUT_JSON} with {len(all_trials)} trials "
        f"({n_enriched_out} enriched + {n_random_out} random)"
    )
    print(f"Replacements: {len(all_replacements)} total")
    print(f"Distinct .rda files: {len(rda_filenames_used)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
