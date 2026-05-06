#!/usr/bin/env python3
"""Tier-P blinded-audit calibration comparator for ARAC v0.1.1.

Reads:
  data/audit_v0.1.1/audit_llm_outputs.json   (written by tier_p_audit_batch.py)
  data/audit_v0.1.1/audit_auditor_results.json (written by the auditor HTML form)

Writes:
  data/audit_v0.1.1/audit_calibration_report.json

Statistics produced:
  - Confusion matrix (TP / FN / FP / TN) — Insufficient excluded
  - Sensitivity = TP / (TP + FN),  Wilson 95% CI
  - Specificity = TN / (TN + FP),  Wilson 95% CI
  - PPV = TP / (TP + FP)
  - Cohen's κ on the 2×2

Auditor JSON schema expected per result entry:
  {
    "trial_id": "...",
    "auditor_verdict": "African_majority" | "Not_African_majority" | "Insufficient"
  }
  (plus optional: auditor_african_pct, evidence_quote, confidence, notes)

Run via:
    python scripts/tier_p_audit_compare.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
_AUDIT_DIR = _REPO_ROOT / "data" / "audit_v0.1.1"
_LLM_FILE = _AUDIT_DIR / "audit_llm_outputs.json"
_AUDITOR_FILE = _AUDIT_DIR / "audit_auditor_results.json"
_REPORT_FILE = _AUDIT_DIR / "audit_calibration_report.json"

_SPEC_VERSION = "v0.1.1"
_SPEC_COMMIT = "ebc8c13"
_AMENDMENT = "prereg-v0.1.1.1-amend-1 (commit 0d3f69c)"

_EXPECTED_N = 30
_Z = 1.96  # 95% two-sided Wilson CI


# ---------------------------------------------------------------------------
# Category helpers
# ---------------------------------------------------------------------------

# LLM output: tier_p field values
_LLM_POSITIVE = "african_majority"
_LLM_NEGATIVE = "not_african_majority"
_LLM_INSUFFICIENT = "insufficient_data"

# Auditor verdict field values (case-sensitive, matching the HTML form)
_AUD_POSITIVE = "African_majority"
_AUD_NEGATIVE = "Not_African_majority"
_AUD_INSUFFICIENT = "Insufficient"


def _llm_evaluable(tier_p: str) -> bool:
    return tier_p in (_LLM_POSITIVE, _LLM_NEGATIVE)


def _aud_evaluable(verdict: str) -> bool:
    return verdict in (_AUD_POSITIVE, _AUD_NEGATIVE)


# ---------------------------------------------------------------------------
# Wilson 95% CI
# ---------------------------------------------------------------------------

def _wilson_ci(n: int, k: int) -> tuple[float, float]:
    """Wilson score 95% CI for k successes out of n trials.

    Returns (lower, upper). If n == 0, returns (nan, nan) — no crash.

    Formula (per spec §5):
        p = k / n
        centre = (p + z²/(2n)) / (1 + z²/n)
        spread  = (z * sqrt(p*(1-p)/n + z²/(4*n²))) / (1 + z²/n)
        CI      = (centre - spread, centre + spread)
    """
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = _Z * _Z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    spread = (_Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    lower = max(0.0, centre - spread)
    upper = min(1.0, centre + spread)
    return (lower, upper)


# ---------------------------------------------------------------------------
# Cohen's κ
# ---------------------------------------------------------------------------

def _cohen_kappa(tp: int, fn: int, fp: int, tn: int) -> float:
    """Cohen's κ on a 2×2 confusion matrix (LLM vs auditor), excluding Insufficient.

    Rows = auditor (true label): positive / negative
    Cols = LLM (predicted):      positive / negative

        LLM+  LLM-
    Aud+ TP    FN
    Aud- FP    TN

    p_observed = (TP + TN) / N
    p_chance   = ((TP+FN)*(TP+FP) + (FP+TN)*(FN+TN)) / N²
    κ          = (p_observed - p_chance) / (1 - p_chance)

    Returns nan if N == 0 or p_chance == 1.
    """
    n = tp + fn + fp + tn
    if n == 0:
        return float("nan")
    p_obs = (tp + tn) / n
    # Marginals
    row_pos = tp + fn    # auditor positives
    row_neg = fp + tn    # auditor negatives
    col_pos = tp + fp    # LLM positives
    col_neg = fn + tn    # LLM negatives
    p_chance = (row_pos * col_pos + row_neg * col_neg) / (n * n)
    if abs(1 - p_chance) < 1e-12:
        return float("nan")
    return (p_obs - p_chance) / (1 - p_chance)


# ---------------------------------------------------------------------------
# PPV
# ---------------------------------------------------------------------------

def _ppv(tp: int, fp: int) -> float | None:
    denom = tp + fp
    if denom == 0:
        return None
    return tp / denom


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------

def _load_json(path: Path, label: str) -> dict:
    if not path.is_file():
        print(f"ERROR: {label} not found at {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _validate_inputs(
    llm_data: dict,
    auditor_data: dict,
    expected_n: int = _EXPECTED_N,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Return (llm_by_id, auditor_by_id) after validating counts and id coverage.

    ``expected_n`` defaults to _EXPECTED_N (30) for production; tests may pass
    any positive integer to accommodate synthetic datasets of arbitrary size.
    """
    llm_results: list[dict] = llm_data.get("results", [])
    aud_results: list[dict] = auditor_data.get("results", [])

    if len(llm_results) != expected_n:
        print(
            f"ERROR: audit_llm_outputs.json has {len(llm_results)} results, "
            f"expected {expected_n}.",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(aud_results) != expected_n:
        print(
            f"ERROR: audit_auditor_results.json has {len(aud_results)} results, "
            f"expected {expected_n}.",
            file=sys.stderr,
        )
        sys.exit(1)

    llm_by_id = {r["trial_id"]: r for r in llm_results}
    aud_by_id = {r["trial_id"]: r for r in aud_results}

    missing_in_aud = set(llm_by_id) - set(aud_by_id)
    missing_in_llm = set(aud_by_id) - set(llm_by_id)
    if missing_in_aud or missing_in_llm:
        if missing_in_aud:
            print(
                f"ERROR: trial_ids in LLM file but not auditor file: {sorted(missing_in_aud)}",
                file=sys.stderr,
            )
        if missing_in_llm:
            print(
                f"ERROR: trial_ids in auditor file but not LLM file: {sorted(missing_in_llm)}",
                file=sys.stderr,
            )
        sys.exit(1)

    return llm_by_id, aud_by_id


def _print_sanity_table(
    llm_by_id: dict[str, dict],
    aud_by_id: dict[str, dict],
) -> None:
    print(
        f"\n{'trial_id':<45} {'llm_tier_p':<25} {'auditor_verdict':<25}",
        file=sys.stderr,
    )
    print("-" * 95, file=sys.stderr)
    for tid in sorted(llm_by_id):
        llm_v = llm_by_id[tid].get("tier_p", "?")
        aud_v = aud_by_id[tid].get("auditor_verdict", "?")
        print(f"{tid:<45} {llm_v:<25} {aud_v:<25}", file=sys.stderr)
    print(file=sys.stderr)


# ---------------------------------------------------------------------------
# Confusion matrix computation
# ---------------------------------------------------------------------------

def _compute_confusion(
    llm_by_id: dict[str, dict],
    aud_by_id: dict[str, dict],
) -> tuple[dict[str, int], dict[str, int]]:
    """Return (cm, insufficient_counts).

    cm = {TP, FN, FP, TN}
    insufficient_counts = {llm_only, auditor_only, both, either}
    """
    tp = fn = fp = tn = 0
    n_insuf_llm = 0
    n_insuf_aud = 0
    n_insuf_both = 0
    n_insuf_either = 0

    for tid, llm_r in llm_by_id.items():
        aud_r = aud_by_id[tid]
        llm_v = llm_r.get("tier_p", "")
        aud_v = aud_r.get("auditor_verdict", "")

        llm_insuf = not _llm_evaluable(llm_v)
        aud_insuf = not _aud_evaluable(aud_v)

        if llm_insuf or aud_insuf:
            n_insuf_either += 1
            if llm_insuf:
                n_insuf_llm += 1
            if aud_insuf:
                n_insuf_aud += 1
            if llm_insuf and aud_insuf:
                n_insuf_both += 1
            continue

        # Both evaluable — compute confusion cell
        llm_pos = llm_v == _LLM_POSITIVE
        aud_pos = aud_v == _AUD_POSITIVE

        if aud_pos and llm_pos:
            tp += 1
        elif aud_pos and not llm_pos:
            fn += 1
        elif not aud_pos and llm_pos:
            fp += 1
        else:
            tn += 1

    cm = {"TP": tp, "FN": fn, "FP": fp, "TN": tn}
    insuf = {
        "llm_only": n_insuf_llm - n_insuf_both,
        "auditor_only": n_insuf_aud - n_insuf_both,
        "both": n_insuf_both,
        "either": n_insuf_either,
    }
    return cm, insuf


# ---------------------------------------------------------------------------
# Headline formatter
# ---------------------------------------------------------------------------

def _format_headline(
    sensitivity: float,
    ci_lower: float,
    ci_upper: float,
    tp: int,
    fn: int,
    fp: int,
    tn: int,
    n_total: int,
) -> tuple[str, str]:
    """Return (value_str, qualifier_str) suitable for tiba.yaml."""
    n_aud_pos = tp + fn
    if math.isnan(sensitivity):
        value_str = "NaN (insufficient auditor-positive trials)"
        qualifier_str = (
            f"TP={tp}, FN={fn}, FP={fp}, TN={tn}; "
            f"{n_aud_pos} auditor-positive trials; "
            "n=30 (15 enriched + 15 random)"
        )
    else:
        pct = round(sensitivity * 100, 1)
        lo = round(ci_lower * 100, 1)
        hi = round(ci_upper * 100, 1)
        value_str = f"{pct}%"
        qualifier_str = (
            f"Wilson 95% CI [{lo}%–{hi}%]; "
            f"TP={tp}, FN={fn}, FP={fp}, TN={tn}; "
            f"{n_aud_pos} auditor-positive trials; "
            "15 enriched + 15 random stratum; "
            "auditor: mahmood726-cyber (v0.1.1; Makerere IRR planned for v0.2); "
            "pre-reg OTS stamped"
        )
    return value_str, qualifier_str


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def compute_calibration(
    llm_data: dict,
    auditor_data: dict,
    expected_n: int = _EXPECTED_N,
) -> dict:
    """Core computation — separated for testability.

    Parameters
    ----------
    llm_data:    dict matching audit_llm_outputs.json schema
    auditor_data: dict matching audit_auditor_results.json schema
    expected_n:  expected number of trials (default 30). Tests may pass any value.

    Returns the calibration report dict (does not write files).
    """
    llm_by_id, aud_by_id = _validate_inputs(llm_data, auditor_data, expected_n=expected_n)
    _print_sanity_table(llm_by_id, aud_by_id)

    cm, insuf = _compute_confusion(llm_by_id, aud_by_id)
    tp, fn, fp, tn = cm["TP"], cm["FN"], cm["FP"], cm["TN"]

    # Sensitivity
    n_sens = tp + fn
    sens_point = tp / n_sens if n_sens > 0 else float("nan")
    sens_lo, sens_hi = _wilson_ci(n_sens, tp)

    # Specificity
    n_spec = tn + fp
    spec_point = tn / n_spec if n_spec > 0 else float("nan")
    spec_lo, spec_hi = _wilson_ci(n_spec, tn)

    ppv_val = _ppv(tp, fp)
    kappa = _cohen_kappa(tp, fn, fp, tn)

    value_str, qualifier_str = _format_headline(
        sens_point, sens_lo, sens_hi, tp, fn, fp, tn,
        llm_data.get("n_trials", _EXPECTED_N),
    )

    return {
        "spec_version": _SPEC_VERSION,
        "spec_commit": _SPEC_COMMIT,
        "amendment": _AMENDMENT,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_trials": llm_data.get("n_trials", _EXPECTED_N),
        "confusion_matrix": cm,
        "n_insufficient_excluded": insuf["either"],
        "n_insufficient_llm_only": insuf["llm_only"],
        "n_insufficient_auditor_only": insuf["auditor_only"],
        "n_insufficient_both": insuf["both"],
        "sensitivity": {
            "point": None if math.isnan(sens_point) else sens_point,
            "ci_lower": None if math.isnan(sens_lo) else sens_lo,
            "ci_upper": None if math.isnan(sens_hi) else sens_hi,
        },
        "specificity": {
            "point": None if math.isnan(spec_point) else spec_point,
            "ci_lower": None if math.isnan(spec_lo) else spec_lo,
            "ci_upper": None if math.isnan(spec_hi) else spec_hi,
        },
        "ppv": ppv_val,
        "kappa": None if math.isnan(kappa) else kappa,
        "headline_for_tiba_yaml": value_str,
        "headline_qualifier_for_tiba_yaml": qualifier_str,
    }


def main() -> int:
    # Ensure UTF-8 output on Windows cp1252 consoles (per lessons.md).
    import io as _io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    llm_data = _load_json(_LLM_FILE, "audit_llm_outputs.json")
    auditor_data = _load_json(_AUDITOR_FILE, "audit_auditor_results.json")

    report = compute_calibration(llm_data, auditor_data)

    # --- Human-readable summary to stdout ---
    cm = report["confusion_matrix"]
    tp, fn, fp, tn = cm["TP"], cm["FN"], cm["FP"], cm["TN"]
    sens = report["sensitivity"]
    spec = report["specificity"]

    def _fmt_pct(v) -> str:
        return "NaN" if v is None else f"{v*100:.1f}%"

    print("=" * 60)
    print("ARAC v0.1.1 - Tier-P Blinded-Audit Calibration Report")
    print("=" * 60)
    print(f"Trials evaluated (confusion matrix):  {tp+fn+fp+tn}")
    print(f"Trials excluded (Insufficient):       {report['n_insufficient_excluded']}")
    print()
    print("Confusion matrix:")
    print(f"  TP={tp}  FN={fn}  FP={fp}  TN={tn}")
    print()
    print(f"Sensitivity: {_fmt_pct(sens['point'])}  "
          f"(95% CI: {_fmt_pct(sens['ci_lower'])}-{_fmt_pct(sens['ci_upper'])})")
    print(f"Specificity: {_fmt_pct(spec['point'])}  "
          f"(95% CI: {_fmt_pct(spec['ci_lower'])}-{_fmt_pct(spec['ci_upper'])})")
    ppv_val = report["ppv"]
    print(f"PPV:         {_fmt_pct(ppv_val) if ppv_val is not None else 'N/A (TP+FP=0)'}")
    kappa = report["kappa"]
    print(f"Cohen's kappa: {'NaN' if kappa is None else f'{kappa:.4f}'}")
    print()
    print("Headline for tiba.yaml:")
    print(f"  value: {report['headline_for_tiba_yaml']!r}")
    print(f"  ci_or_qualifier: {report['headline_qualifier_for_tiba_yaml']!r}")
    print()

    # --- Write report ---
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"Report written: {_REPORT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
