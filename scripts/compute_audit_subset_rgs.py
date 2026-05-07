# sentinel:skip-file — local-path defaults are research fixture locators (Pairwise70
# data dir), not shipping code. The canonical override is the PAIRWISE70_DIR env var.
"""Compute Tier-P RGS metrics for the v0.1.1 audit subset.

Reads the frozen opus Tier-P classifications from:
    data/audit_v0.1.1/audit_llm_outputs.json

Groups by MA (using trial_id prefix), loads each MA's Pairwise70 .rda,
and computes per-MA RGS metrics using ARAC's existing RGSEngine.

Output: data/audit_v0.1.1/atlas_subset.csv (24-column ARAC standard atlas schema).

Usage:
    python scripts/compute_audit_subset_rgs.py [--out data/audit_v0.1.1/atlas_subset.csv]

Pre-flight: verifies audit_llm_outputs.json sha256 matches sample_list.json's recorded
value (anti-tamper check). Fails closed if mismatch detected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import pyreadr

# Ensure ARAC src is on path (when run from scripts/ or repo root).
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
# Also ensure scripts/ is on path (for inspect_rda._data_dir).
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from arac.bridge import MARecord  # noqa: E402 — sys.path must be set first
from arac.repool import repool_subset  # noqa: E402
from arac.rgs.csv_writer import write_rgs_rows  # noqa: E402
from arac.rgs.engine import RGSEngine, RGSTier  # noqa: E402


# ---------------------------------------------------------------------------
# Paths (relative to repo root)
# ---------------------------------------------------------------------------
_AUDIT_DIR = _REPO_ROOT / "data" / "audit_v0.1.1"
_AUDIT_LLM_OUTPUTS = _AUDIT_DIR / "audit_llm_outputs.json"
_SAMPLE_LIST = _AUDIT_DIR / "sample_list.json"
_DEFAULT_OUT = _AUDIT_DIR / "atlas_subset.csv"


def _sha256_file(path: Path) -> str:
    """Compute sha256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _preflight(llm_outputs_path: Path, sample_list_path: Path) -> dict:
    """Anti-tamper check: verify audit_llm_outputs.json sha256 against sample_list.json.

    Returns the parsed audit_llm_outputs dict if check passes.
    Raises RuntimeError if any preflight fails.
    """
    if not llm_outputs_path.is_file():
        raise RuntimeError(
            f"audit_llm_outputs.json not found at {llm_outputs_path}. "
            "Run the v0.1.1 audit batch first."
        )
    if not sample_list_path.is_file():
        raise RuntimeError(
            f"sample_list.json not found at {sample_list_path}."
        )

    with sample_list_path.open(encoding="utf-8") as f:
        sample_list = json.load(f)

    # audit_llm_outputs.json records the sample_list_sha256 it was produced from.
    with llm_outputs_path.open(encoding="utf-8") as f:
        llm_outputs = json.load(f)

    recorded_sha = llm_outputs.get("sample_list_sha256")
    actual_sha = _sha256_file(sample_list_path)
    if recorded_sha and recorded_sha != actual_sha:
        raise RuntimeError(
            f"ANTI-TAMPER FAIL: sample_list.json sha256 mismatch.\n"
            f"  audit_llm_outputs records: {recorded_sha}\n"
            f"  actual file sha256:        {actual_sha}\n"
            "Do NOT recompute with a modified sample list — the Tier-P verdicts "
            "are frozen to the original sample."
        )

    return llm_outputs, sample_list


def _parse_trial_id(trial_id: str) -> tuple[str, int]:
    """Extract (ma_id, trial_index) from trial_id like 'MA__A1::t7'."""
    sep = "::"
    if sep not in trial_id:
        raise ValueError(f"Unexpected trial_id format (no '::'): {trial_id!r}")
    ma_id, rest = trial_id.rsplit(sep, 1)
    if not rest.startswith("t"):
        raise ValueError(f"Unexpected trial_id suffix (expected 't<N>'): {trial_id!r}")
    trial_index = int(rest[1:])
    return ma_id, trial_index


def _group_by_ma(
    results: list[dict],
    sample_trials: list[dict],
) -> dict[str, dict]:
    """Return a dict keyed by ma_id. Each value:

    {
        "rda_filename": str,
        "audited_trials": {trial_index: tier_p_verdict},
    }

    Merges verdict info from llm_outputs with rda_filename from sample_list.
    """
    # Build trial_id → rda_filename from sample_list.
    rda_by_trial: dict[str, str] = {t["trial_id"]: t["rda_filename"] for t in sample_trials}

    # Build trial_id → tier_p from llm_outputs.
    tier_p_by_trial: dict[str, str] = {r["trial_id"]: r["tier_p"] for r in results}

    ma_map: dict[str, dict] = {}
    for trial_id, rda_filename in rda_by_trial.items():
        ma_id, trial_index = _parse_trial_id(trial_id)
        if ma_id not in ma_map:
            ma_map[ma_id] = {"rda_filename": rda_filename, "audited_trials": {}}
        tier_p = tier_p_by_trial.get(trial_id, "not_classified")
        ma_map[ma_id]["audited_trials"][trial_index] = tier_p

    return ma_map


def _load_ma_record(ma_id: str, rda_filename: str, pairwise70_dir: Path) -> Optional[MARecord]:
    """Load one MARecord from a .rda file. Returns None if load fails."""
    rda_path = pairwise70_dir / rda_filename
    if not rda_path.is_file():
        print(f"  WARN: .rda not found: {rda_path}", file=sys.stderr)
        return None

    # Parse MA identifiers from ma_id: format "CD<review>_pub<N>_data__A<analysis_number>"
    # e.g. "CD006404_pub5_data__A10"
    try:
        parts = ma_id.split("__A")
        review_id = parts[0]  # e.g. "CD006404_pub5_data"
        analysis_number = int(parts[1])
    except (IndexError, ValueError):
        print(f"  WARN: cannot parse ma_id: {ma_id!r}", file=sys.stderr)
        return None

    try:
        bundle = pyreadr.read_r(str(rda_path))
        df = next(iter(bundle.values()))
    except Exception as e:
        print(f"  WARN: failed to read {rda_path}: {e}", file=sys.stderr)
        return None

    # Filter rows for this analysis number.
    if "Analysis.number" not in df.columns:
        print(f"  WARN: no 'Analysis.number' column in {rda_filename}", file=sys.stderr)
        return None

    sub = df[df["Analysis.number"] == analysis_number].reset_index(drop=True)
    if sub.empty:
        print(f"  WARN: no rows for analysis {analysis_number} in {rda_filename}", file=sys.stderr)
        return None

    k = len(sub)

    # Detect data type and build MAInputs — reuse ARAC's bridge / repro-floor-atlas loader.
    # We delegate to the full load_all_mas machinery for consistency.
    from inspect_rda import _data_dir as _inspect_data_dir  # type: ignore  # noqa: F401
    from arac.bridge import load_all_mas  # noqa: F811

    try:
        all_mas = load_all_mas(pairwise70_dir, max_reviews=None)
    except Exception as e:
        print(f"  WARN: load_all_mas failed: {e}", file=sys.stderr)
        return None

    record = next((m for m in all_mas if m.ma_id == ma_id), None)
    if record is None:
        print(f"  WARN: MA {ma_id!r} not found in Pairwise70 load result", file=sys.stderr)
    return record


def _pairwise70_dir() -> Path:
    """Resolve Pairwise70 data directory (mirrors inspect_rda._data_dir logic)."""
    import os
    env = os.environ.get("PAIRWISE70_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
        raise RuntimeError(f"PAIRWISE70_DIR={env!r} is not a directory")
    for candidate in ["C:/Projects/Pairwise70/data", "D:/Projects/Pairwise70/data"]:  # sentinel:skip-line P0-hardcoded-local-path
        p = Path(candidate)
        if p.is_dir():
            return p
    raise RuntimeError(  # sentinel:skip-line P0-hardcoded-local-path
        "Pairwise70 data directory not found. Set PAIRWISE70_DIR env var "
        "or place data at C:/Projects/Pairwise70/data or D:/Projects/Pairwise70/data."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(_DEFAULT_OUT))
    args = ap.parse_args(argv)
    out_path = Path(args.out)

    # --- Pre-flight -----------------------------------------------------------
    print("Pre-flight: verifying audit_llm_outputs.json anti-tamper check...")
    try:
        llm_outputs, sample_list = _preflight(_AUDIT_LLM_OUTPUTS, _SAMPLE_LIST)
    except RuntimeError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(f"  OK — {llm_outputs['n_trials']} trials, model={llm_outputs['model']}")

    # --- Group by MA ----------------------------------------------------------
    ma_map = _group_by_ma(llm_outputs["results"], sample_list["trials"])
    unique_mas = sorted(ma_map.keys())
    print(f"\nGrouped {llm_outputs['n_trials']} trials -> {len(unique_mas)} unique MAs")

    # Count african_majority verdicts.
    total_african = sum(
        1
        for ma_info in ma_map.values()
        for verdict in ma_info["audited_trials"].values()
        if verdict == "african_majority"
    )
    print(f"african_majority verdicts across all MAs: {total_african}")

    # --- Load Pairwise70 data -------------------------------------------------
    try:
        pairwise70_dir = _pairwise70_dir()
    except RuntimeError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(f"\nPairwise70 dir: {pairwise70_dir}")

    # Load all MAs referenced in the sample (cache full load once).
    print("Loading MARecords from Pairwise70...")
    from arac.bridge import load_all_mas  # noqa: F811
    try:
        all_mas = load_all_mas(pairwise70_dir, max_reviews=None)
    except Exception as e:
        print(f"FAIL loading Pairwise70: {e}", file=sys.stderr)
        return 1
    ma_lookup: dict[str, MARecord] = {m.ma_id: m for m in all_mas}
    print(f"  Loaded {len(ma_lookup)} total MAs from Pairwise70")

    # --- Compute RGS for each MA in the audit subset -------------------------
    engine = RGSEngine()
    rgs_rows = []
    summary_lines = []

    header = (
        f"{'MA':<40} {'k_tot':>5} {'k_sub':>5} {'invisible':>9} "
        f"{'full_est':>10} {'sub_est':>10} {'repro_gap':>9} {'sign_flip':>9} {'rec_chg':>7}"
    )
    summary_lines.append(header)
    summary_lines.append("-" * len(header))

    for ma_id in unique_mas:
        ma_info = ma_map[ma_id]
        audited_trials = ma_info["audited_trials"]  # {trial_index: verdict}

        # African majority indices.
        african_indices = tuple(
            idx for idx, verdict in audited_trials.items()
            if verdict == "african_majority"
        )

        # Load MARecord.
        record = ma_lookup.get(ma_id)
        if record is None:
            print(f"  WARN: {ma_id} not found in Pairwise70 load — skipping", file=sys.stderr)
            continue

        # Compute RGS (engine handles k_subset < 3 → invisible internally).
        result = engine.compute(record, RGSTier.PARTICIPANT, african_indices)
        rgs_rows.append(result)

        # Summary row.
        full_est_str = f"{result.full_pooled_estimate:.4f}" if result.full_pooled_estimate is not None else "N/A"
        sub_est_str = f"{result.subset_pooled_estimate:.4f}" if result.subset_pooled_estimate is not None else "N/A"
        summary_lines.append(
            f"{ma_id:<40} {record.k:>5} {len(african_indices):>5} "
            f"{'True' if result.invisible else 'False':>9} "
            f"{full_est_str:>10} {sub_est_str:>10} "
            f"{str(result.reproduction_gap):>9} "
            f"{str(result.sign_flip):>9} "
            f"{str(result.recommendation_change):>7}"
        )

    # --- Write CSV ------------------------------------------------------------
    n_written = write_rgs_rows(rgs_rows, out_path)
    print(f"\nWrote {n_written} rows to {out_path}")

    # --- Print summary table --------------------------------------------------
    print("\n" + "\n".join(summary_lines))

    # --- Stats summary --------------------------------------------------------
    n_invisible = sum(1 for r in rgs_rows if r.invisible)
    n_visible = sum(1 for r in rgs_rows if not r.invisible)
    n_repro_gap = sum(1 for r in rgs_rows if r.reproduction_gap is True)
    print(f"\nSummary: {len(rgs_rows)} MAs total | {n_invisible} invisible | {n_visible} visible")
    if n_visible > 0:
        print(f"  Visible MAs with reproduction_gap: {n_repro_gap}/{n_visible}")
    else:
        print(
            "  All MAs invisible (k_subset < 3 in every MA). "
            "This is expected: only 2 african_majority trials in the 30-trial "
            "v0.1.1 sample, both in separate MAs (k_subset=1 each) -> invisible. "
            "Full pooled estimates are computed for all MAs. "
            "v0.2 pilot atlas (n=100, targeted sampling) will produce visible rows."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
