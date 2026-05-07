"""Phase 4 — Sonnet calibration mini-audit for ARAC v0.2.

Compares sonnet classifications against v0.1.1 opus classifications on the first 10
evaluable (non-insufficient) trials from the v0.1.1 sample.

Usage:
    cd <arac repo root>
    python scripts/run_sonnet_calibration_v0_2.py

Output: data/v0.2/sonnet_calibration_report.json

STOP gate: if kappa < 0.6, the script exits non-zero and prints STOP.
If kappa >= 0.6, it exits 0 and prints PROCEED.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_AUDIT_DIR = _REPO_ROOT / "data" / "audit_v0.1.1"
_AUDIT_LLM_OUTPUTS = _AUDIT_DIR / "audit_llm_outputs.json"
_ABSTRACTS_CACHE = _AUDIT_DIR / "abstracts_cache.json"
_OUT_DIR = _REPO_ROOT / "data" / "v0.2"
_OUT_REPORT = _OUT_DIR / "sonnet_calibration_report.json"

# ---------------------------------------------------------------------------
# System prompt (verbatim from tier_p_extractor.py)
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are extracting participant-geography data from clinical trial reports for a meta-research project (ARAC — African Representation Atlas of Cochrane).

Given a trial's title and abstract, identify what fraction of participants were enrolled in African countries vs non-African countries.

Definitions:
- "African" means the participant was enrolled at a site in any of the 54 African Union member states (Algeria, Angola, Benin, Botswana, Burkina Faso, Burundi, Cabo Verde, Cameroon, Central African Republic, Chad, Comoros, Congo, Democratic Republic of the Congo, Cote d'Ivoire, Djibouti, Egypt, Equatorial Guinea, Eritrea, Eswatini, Ethiopia, Gabon, Gambia, Ghana, Guinea, Guinea-Bissau, Kenya, Lesotho, Liberia, Libya, Madagascar, Malawi, Mali, Mauritania, Mauritius, Morocco, Mozambique, Namibia, Niger, Nigeria, Rwanda, Sao Tome and Principe, Senegal, Seychelles, Sierra Leone, Somalia, South Africa, South Sudan, Sudan, Tanzania, Togo, Tunisia, Uganda, Zambia, Zimbabwe).

Rules:
1. Only count participants explicitly described in the abstract. Do not infer from author affiliations or sponsor location.
2. If exact percentages are given, use them. If only counts are given (e.g., "200 in Uganda, 100 in Kenya, 700 in USA"), compute the percentage.
3. If geography is not mentioned in the abstract at all, set confidence to "insufficient" and leave percentages null.
4. If the abstract mentions a multi-country trial without specifying counts (e.g., "conducted in 14 countries including Uganda and South Africa"), set confidence to "low" and estimate based on country count if possible.
5. Always quote the exact source text you used as evidence.
6. Be conservative: if you're not sure, set confidence to "insufficient" rather than guessing.

Return a structured ParticipantGeography record. Set null values when the abstract doesn't support extraction; do not fabricate."""


def _classify_with_sonnet(pmid: str, abstract_text: str, api_key: str, model: str) -> dict:
    """Call sonnet to classify one abstract. Returns dict with tier_p, confidence, african_pct."""
    import anthropic
    from pydantic import BaseModel, Field
    from typing import Optional, Literal

    class ParticipantGeography(BaseModel):
        african_participant_pct: Optional[float] = Field(None, ge=0, le=100)
        non_african_participant_pct: Optional[float] = Field(None, ge=0, le=100)
        countries_mentioned: list[str] = Field(default_factory=list)
        evidence_source: Optional[str] = None
        confidence: Literal["high", "medium", "low", "insufficient"]
        reasoning: str

    client = anthropic.Anthropic(api_key=api_key)
    tool_schema = ParticipantGeography.model_json_schema()

    user_text = f"PMID: {pmid}\n\nAbstract:\n{abstract_text}"

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text}],
        tools=[{
            "name": "extract_participant_geography",
            "description": "Extract participant geography data from a clinical trial abstract.",
            "input_schema": tool_schema,
        }],
        tool_choice={"type": "tool", "name": "extract_participant_geography"},
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    result = ParticipantGeography.model_validate(tool_block.input)

    # Derive tier_p
    pct = result.african_participant_pct
    if result.confidence == "insufficient" or pct is None:
        tier_p = "insufficient_data"
    elif pct >= 50.0:
        tier_p = "african_majority"
    else:
        tier_p = "not_african_majority"

    return {
        "pmid": pmid,
        "tier_p": tier_p,
        "confidence": result.confidence,
        "african_pct": pct,
        "non_african_pct": result.non_african_participant_pct,
        "countries_mentioned": result.countries_mentioned,
        "evidence_source": result.evidence_source,
        "reasoning": result.reasoning,
    }


def _cohen_kappa(opus_labels: list[str], sonnet_labels: list[str]) -> float:
    """Compute Cohen's kappa for two-rater binary classification.

    Only counts trials where BOTH classifiers give a definitive classification
    (african_majority or not_african_majority). insufficient_data trials are
    excluded from kappa computation (they are agreement by tie, not by judgment).
    """
    assert len(opus_labels) == len(sonnet_labels)
    n = len(opus_labels)
    if n == 0:
        return float("nan")

    agree = sum(1 for a, b in zip(opus_labels, sonnet_labels) if a == b)
    po = agree / n  # observed agreement

    # Expected agreement (by chance)
    classes = sorted(set(opus_labels) | set(sonnet_labels))
    pe = sum(
        (opus_labels.count(c) / n) * (sonnet_labels.count(c) / n)
        for c in classes
    )

    if pe == 1.0:
        return 1.0  # perfect agreement by chance too
    return (po - pe) / (1.0 - pe)


def main() -> int:
    # Idempotency
    if _OUT_REPORT.is_file():
        print(
            f"WARNING: {_OUT_REPORT} already exists. Delete it to re-run.",
            file=sys.stderr,
        )
        report = json.loads(_OUT_REPORT.read_text(encoding="utf-8"))
        kappa = report.get("kappa", 0.0)
        verdict = report.get("verdict", "UNKNOWN")
        print(f"Existing report: kappa={kappa:.3f}  verdict={verdict}")
        return 0 if verdict == "PROCEED" else 1

    # Load v0.1.1 opus outputs
    if not _AUDIT_LLM_OUTPUTS.is_file():
        print(f"ERROR: {_AUDIT_LLM_OUTPUTS} not found", file=sys.stderr)
        return 1
    llm_outputs = json.loads(_AUDIT_LLM_OUTPUTS.read_text(encoding="utf-8"))

    # Load abstracts cache
    if not _ABSTRACTS_CACHE.is_file():
        print(f"ERROR: {_ABSTRACTS_CACHE} not found", file=sys.stderr)
        return 1
    abstracts_cache: dict[str, str] = json.loads(
        _ABSTRACTS_CACHE.read_text(encoding="utf-8")
    )

    # Get 10 evaluable trials (first 10 by trial_id, non-insufficient)
    evaluable = [
        r for r in llm_outputs["results"]
        if r["tier_p"] in ("african_majority", "not_african_majority")
    ]
    evaluable_sorted = sorted(evaluable, key=lambda r: r["trial_id"])
    cal_trials = evaluable_sorted[:10]
    print(f"Calibration trials: {len(cal_trials)} (first 10 evaluable by trial_id)")

    # Resolve API key + model
    api_key = (
        os.environ.get("ARAC_ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    if not api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY not set. Cannot run sonnet calibration.",
            file=sys.stderr,
        )
        return 1

    sonnet_model = os.environ.get("ARAC_TIER_P_MODEL", "claude-sonnet-4-6")
    opus_model = llm_outputs.get("model", "claude-opus-4-7")
    print(f"Opus model (v0.1.1): {opus_model}")
    print(f"Sonnet model (v0.2): {sonnet_model}")

    # Run sonnet on each calibration trial
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    sonnet_results = []
    opus_labels = []
    sonnet_labels = []

    for i, trial in enumerate(cal_trials, 1):
        pmid = trial["pmid"]
        abstract_text = abstracts_cache.get(pmid, "")
        if not abstract_text:
            print(f"  [{i}/10] {trial['trial_id']}: NO ABSTRACT in cache — skip", flush=True)
            continue

        print(f"  [{i}/10] {trial['trial_id']}  pmid={pmid}  opus={trial['tier_p']}", flush=True)

        try:
            sonnet_result = _classify_with_sonnet(pmid, abstract_text, api_key, sonnet_model)
            sonnet_result["trial_id"] = trial["trial_id"]
            sonnet_result["opus_tier_p"] = trial["tier_p"]
            sonnet_result["opus_african_pct"] = trial["african_pct"]
            sonnet_results.append(sonnet_result)

            opus_labels.append(trial["tier_p"])
            sonnet_labels.append(sonnet_result["tier_p"])

            agreement = "AGREE" if trial["tier_p"] == sonnet_result["tier_p"] else "DISAGREE"
            print(f"    sonnet={sonnet_result['tier_p']}  [{agreement}]", flush=True)
        except Exception as exc:
            print(f"    ERROR: {exc}", file=sys.stderr)
            # Still add to record
            sonnet_results.append({
                "trial_id": trial["trial_id"],
                "pmid": pmid,
                "tier_p": "ERROR",
                "opus_tier_p": trial["tier_p"],
                "error": str(exc),
            })

    # Compute kappa (only on trials where both gave definitive labels)
    definitive_pairs = [
        (o, s) for o, s in zip(opus_labels, sonnet_labels)
        if o in ("african_majority", "not_african_majority")
        and s in ("african_majority", "not_african_majority")
    ]
    kappa_pairs_n = len(definitive_pairs)

    if kappa_pairs_n == 0:
        kappa = float("nan")
        n_agree = 0
    else:
        opus_def = [p[0] for p in definitive_pairs]
        sonnet_def = [p[1] for p in definitive_pairs]
        kappa = _cohen_kappa(opus_def, sonnet_def)
        n_agree = sum(1 for o, s in definitive_pairs if o == s)

    kappa_threshold = 0.6
    if kappa != kappa and kappa_pairs_n == 0:
        verdict = "STOP"
        verdict_reason = "No evaluable pairs for kappa computation"
    elif kappa >= kappa_threshold:
        verdict = "PROCEED"
        verdict_reason = f"kappa={kappa:.3f} >= threshold {kappa_threshold}"
    else:
        verdict = "STOP"
        verdict_reason = f"kappa={kappa:.3f} < threshold {kappa_threshold} — sonnet too divergent from opus"

    report = {
        "spec_version": "v0.2",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "opus_model": opus_model,
        "sonnet_model": sonnet_model,
        "n_calibration_trials": len(cal_trials),
        "n_evaluated": len(sonnet_results),
        "n_definitive_pairs": kappa_pairs_n,
        "n_agree": n_agree,
        "kappa": round(kappa, 4) if kappa == kappa else None,
        "kappa_threshold": kappa_threshold,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "trial_results": sonnet_results,
    }

    _OUT_REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n--- CALIBRATION RESULT ---")
    print(f"n_definitive_pairs: {kappa_pairs_n}")
    print(f"n_agree:            {n_agree}")
    print(f"kappa:              {kappa:.3f}" if kappa == kappa else "kappa: NaN")
    print(f"verdict:            {verdict}")
    print(f"reason:             {verdict_reason}")
    print(f"report:             {_OUT_REPORT}")

    if verdict == "STOP":
        print("\nSTOP — do not proceed with pilot batch.", file=sys.stderr)
        return 1

    print("\nPROCEED — kappa meets threshold. Pilot batch may proceed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
