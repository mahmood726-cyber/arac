"""Per-trial labels CSV: one row per trial with all 3 Tier classifications
+ source context for the verification UI.

The CSV is the durable interface between the batch classifier run and the
interactive verification UI. Students see one trial at a time, with all
algorithmic decisions pre-populated, and either confirm or flag each tier.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Iterable, Optional


LABEL_COLUMNS = (
    "trial_id",
    "ma_id",
    "trial_index",
    "study_string",
    "pmid",
    "nct_id",
    "title",
    "tier_s_label",
    "tier_s_source",
    "tier_s_confidence",
    "tier_s_country",
    "tier_a_label",
    "tier_a_position",
    "tier_a_confidence",
    "tier_a_country",
    "tier_p_label",
    "tier_p_confidence",
    "abstract_excerpt",
)
# Note: 18 canonical columns above include abstract_excerpt (source context).
# tier_p_evidence, tier_p_african_pct, authors_list are additional context
# fields appended here; they ride alongside LABEL_COLUMNS in the CSV header.
_EXTRA_COLUMNS = ("tier_p_evidence", "tier_p_african_pct", "authors_list")
ALL_COLUMNS = LABEL_COLUMNS + _EXTRA_COLUMNS


@dataclass(frozen=True)
class TrialLabel:
    trial_id: str
    ma_id: str
    trial_index: int
    study_string: str
    pmid: Optional[str]
    nct_id: Optional[str]
    title: Optional[str]
    tier_s_label: Optional[str]
    tier_s_source: Optional[str]
    tier_s_confidence: Optional[float]
    tier_s_country: Optional[str]
    tier_a_label: Optional[str]
    tier_a_position: Optional[str]
    tier_a_confidence: Optional[float]
    tier_a_country: Optional[str]
    tier_p_label: Optional[str]
    tier_p_confidence: Optional[float]
    tier_p_african_pct: Optional[float]
    tier_p_evidence: Optional[str]
    abstract_excerpt: Optional[str]
    authors_list: Optional[str]


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _row_to_dict(r: TrialLabel) -> dict:
    return {
        "trial_id": r.trial_id, "ma_id": r.ma_id,
        "trial_index": _cell(r.trial_index),
        "study_string": _cell(r.study_string),
        "pmid": _cell(r.pmid), "nct_id": _cell(r.nct_id),
        "title": _cell(r.title),
        "tier_s_label": _cell(r.tier_s_label),
        "tier_s_source": _cell(r.tier_s_source),
        "tier_s_confidence": _cell(r.tier_s_confidence),
        "tier_s_country": _cell(r.tier_s_country),
        "tier_a_label": _cell(r.tier_a_label),
        "tier_a_position": _cell(r.tier_a_position),
        "tier_a_confidence": _cell(r.tier_a_confidence),
        "tier_a_country": _cell(r.tier_a_country),
        "tier_p_label": _cell(r.tier_p_label),
        "tier_p_confidence": _cell(r.tier_p_confidence),
        "tier_p_african_pct": _cell(r.tier_p_african_pct),
        "tier_p_evidence": _cell(r.tier_p_evidence),
        "abstract_excerpt": _cell(r.abstract_excerpt),
        "authors_list": _cell(r.authors_list),
    }


def write_trial_labels(rows: Iterable[TrialLabel], out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(ALL_COLUMNS))
        writer.writeheader()
        for r in rows:
            writer.writerow(_row_to_dict(r))
            n += 1
    return n


def render_verification_ui(rows: list) -> str:
    """Render the full verification UI HTML. `rows` is a list of TrialLabel
    OR list of dicts already loaded from CSV."""
    from arac.verify.html_template import TEMPLATE

    # Normalise to a list of dicts that the JS can consume directly.
    trials_json: list = []
    for r in rows:
        if isinstance(r, TrialLabel):
            d = _row_to_dict(r)
        elif isinstance(r, dict):
            d = r
        else:
            raise TypeError(f"unexpected row type: {type(r)}")
        trials_json.append(d)

    return Template(TEMPLATE).substitute(
        trials_json=json.dumps(trials_json, ensure_ascii=False),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        row_count=len(trials_json),
        storage_key="arac-verification-v1",
    )
