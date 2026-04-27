"""Pairwise70 bridge — thin reuse layer over repro-floor-atlas's loader.

We do NOT reimplement .rda parsing or MA construction. We adapt repro-floor-atlas's
canonical MAInputs to ARAC's MARecord, which adds a stable per-trial enumeration
that later plans use to attach Tier-S/A/P labels.

repro-floor-atlas location is resolved via:
  1. REPRO_FLOOR_ATLAS_SRC env var (full path to the src/ directory)
  2. Candidate-root discovery: <drive>:/Projects/repro-floor-atlas/src (C: then D:)
  3. Fails closed with an actionable error if neither resolves.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

# ---------------------------------------------------------------------------
# Resolve repro-floor-atlas src directory — env var then candidate discovery.
# Per lessons.md: "Do not hardcode one drive."
# ---------------------------------------------------------------------------
_CANDIDATE_RFA_ROOTS = [
    "C:/Projects/repro-floor-atlas/src",  # sentinel:skip-line P0-hardcoded-local-path
    "D:/Projects/repro-floor-atlas/src",  # sentinel:skip-line P0-hardcoded-local-path
]


def _rfa_src_dir() -> Path:
    env_override = os.environ.get("REPRO_FLOOR_ATLAS_SRC")
    if env_override:
        p = Path(env_override)
        if not p.is_dir():
            raise RuntimeError(
                f"REPRO_FLOOR_ATLAS_SRC={env_override!r} is set but is not a directory. "
                f"Point it at the repro-floor-atlas/src/ directory, or unset it to "
                f"fall back to C:/D: candidate discovery."
            )
        return p
    for candidate in _CANDIDATE_RFA_ROOTS:
        p = Path(candidate)
        if p.is_dir():
            return p
    raise RuntimeError(
        "repro-floor-atlas src directory not found. Set REPRO_FLOOR_ATLAS_SRC env var "
        f"or place the project at one of: {_CANDIDATE_RFA_ROOTS}"
    )


_rfa_src = _rfa_src_dir()
if str(_rfa_src) not in sys.path:
    sys.path.insert(0, str(_rfa_src))

from repro_floor_atlas.loader import MAInputs, load_directory  # noqa: E402


@dataclass(frozen=True)
class TrialRow:
    """One trial inside one meta-analysis. Stable identifier for Tier labelling."""
    ma_id: str
    trial_index: int  # 0-based position within the parent MA's k trials
    trial_id: str     # ma_id + "::t" + trial_index — globally unique within ARAC
    data_type: str
    k_total: int      # k of the parent MA (so a worker can compute progress)


@dataclass(frozen=True)
class MARecord:
    """ARAC's view of a Pairwise70 MA: original MAInputs + stable trial-row list."""
    ma_id: str
    review_id: str
    analysis_number: int
    k: int
    data_type: str
    inputs: MAInputs
    trials: tuple[TrialRow, ...]


def _make_trials(ma: MAInputs) -> tuple[TrialRow, ...]:
    return tuple(
        TrialRow(
            ma_id=ma.ma_id,
            trial_index=i,
            trial_id=f"{ma.ma_id}::t{i}",
            data_type=ma.data_type,
            k_total=ma.k,
        )
        for i in range(ma.k)
    )


def load_all_mas(pairwise70_dir: Path, max_reviews: Optional[int] = None) -> list[MARecord]:
    """Load every MA in Pairwise70 (or first `max_reviews` for quick iteration)."""
    ma_inputs = load_directory(pairwise70_dir, max_reviews=max_reviews)
    return [
        MARecord(
            ma_id=m.ma_id,
            review_id=m.review_id,
            analysis_number=m.analysis_number,
            k=m.k,
            data_type=m.data_type,
            inputs=m,
            trials=_make_trials(m),
        )
        for m in ma_inputs
    ]


def iter_trial_rows(records: list[MARecord]) -> Iterator[TrialRow]:
    """Flatten MARecord list into a stream of trial rows."""
    for rec in records:
        yield from rec.trials
