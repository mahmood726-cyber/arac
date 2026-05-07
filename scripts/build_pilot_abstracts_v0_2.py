"""Phase 5a — Resolve PMIDs and fetch abstracts for all trials in the v0.2 pilot sample.

Loads all 100 sampled MAs, resolves each trial's Study string to a PMID,
fetches the abstract, and outputs a cache file for the LLM classification step.

Usage:
    cd <arac repo root>
    python scripts/build_pilot_abstracts_v0_2.py

Output: data/v0.2/pilot_trial_index.json  — dict keyed by unique_key=(ma_id, trial_index)
    Each value: {pmid, abstract_text, study_string, ma_id, trial_index, stratum}
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyreadr

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_SCRIPT_DIR))

from arac.bridge import TrialRow
from arac.resolve.pubmed import PubMedClient
from arac.resolve.resolver import StudyResolver

_OUT_DIR = _REPO_ROOT / "data" / "v0.2"
_SAMPLE_JSON = _OUT_DIR / "sample_list_pilot.json"
_OUT_INDEX = _OUT_DIR / "pilot_trial_index.json"


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
    raise SystemExit("Pairwise70 data directory not found. Set PAIRWISE70_DIR env var.")


def main() -> int:
    if _OUT_INDEX.is_file():
        data = json.loads(_OUT_INDEX.read_text(encoding="utf-8"))
        n = len(data.get("trials", {}))
        print(f"pilot_trial_index.json already exists with {n} trials. Skipping.")
        return 0

    sample = json.loads(_SAMPLE_JSON.read_text(encoding="utf-8"))
    ma_list = sample["ma_list"]
    pairwise70_dir = _data_dir()

    cache_dir = _REPO_ROOT / "outputs" / "cache" / "resolve"
    cache_dir.mkdir(parents=True, exist_ok=True)
    resolver = StudyResolver(cache_dir=cache_dir)
    pubmed = PubMedClient(cache_dir=cache_dir / "pubmed")

    trials: dict[str, dict] = {}  # key = f"{ma_id}::t{trial_index}"

    total_mas = len(ma_list)
    n_resolved = 0
    n_failed = 0

    for ma_idx, m in enumerate(ma_list):
        ma_id = m["ma_id"]
        rda_fn = m["rda_filename"]
        stratum = m["stratum"]

        parts = ma_id.split("__A")
        an = int(parts[1])

        try:
            bundle = pyreadr.read_r(str(pairwise70_dir / rda_fn))
            df = next(iter(bundle.values()))
        except Exception as e:
            print(f"  WARN: cannot read {rda_fn}: {e}", file=sys.stderr)
            continue

        sub = df[df["Analysis.number"] == an].reset_index(drop=True)
        studies = sub["Study"].astype(str).tolist()

        print(
            f"[{ma_idx + 1}/{total_mas}] {ma_id}  k={len(studies)}",
            flush=True,
        )

        for trial_index, study_string in enumerate(studies):
            trial_id = f"{ma_id}::t{trial_index}"

            if trial_id in trials:
                continue  # already resolved

            row = TrialRow(
                ma_id=ma_id,
                trial_index=trial_index,
                trial_id=trial_id,
                data_type="unknown",
                k_total=len(studies),
            )

            try:
                meta = resolver.resolve(row, study_string)
            except Exception as exc:
                print(f"  resolver error {trial_id}: {exc}", file=sys.stderr)
                trials[trial_id] = {
                    "ma_id": ma_id,
                    "trial_index": trial_index,
                    "study_string": study_string,
                    "stratum": stratum,
                    "pmid": None,
                    "abstract_text": None,
                    "resolve_error": str(exc),
                }
                n_failed += 1
                continue

            if meta.pmid is None:
                trials[trial_id] = {
                    "ma_id": ma_id,
                    "trial_index": trial_index,
                    "study_string": study_string,
                    "stratum": stratum,
                    "pmid": None,
                    "abstract_text": None,
                    "resolve_error": "no_pmid",
                }
                n_failed += 1
                continue

            try:
                rec = pubmed.efetch(meta.pmid)
            except Exception as exc:
                print(f"  pubmed error pmid={meta.pmid}: {exc}", file=sys.stderr)
                trials[trial_id] = {
                    "ma_id": ma_id,
                    "trial_index": trial_index,
                    "study_string": study_string,
                    "stratum": stratum,
                    "pmid": meta.pmid,
                    "abstract_text": None,
                    "resolve_error": "pubmed_fetch_error",
                }
                n_failed += 1
                continue

            abstract_text = rec.abstract_text if rec else None
            trials[trial_id] = {
                "ma_id": ma_id,
                "trial_index": trial_index,
                "study_string": study_string,
                "stratum": stratum,
                "pmid": meta.pmid,
                "abstract_text": abstract_text,
                "resolve_error": None if abstract_text else "no_abstract",
            }

            if abstract_text:
                n_resolved += 1
            else:
                n_failed += 1

    output = {
        "spec_version": "v0.2",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_trials_total": len(trials),
        "n_resolved_with_abstract": n_resolved,
        "n_failed": n_failed,
        "trials": trials,
    }

    _OUT_INDEX.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {_OUT_INDEX}")
    print(f"  n_resolved={n_resolved}  n_failed={n_failed}  total={len(trials)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
