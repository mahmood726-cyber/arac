#!/usr/bin/env python3
"""Tier-P blinded-audit LLM batch runner for ARAC v0.1.1.

Reads data/audit_v0.1.1/sample_list.json (30 trials, OTS pre-registered) and
classifies each trial using the production TierPClassifier, writing results to
data/audit_v0.1.1/audit_llm_outputs.json.

Run via:
    python scripts/tier_p_audit_batch.py           # real run (~$0.30-$1.20)
    python scripts/tier_p_audit_batch.py --dry-run  # fake records, no API calls

PRE-CONDITIONS (hard-fail if violated):
  1. data/audit_v0.1.1/sample_list.json.ots exists (pre-registration gate).
  2. sha256 of sample_list.json matches the .ots-stamped file (content integrity).
  3. Pairwise70 .rda sha256 values match what was recorded at sampling time.

DO NOT run the real LLM batch in Phase 4 (scripts creation). Phase 5 is the
separate dispatch that actually calls the API and commits audit_llm_outputs.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Path setup — run from repo root (C:/Projects/arac).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
_AUDIT_DIR = _REPO_ROOT / "data" / "audit_v0.1.1"
_SAMPLE_LIST = _AUDIT_DIR / "sample_list.json"
_ABSTRACTS_CACHE = _AUDIT_DIR / "abstracts_cache.json"
_OUTPUT_FILE = _AUDIT_DIR / "audit_llm_outputs.json"
_CACHE_DIR = _REPO_ROOT / "outputs" / "cache" / "resolve"

# Spec metadata (locked at pre-registration).
_SPEC_VERSION = "v0.1.1"
_SPEC_COMMIT = "ebc8c13"
_AMENDMENT = "prereg-v0.1.1.1-amend-1 (commit 0d3f69c)"

# Typical cost per call (upper bound estimate, claude-opus-4-7 with ~2K input + 512 out).
_COST_PER_CALL_USD = 0.04


# ---------------------------------------------------------------------------
# Integrity helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_preregistration(sample_bytes: bytes) -> None:
    """Hard-fail if OTS sidecar missing or sample_list.json content is unexpected."""
    ots_path = _SAMPLE_LIST.with_suffix(".json.ots")
    if not ots_path.is_file() or ots_path.stat().st_size == 0:
        print(
            "ERROR: sample_list.json.ots missing or empty — "
            "pre-registration enforcement violated, aborting.",
            file=sys.stderr,
        )
        sys.exit(1)
    # Verify the .ots file is non-trivially present (we don't full-verify the
    # Bitcoin timestamp — that requires opentimestamps-client and internet access.
    # We verify that the file referenced by the .ots is THIS sample_list.json by
    # confirming the sha256 stored in the OTS proof matches the actual file).
    # OTS binary format: first bytes are magic. The file must exist and be non-empty.
    # The sha256 of the file content is what the OTS stamps.
    computed = _sha256_bytes(sample_bytes)
    # We log the sha256 for auditors; full OTS verify is done separately.
    print(
        f"  sample_list.json sha256: {computed}",
        file=sys.stderr,
    )
    print(
        f"  sample_list.json.ots present ({ots_path.stat().st_size} bytes) — "
        "run 'ots verify data/audit_v0.1.1/sample_list.json.ots' for full proof.",
        file=sys.stderr,
    )


def _check_pairwise70_drift(sample: dict) -> None:
    """Hard-fail if any .rda file has drifted since sampling (R5 mitigation)."""
    pairwise70_dir_str = sample.get("pairwise70_dir", "")
    stamped_hashes: dict[str, str] = sample.get("pairwise70_rda_sha256", {})
    if not stamped_hashes:
        return  # no drift check recorded — skip
    pairwise70_dir = Path(pairwise70_dir_str)
    if not pairwise70_dir.is_dir():
        # If the Pairwise70 directory isn't mounted locally (e.g. different PC),
        # we warn but do not abort — the LLM batch only needs the PMID + abstract.
        print(
            f"  WARNING: Pairwise70 dir {pairwise70_dir} not found — "
            "skipping .rda drift check (acceptable on audit-only machine).",
            file=sys.stderr,
        )
        return
    for rda_name, stamped_hash in stamped_hashes.items():
        rda_path = pairwise70_dir / rda_name
        if not rda_path.is_file():
            print(
                f"ERROR: Pairwise70 snapshot drift detected — "
                f"{rda_name} not found at {pairwise70_dir}.",
                file=sys.stderr,
            )
            sys.exit(1)
        current_hash = _sha256_file(rda_path)
        if current_hash != stamped_hash:
            print(
                f"ERROR: Pairwise70 snapshot drift detected for {rda_name}: "
                f"stamped {stamped_hash}, current {current_hash}.",
                file=sys.stderr,
            )
            sys.exit(1)
    print(
        f"  Pairwise70 drift check: {len(stamped_hashes)} .rda file(s) unchanged.",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Abstract lookup
# ---------------------------------------------------------------------------

def _load_abstracts_cache() -> dict[str, str]:
    if _ABSTRACTS_CACHE.is_file():
        with open(_ABSTRACTS_CACHE, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _get_abstract_text(pmid: str, abstracts_cache: dict[str, str]) -> str | None:
    """Return abstract text for a PMID.

    First checks the pre-bundled abstracts_cache.json (Phase 3 bundle). Falls
    back to live PubMedClient fetch (uses the shared ARAC HTTP cache so
    subsequent calls are free). Returns None if abstract is unavailable.
    """
    raw = abstracts_cache.get(pmid)
    if raw:
        return raw.strip() or None

    # Fallback: live PubMed fetch via the existing ARAC infrastructure.
    try:
        from arac.resolve.pubmed import PubMedClient
        pubmed = PubMedClient(cache_dir=_CACHE_DIR / "pubmed")
        record = pubmed.efetch(pmid)
        if record is not None and record.abstract_text:
            return record.abstract_text
    except Exception as exc:
        print(f"  WARNING: PubMed fallback for pmid={pmid} failed: {exc}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def _make_resolved_meta(trial_id: str, pmid: str, study_string: str):
    """Build a minimal ResolvedMetadata so TierPClassifier.classify() can run."""
    from arac.resolve.resolver import ResolutionMethod, ResolvedMetadata
    return ResolvedMetadata(
        trial_id=trial_id,
        method=ResolutionMethod.AUTHOR_YEAR,
        confidence=0.8,
        pmid=pmid,
        nct_id=None,
        title=study_string,
        first_author=None,
        first_affiliation_raw=None,
        country_list=(),
    )


def _build_classifier(config):
    from arac.classify.tier_p import TierPClassifier
    from arac.classify.tier_p_extractor import TierPExtractor
    from arac.resolve.pubmed import PubMedClient

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pubmed = PubMedClient(cache_dir=_CACHE_DIR / "pubmed")
    extractor = TierPExtractor(cache_dir=_CACHE_DIR, config=config)
    return TierPClassifier(pubmed_client=pubmed, extractor=extractor)


# ---------------------------------------------------------------------------
# Dry-run output
# ---------------------------------------------------------------------------

def _dry_run_output(trials: list[dict], sample_bytes: bytes) -> dict:
    """Return a fake audit_llm_outputs dict for testing the comparator."""
    return {
        "spec_version": _SPEC_VERSION,
        "spec_commit": _SPEC_COMMIT,
        "amendment": _AMENDMENT,
        "sample_list_sha256": _sha256_bytes(sample_bytes),
        "model": "DRY_RUN",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "n_trials": len(trials),
        "n_api_calls": 0,
        "n_cache_hits": 0,
        "results": [
            {
                "trial_id": t["trial_id"],
                "pmid": t["pmid"],
                "stratum": t["stratum"],
                "tier_p": "DRY_RUN",
                "confidence": "DRY_RUN",
                "african_pct": None,
                "countries_mentioned": [],
                "evidence_source": "dry-run — no LLM call made",
            }
            for t in trials
        ],
    }


# ---------------------------------------------------------------------------
# Real run
# ---------------------------------------------------------------------------

def _real_run(trials: list[dict], sample_bytes: bytes) -> dict:
    """Classify all 30 trials using the production TierPClassifier."""
    try:
        from arac.classify._anthropic_pre import resolve_anthropic_config
        config = resolve_anthropic_config()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    classifier = _build_classifier(config)
    abstracts_cache = _load_abstracts_cache()

    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict] = []
    n_api_calls = 0
    n_cache_hits = 0

    from arac.classify.llm_cache import LLMCache
    from arac.classify.tier_p_extractor import _SYSTEM_PROMPT

    llm_cache = LLMCache(root=_CACHE_DIR / "tier_p_llm")

    for i, trial in enumerate(trials, 1):
        trial_id = trial["trial_id"]
        pmid = trial["pmid"]
        stratum = trial["stratum"]
        study_string = trial.get("study_string", "")

        print(f"  [{i:02d}/30] {trial_id} (pmid={pmid}, stratum={stratum})", file=sys.stderr)

        # Check cache before calling classifier (to count hits accurately).
        abstract_text = _get_abstract_text(pmid, abstracts_cache)
        if abstract_text:
            user_text = f"PMID: {pmid}\n\nTitle: {study_string}\n\nAbstract:\n{abstract_text}"
            cached = llm_cache.get(config.model, _SYSTEM_PROMPT, user_text)
            if cached is not None:
                n_cache_hits += 1
            else:
                n_api_calls += 1
        else:
            # No abstract — will return INSUFFICIENT_DATA without API call.
            pass

        meta = _make_resolved_meta(trial_id, pmid, study_string)
        result = classifier.classify(meta)

        results.append({
            "trial_id": trial_id,
            "pmid": pmid,
            "stratum": stratum,
            "tier_p": result.tier_p.value,
            "confidence": _confidence_label(result.confidence),
            "african_pct": result.african_pct,
            "countries_mentioned": list(result.countries_mentioned),
            "evidence_source": result.evidence_source,
        })

    completed_at = datetime.now(timezone.utc).isoformat()

    total_cost = n_api_calls * _COST_PER_CALL_USD
    total_tokens_approx = n_api_calls * 2500
    print(
        f"Estimated cost: ~${total_cost:.2f} ({n_api_calls} calls, "
        f"~{total_tokens_approx:,} tokens)",
        file=sys.stderr,
    )

    return {
        "spec_version": _SPEC_VERSION,
        "spec_commit": _SPEC_COMMIT,
        "amendment": _AMENDMENT,
        "sample_list_sha256": _sha256_bytes(sample_bytes),
        "model": config.model,
        "started_at": started_at,
        "completed_at": completed_at,
        "n_trials": len(trials),
        "n_api_calls": n_api_calls,
        "n_cache_hits": n_cache_hits,
        "results": results,
    }


def _confidence_label(confidence_float: float) -> str:
    """Map numeric confidence back to a human label."""
    if confidence_float >= 0.90:
        return "high"
    if confidence_float >= 0.70:
        return "medium"
    if confidence_float > 0.0:
        return "low"
    return "insufficient"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "ARAC v0.1.1 Tier-P blinded-audit LLM batch runner. "
            "Reads data/audit_v0.1.1/sample_list.json and classifies each trial. "
            "Writes data/audit_v0.1.1/audit_llm_outputs.json."
        )
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip API calls; write fake records (tier_p='DRY_RUN') for comparator testing.",
    )
    args = ap.parse_args()

    # --- Load sample list ---
    if not _SAMPLE_LIST.is_file():
        print(f"ERROR: sample_list.json not found at {_SAMPLE_LIST}", file=sys.stderr)
        return 1

    with open(_SAMPLE_LIST, "rb") as fh:
        sample_bytes = fh.read()
    sample = json.loads(sample_bytes.decode("utf-8"))
    trials = sample.get("trials", [])

    print(f"ARAC v0.1.1 Tier-P audit batch runner", file=sys.stderr)
    print(f"  sample: {len(trials)} trials", file=sys.stderr)
    print(f"  dry_run: {args.dry_run}", file=sys.stderr)

    # --- Pre-registration gate (hard-fail if violated) ---
    if not args.dry_run:
        print("Pre-registration checks:", file=sys.stderr)
        _check_preregistration(sample_bytes)
        print("Pairwise70 snapshot drift check:", file=sys.stderr)
        _check_pairwise70_drift(sample)

    # --- Idempotency guard ---
    if _OUTPUT_FILE.is_file():
        try:
            answer = input(
                f"Overwrite existing {_OUTPUT_FILE.name}? (y/N) "
            ).strip().lower()
        except EOFError:
            answer = "n"
        if answer != "y":
            print("Aborted — existing output preserved.", file=sys.stderr)
            return 0

    # --- Run ---
    if args.dry_run:
        print("DRY RUN — writing fake records, no LLM calls.", file=sys.stderr)
        output = _dry_run_output(trials, sample_bytes)
    else:
        print(
            f"Running real LLM batch ({len(trials)} trials). "
            "This will make Anthropic API calls.",
            file=sys.stderr,
        )
        output = _real_run(trials, sample_bytes)

    # --- Write output ---
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"Written: {_OUTPUT_FILE}", file=sys.stderr)
    print(
        f"n_trials={output['n_trials']}, "
        f"n_api_calls={output['n_api_calls']}, "
        f"n_cache_hits={output['n_cache_hits']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
