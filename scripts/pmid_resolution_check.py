"""pmid_resolution_check.py — ARAC v0.1.2 R9 mitigation.

Compares the resolved PubMed abstract's title/first-author against the
study_string author-year for each trial in sample_list.json.  Flags
mismatches so upstream Pairwise70 PMID linkage errors can be documented.

CLI:
    python scripts/pmid_resolution_check.py [--sample-list <path>] [--output <path>]
    python scripts/pmid_resolution_check.py --fetch-live  # enables live PubMed API (opt-in)

Defaults:
    --sample-list  data/audit_v0.1.1/sample_list.json
    --output       data/audit_v0.1.1/pmid_resolution_report.json

No live fetches unless --fetch-live is given.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# Matches:  "Sagara 2018 ..."  "de Thurah 2018"  "De La Roque 2011"  "Etherton-Beer 2023"
_STUDY_STRING_RE = re.compile(
    r"^((?:de |De |van |Van |du |Du |le |Le )?"
    r"[A-Z][a-zA-Zäöüéèàâêîôûç\-']+"   # hyphenated single-word surnames e.g. Etherton-Beer
    r"(?:\s+[A-Z][a-zA-Zäöüéèàâêîôûç\-']+)*)"  # optional extra caps words
    r"\s+(\d{4})"
)


def parse_study_string(study_string: str) -> Tuple[Optional[str], Optional[int]]:
    """Return (surname, year) or (None, None) if pattern not matched.

    For compound surnames like "de Thurah" or "De La Roque", the full
    compound is returned as the parsed surname.  The caller uses case-
    insensitive substring matching so "Thurah" will still be found inside
    "de Thurah" when checking a PubMed title.
    """
    m = _STUDY_STRING_RE.match(study_string.strip())
    if not m:
        return None, None
    surname = m.group(1).strip()
    year = int(m.group(2))
    return surname, year


# ---------------------------------------------------------------------------
# Abstracts-cache helpers
# ---------------------------------------------------------------------------

# Regex patterns for parsing the flat PubMed text format stored in the cache.
# Format example:
#   1. Am J Case Rep. 2018 Dec 27;19:1530-1535. doi: ...
#
#   Title line.
#
#   Author A(1), Author B(2), ...
_CITATION_LINE_RE = re.compile(
    r"^\d+\.\s+.+?(\d{4})\s+"
)
_YEAR_IN_CITATION_RE = re.compile(
    r"^\d+\.\s+\S.*?(\b(?:19|20)\d{2})\b"
)
_DOI_LINE_RE = re.compile(r"^\d+\.\s+.+doi:", re.IGNORECASE)


def _extract_title_and_year_from_text(text: str) -> Tuple[Optional[str], Optional[int]]:
    """Parse a raw PubMed efetch text record into (title, year).

    The format is:
        1. <journal>. <year> <month>;<volume>(<issue>):<pages>. doi: ...
        [blank line]
        <Title line(s)>.
        [blank line]
        <Author A(1), Author B(2), ...>

    The year is extracted from the citation line.
    The title is the first non-blank text block after the citation line.
    """
    lines = text.strip().splitlines()
    year: Optional[int] = None
    title_lines: list[str] = []
    state = "citation"

    for line in lines:
        stripped = line.strip()
        if state == "citation":
            # The first line is the citation line; extract year from it
            m = _YEAR_IN_CITATION_RE.match(stripped)
            if m:
                year = int(m.group(1))
            state = "blank_after_citation"
            continue

        if state == "blank_after_citation":
            if stripped == "":
                state = "title"
            # Some records have multi-line citations — keep scanning
            else:
                # Could still be part of the citation (wrapped)
                if not year:
                    m = re.search(r"\b(19|20)\d{2}\b", stripped)
                    if m:
                        year = int(m.group(0))
                # If the line ends with a period, it might be the title
                # starting right after the citation with no blank line.
                # We stay in this state.
            continue

        if state == "title":
            if stripped == "":
                if title_lines:
                    break  # end of title block
                # else: extra blank line, still waiting for title
            else:
                title_lines.append(stripped)

    title = " ".join(title_lines).rstrip(".") if title_lines else None
    return title, year


def _extract_first_author_surname_from_text(text: str) -> Optional[str]:
    """Extract the first author's surname from a raw PubMed text record.

    Author line format:  Surname AB(1), Second CD(2), ...
    We look for the first line that matches the author pattern (after the
    title block).
    """
    lines = text.strip().splitlines()
    # Skip citation + blank + title + blank; then first non-blank is authors
    state = "citation"
    passed_title = False

    for line in lines:
        stripped = line.strip()

        if state == "citation":
            state = "after_citation"
            continue

        if state == "after_citation":
            if stripped == "":
                state = "title"
            continue

        if state == "title":
            if stripped == "":
                state = "after_title"
            continue

        if state == "after_title":
            if stripped == "":
                continue
            # This should be the author line
            # Pattern: Surname AB(1), ...  OR  Surname AB, ...
            m = re.match(r"^([A-Z][a-zA-Zäöüéèàâêîôûç'\- ]+?)\s+[A-Z]{1,4}(?:\(\d+\))?[,.]", stripped)
            if m:
                return m.group(1).strip()
            # Fallback: first word if capitalised
            first_word = stripped.split()[0] if stripped.split() else None
            if first_word and first_word[0].isupper():
                return first_word
            return None

    return None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

CLASSIFICATIONS = (
    "match",
    "surname_mismatch",
    "year_mismatch",
    "both_mismatch",
    "parse_failed",
    "no_pubmed_data",
)


def classify_trial(
    *,
    parsed_surname: Optional[str],
    parsed_year: Optional[int],
    pubmed_title: Optional[str],
    pubmed_first_author: Optional[str],
    pubmed_year: Optional[int],
    pubmed_full_text: Optional[str] = None,
) -> Tuple[str, str]:
    """Return (classification, explanation).

    Surname matching strategy (in priority order):
    1. Exact substring in the PubMed title (case-insensitive).
    2. Match against the extracted first-author surname.
    3. Substring in the *full* PubMed text (catches non-first-author study labels,
       which are a legitimate Cochrane convention — e.g. Ringwald 1998 is second
       author on PMID 9790433).  A hit here is still classified as "match".

    Only when the surname is absent from ALL three sources is it flagged as
    surname_mismatch / both_mismatch.  This avoids false-positives for the
    common pattern where a Cochrane review labels a trial by a non-first author.
    """

    if parsed_surname is None:
        return "parse_failed", "study_string did not match author-year regex"

    if pubmed_title is None and pubmed_first_author is None and pubmed_year is None:
        return "no_pubmed_data", "PMID not in abstracts cache and live fetch disabled"

    # Surname check: case-insensitive substring in title OR match against
    # first-author surname (last word of the parsed compound).
    surname_parts = parsed_surname.lower().split()
    last_part = surname_parts[-1]  # e.g. "thurah" from "de Thurah"

    surname_in_title = False
    if pubmed_title:
        title_lower = pubmed_title.lower()
        surname_in_title = (
            parsed_surname.lower() in title_lower
            or last_part in title_lower
        )

    surname_in_first_author = False
    if pubmed_first_author:
        auth_lower = pubmed_first_author.lower()
        surname_in_first_author = (
            parsed_surname.lower() in auth_lower
            or last_part in auth_lower
        )

    # Fallback: check full text (covers non-first-author labels)
    surname_in_full_text = False
    if pubmed_full_text and not (surname_in_title or surname_in_first_author):
        full_lower = pubmed_full_text.lower()
        surname_in_full_text = (
            parsed_surname.lower() in full_lower
            or last_part in full_lower
        )

    surname_ok = surname_in_title or surname_in_first_author or surname_in_full_text

    year_ok = False
    if pubmed_year is not None and parsed_year is not None:
        year_ok = abs(pubmed_year - parsed_year) <= 1

    if surname_ok and year_ok:
        where = (
            "title" if surname_in_title
            else ("first-author" if surname_in_first_author else "author-list")
        )
        return "match", (
            f"surname '{parsed_surname}' found in {where}, "
            f"year {parsed_year} ≈ {pubmed_year}"
        )
    elif not surname_ok and not year_ok:
        return "both_mismatch", (
            f"surname '{parsed_surname}' not found in title, authors, or full text; "
            f"year {parsed_year} vs pubmed {pubmed_year}"
        )
    elif not surname_ok:
        return "surname_mismatch", (
            f"surname '{parsed_surname}' absent from title, authors, and full text; "
            f"year ok ({parsed_year} ≈ {pubmed_year})"
        )
    else:
        return "year_mismatch", (
            f"surname ok; year {parsed_year} vs pubmed {pubmed_year} (|Δ|>1)"
        )


# ---------------------------------------------------------------------------
# Live PubMed fetch (opt-in only)
# ---------------------------------------------------------------------------

_NCBI_BASE = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    "?db=pubmed&rettype=abstract&retmode=text&id="
)
_FETCH_DELAY = 0.35  # seconds between requests (NCBI guideline: ≤3/s)


def fetch_pubmed_text(pmid: str) -> Optional[str]:
    """Fetch raw PubMed abstract text for a PMID.  May raise or return None."""
    url = _NCBI_BASE + pmid
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "arac-pmid-check/0.1.2"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        time.sleep(_FETCH_DELAY)
        return text if text.strip() else None
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] live fetch failed for PMID {pmid}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# SHA256 helper
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_short_sha(repo: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(repo)
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def run_check(
    sample_list_path: Path,
    abstracts_cache_path: Path,
    fetch_live: bool,
) -> dict:
    """Run the PMID resolution check and return the report dict."""

    # --- load inputs ---
    with sample_list_path.open(encoding="utf-8") as fh:
        sample_data = json.load(fh)
    trials_raw = sample_data.get("trials", [])

    cache: dict[str, str] = {}
    if abstracts_cache_path.exists():
        with abstracts_cache_path.open(encoding="utf-8") as fh:
            cache = json.load(fh)

    repo_root = sample_list_path.parents[2]  # arac/
    spec_commit = _git_short_sha(repo_root)
    sample_sha = _sha256_file(sample_list_path)

    trial_results = []
    summary: dict[str, int] = {k: 0 for k in CLASSIFICATIONS}

    for trial in trials_raw:
        trial_id = trial.get("trial_id", "")
        pmid = str(trial.get("pmid", "")).strip()
        study_string = trial.get("study_string", "")

        # 1. Parse study_string
        parsed_surname, parsed_year = parse_study_string(study_string)

        # 2. Get PubMed data from cache (or live fetch if opted in)
        pubmed_text: Optional[str] = cache.get(pmid)
        if pubmed_text is None and fetch_live and pmid:
            pubmed_text = fetch_pubmed_text(pmid)

        pubmed_title: Optional[str] = None
        pubmed_first_author: Optional[str] = None
        pubmed_year: Optional[int] = None

        if pubmed_text:
            pubmed_title, pubmed_year = _extract_title_and_year_from_text(pubmed_text)
            pubmed_first_author = _extract_first_author_surname_from_text(pubmed_text)

        # 3. Classify
        classification, explanation = classify_trial(
            parsed_surname=parsed_surname,
            parsed_year=parsed_year,
            pubmed_title=pubmed_title,
            pubmed_first_author=pubmed_first_author,
            pubmed_year=pubmed_year,
            pubmed_full_text=pubmed_text,
        )
        summary[classification] += 1

        trial_results.append({
            "trial_id": trial_id,
            "pmid": pmid,
            "study_string": study_string,
            "parsed_surname": parsed_surname,
            "parsed_year": parsed_year,
            "pubmed_title": pubmed_title,
            "pubmed_first_author": pubmed_first_author,
            "pubmed_year": pubmed_year,
            "classification": classification,
            "explanation": explanation,
        })

    report = {
        "spec_version": "v0.1.2",
        "spec_commit": spec_commit,
        "ran_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "sample_list_path": str(sample_list_path),
        "sample_list_sha256": sample_sha,
        "abstracts_cache_path": str(abstracts_cache_path),
        "n_trials": len(trial_results),
        "summary": summary,
        "trials": trial_results,
    }
    return report


# ---------------------------------------------------------------------------
# Human-readable stdout summary
# ---------------------------------------------------------------------------

def print_summary(report: dict, output_path: Path) -> None:
    sl = report["sample_list_path"]
    sha = report["sample_list_sha256"][:16] + "..."
    print(f"Pairwise70 PMID Resolution Check — {report['spec_version']}")
    print(f"Sample: {sl} (sha256 {sha})")
    print(f"N trials: {report['n_trials']}")
    print()
    print("Classification counts:")
    for cls, cnt in report["summary"].items():
        print(f"  {cls:<20s} {cnt}")

    mismatched = [
        t for t in report["trials"]
        if t["classification"] not in ("match", "no_pubmed_data", "parse_failed")
    ]
    no_data = [t for t in report["trials"] if t["classification"] == "no_pubmed_data"]
    parse_fail = [t for t in report["trials"] if t["classification"] == "parse_failed"]

    print()
    if mismatched:
        print(f"Mismatched trials (report -> {output_path}):")
        for t in mismatched:
            title_snippet = (t["pubmed_title"] or "")[:60]
            print(
                f"  - {t['trial_id']} (PMID {t['pmid']}): "
                f"{t['study_string']!r} -> \"{title_snippet}\" "
                f"[{t['classification']}]"
            )
    else:
        print("No title/year mismatches detected.")

    if no_data:
        pmids_seen: set[str] = set()
        print()
        print("Trials with no PubMed data (not in cache, live fetch disabled):")
        for t in no_data:
            pmid = t["pmid"]
            if pmid not in pmids_seen:
                print(f"  PMID {pmid}: {t['study_string']!r}")
                pmids_seen.add(pmid)

    if parse_fail:
        print()
        print("Trials where study_string parse failed:")
        for t in parse_fail:
            print(f"  - {t['trial_id']}: {t['study_string']!r}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _default_paths(script_dir: Path) -> Tuple[Path, Path]:
    repo_root = script_dir.parent
    sample = repo_root / "data" / "audit_v0.1.1" / "sample_list.json"
    output = repo_root / "data" / "audit_v0.1.1" / "pmid_resolution_report.json"
    return sample, output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARAC v0.1.2 PMID resolution check")
    parser.add_argument(
        "--sample-list",
        default=None,
        help="Path to sample_list.json (default: data/audit_v0.1.1/sample_list.json)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path for output JSON report",
    )
    parser.add_argument(
        "--fetch-live",
        action="store_true",
        default=False,
        help="Opt-in: fetch missing PMIDs from PubMed API",
    )
    args = parser.parse_args(argv)

    script_dir = Path(__file__).parent
    default_sample, default_output = _default_paths(script_dir)

    sample_list_path = Path(args.sample_list) if args.sample_list else default_sample
    output_path = Path(args.output) if args.output else default_output

    if not sample_list_path.exists():
        print(f"ERROR: sample-list not found: {sample_list_path}", file=sys.stderr)
        return 1

    abstracts_cache_path = sample_list_path.parent / "abstracts_cache.json"

    report = run_check(
        sample_list_path=sample_list_path,
        abstracts_cache_path=abstracts_cache_path,
        fetch_live=args.fetch_live,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print_summary(report, output_path)
    print()
    print(f"Report written to: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
