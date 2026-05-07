"""Phase 5b — Classify all pilot trials with sonnet and compute atlas.

Reads pilot_trial_index.json, classifies each unique (pmid, abstract) with the
production Tier-P system prompt, and writes:
  - data/v0.2/sonnet_extractions.json  (per-trial LLM output)
  - data/v0.2/atlas_pilot.csv          (100-row RGS atlas)

Usage:
    cd <arac repo root>
    ARAC_TIER_P_MODEL=claude-sonnet-4-6 python scripts/run_pilot_batch_v0_2.py

The script is designed to be re-runnable: already-classified trials are read
from the per-PMID cache in data/v0.2/.cache/ and skipped. A failed batch can
be resumed by re-running the script.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pyreadr

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_SCRIPT_DIR))

from arac.bridge import load_all_mas, MARecord
from arac.rgs.csv_writer import write_rgs_rows
from arac.rgs.engine import RGSEngine, RGSTier

_OUT_DIR = _REPO_ROOT / "data" / "v0.2"
_TRIAL_INDEX = _OUT_DIR / "pilot_trial_index.json"
_EXTRACTIONS = _OUT_DIR / "sonnet_extractions.json"
_ATLAS = _OUT_DIR / "atlas_pilot.csv"
_CACHE_DIR = _OUT_DIR / ".cache"

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


def _classify_with_llm(pmid: str, abstract_text: str, api_key: str, model: str) -> dict:
    """Classify one abstract. Returns Tier-P dict. Raises on API error."""
    import anthropic
    from pydantic import BaseModel, Field
    from typing import Literal

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


def _load_pmid_cache(pmid: str) -> Optional[dict]:
    cache_path = _CACHE_DIR / f"{pmid}.json"
    if cache_path.is_file():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    return None


def _save_pmid_cache(pmid: str, result: dict) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _CACHE_DIR / f"{pmid}.json"
    cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def _data_dir() -> Path:
    env = os.environ.get("PAIRWISE70_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    for candidate in [
        "C:/Projects/Pairwise70/data",  # sentinel:skip-line P0-hardcoded-local-path
        "D:/Projects/Pairwise70/data",  # sentinel:skip-line P0-hardcoded-local-path
    ]:
        p = Path(candidate)
        if p.is_dir():
            return p
    raise SystemExit("Pairwise70 data directory not found.")


def main() -> int:
    # Load trial index
    if not _TRIAL_INDEX.is_file():
        print(f"ERROR: {_TRIAL_INDEX} not found. Run build_pilot_abstracts_v0_2.py first.", file=sys.stderr)
        return 1

    index = json.loads(_TRIAL_INDEX.read_text(encoding="utf-8"))
    trials = index["trials"]

    api_key = (
        os.environ.get("ARAC_ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        return 1

    model = os.environ.get("ARAC_TIER_P_MODEL", "claude-sonnet-4-6")
    print(f"Model: {model}")
    print(f"Total trials in index: {len(trials)}")

    # Build unique PMID → abstract mapping
    pmid_to_abstract: dict[str, str] = {}
    for trial_id, t in trials.items():
        pmid = t.get("pmid")
        abstract = t.get("abstract_text")
        if pmid and abstract:
            pmid_to_abstract[pmid] = abstract

    print(f"Unique PMIDs with abstracts: {len(pmid_to_abstract)}")

    # Classify each unique PMID (with per-PMID cache)
    pmid_results: dict[str, dict] = {}
    n_cached = 0
    n_classified = 0
    n_errors = 0

    for i, (pmid, abstract) in enumerate(sorted(pmid_to_abstract.items()), 1):
        cached = _load_pmid_cache(pmid)
        if cached is not None:
            pmid_results[pmid] = cached
            n_cached += 1
            continue

        print(f"  [{i}/{len(pmid_to_abstract)}] Classifying pmid={pmid}...", flush=True)
        try:
            result = _classify_with_llm(pmid, abstract, api_key, model)
            _save_pmid_cache(pmid, result)
            pmid_results[pmid] = result
            n_classified += 1
            print(f"    tier_p={result['tier_p']}  african_pct={result['african_pct']}", flush=True)
        except Exception as exc:
            print(f"    ERROR: {exc}", file=sys.stderr)
            error_result = {
                "pmid": pmid,
                "tier_p": "error",
                "confidence": "insufficient",
                "african_pct": None,
                "non_african_pct": None,
                "countries_mentioned": [],
                "evidence_source": None,
                "reasoning": f"API error: {exc}",
                "error": str(exc),
            }
            pmid_results[pmid] = error_result
            n_errors += 1

    print(f"\nClassification complete: {n_cached} cached + {n_classified} new + {n_errors} errors")

    # Build per-trial results
    trial_results = []
    for trial_id, t in trials.items():
        pmid = t.get("pmid")
        if pmid and pmid in pmid_results:
            r = dict(pmid_results[pmid])
            r["trial_id"] = trial_id
            r["ma_id"] = t["ma_id"]
            r["trial_index"] = t["trial_index"]
            r["study_string"] = t["study_string"]
            r["stratum"] = t["stratum"]
        else:
            r = {
                "trial_id": trial_id,
                "ma_id": t["ma_id"],
                "trial_index": t["trial_index"],
                "study_string": t["study_string"],
                "stratum": t["stratum"],
                "pmid": pmid,
                "tier_p": "insufficient_data",
                "confidence": "insufficient",
                "african_pct": None,
                "non_african_pct": None,
                "countries_mentioned": [],
                "evidence_source": None,
                "reasoning": "No abstract resolved",
                "error": t.get("resolve_error"),
            }
        trial_results.append(r)

    # Write sonnet_extractions.json
    extractions_out = {
        "spec_version": "v0.2",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "n_trials": len(trial_results),
        "n_unique_pmids": len(pmid_to_abstract),
        "n_cached": n_cached,
        "n_classified": n_classified,
        "n_errors": n_errors,
        "results": trial_results,
    }
    _EXTRACTIONS.write_text(
        json.dumps(extractions_out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {_EXTRACTIONS}")

    # --- Phase 6: Compute RGS atlas ---
    print("\n--- Phase 6: Computing RGS atlas ---")
    pairwise70_dir = _data_dir()

    # Build ma_id → african_trial_indices from sonnet results
    ma_african: dict[str, list[int]] = defaultdict(list)
    for r in trial_results:
        if r.get("tier_p") == "african_majority":
            ma_african[r["ma_id"]].append(r["trial_index"])

    # Load sample MA list
    sample = json.loads((Path(_OUT_DIR) / "sample_list_pilot.json").read_text(encoding="utf-8"))
    sampled_ma_ids = [m["ma_id"] for m in sample["ma_list"]]

    # Load Pairwise70 MA records
    print("Loading MARecords from Pairwise70...")
    all_mas = load_all_mas(pairwise70_dir, max_reviews=None)
    ma_lookup: dict[str, MARecord] = {m.ma_id: m for m in all_mas}
    print(f"  Loaded {len(ma_lookup)} total MAs")

    engine = RGSEngine()
    rgs_rows = []

    for ma_id in sampled_ma_ids:
        record = ma_lookup.get(ma_id)
        if record is None:
            print(f"  WARN: {ma_id} not found in Pairwise70 — skipping", file=sys.stderr)
            continue

        african_indices = tuple(sorted(ma_african.get(ma_id, [])))
        result = engine.compute(record, RGSTier.PARTICIPANT, african_indices)
        rgs_rows.append(result)

    n_written = write_rgs_rows(rgs_rows, _ATLAS)
    print(f"Wrote {n_written} rows to {_ATLAS}")

    # Summary
    n_invisible = sum(1 for r in rgs_rows if r.invisible)
    n_visible = sum(1 for r in rgs_rows if not r.invisible)
    n_sign_flip = sum(1 for r in rgs_rows if r.sign_flip is True)
    n_repro_gap = sum(1 for r in rgs_rows if r.reproduction_gap is True)

    print(f"\n=== PILOT ATLAS SUMMARY ===")
    print(f"Total MAs: {len(rgs_rows)}")
    print(f"Visible (k_subset >= 3): {n_visible}")
    print(f"Invisible (k_subset < 3): {n_invisible}")
    if n_visible > 0:
        print(f"Sign flips (visible only): {n_sign_flip}/{n_visible}")
        print(f"Reproduction gap (visible): {n_repro_gap}/{n_visible}")
    else:
        print("WARNING: all MAs invisible — enrichment strategy needs revision (R14)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
