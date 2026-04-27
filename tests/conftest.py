"""Shared pytest fixtures for ARAC tests."""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def pairwise70_dir() -> Path:
    """Path to the Pairwise70 .rda data directory.

    Resolution order: $PAIRWISE70_DIR env var, then C:/Projects/Pairwise70/data,
    then D:/Projects/Pairwise70/data. Skips test if none resolve.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    try:
        from inspect_rda import _data_dir
    finally:
        sys.path.pop(0)
    try:
        return _data_dir()
    except RuntimeError as e:
        pytest.skip(str(e))


@pytest.fixture(scope="session")
def repro_floor_baseline() -> dict:
    """The 14.3% non-reproducibility headline from repro-floor-atlas v0.1.0."""
    return {
        "pooled_estimate": 14.3,
        "binary": 12.9,
        "continuous": 25.0,
        "giv": 27.0,
        "tolerance_pp": 0.5,
        "commit_sha": "a1c63d48cfb9488f0f218283d84e65bcd05b4427",
    }
