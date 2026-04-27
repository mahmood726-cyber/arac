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
