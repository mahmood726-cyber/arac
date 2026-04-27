"""Bridge: load all MAs from Pairwise70 dir and assert basic invariants."""

from __future__ import annotations

from pathlib import Path

from arac.bridge import load_all_mas, MARecord


def test_load_all_mas_returns_nonempty(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=5)
    assert len(mas) >= 1
    assert all(isinstance(m, MARecord) for m in mas)
    assert all(m.k >= 1 for m in mas), "every MA in Pairwise70 should have k>=1"
    assert all(m.data_type in ("binary", "continuous", "giv") for m in mas)
    assert len({m.ma_id for m in mas}) == len(mas), "ma_id must be unique"


def test_trial_rows_are_stable_and_unique(pairwise70_dir: Path) -> None:
    mas = load_all_mas(pairwise70_dir, max_reviews=5)

    # Each MA's trials count equals its k.
    for ma in mas:
        assert len(ma.trials) == ma.k

    # trial_index is a contiguous 0..k-1 sequence per MA.
    for ma in mas:
        assert [t.trial_index for t in ma.trials] == list(range(ma.k))

    # trial_id is globally unique across the whole loaded set.
    all_ids = [t.trial_id for ma in mas for t in ma.trials]
    assert len(all_ids) == len(set(all_ids)), "trial_id collisions across MAs"

    # Re-loading produces identical trial_ids (stability for downstream Tier joins).
    mas2 = load_all_mas(pairwise70_dir, max_reviews=5)
    assert [t.trial_id for ma in mas for t in ma.trials] == \
           [t.trial_id for ma in mas2 for t in ma.trials]
