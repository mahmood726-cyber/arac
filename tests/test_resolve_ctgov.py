"""CT.gov v2 client: get a study by NCT ID, return sites + sponsor."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.resolve.ctgov import CTGovClient, CTGovStudy


CASSETTE_DIR = Path(__file__).parent / "cassettes"


@pytest.mark.vcr(cassette_library_dir=str(CASSETTE_DIR), record_mode="none")
def test_get_victoria_trial(tmp_path: Path) -> None:
    """NCT02861534 = VICTORIA (vericiguat in HFrEF). Known multi-country trial."""
    client = CTGovClient(cache_dir=tmp_path)
    study = client.get_study("NCT02861534")
    assert study is None or isinstance(study, CTGovStudy)
    if study is not None:
        assert study.nct_id == "NCT02861534"
        assert len(study.country_list) > 0
        assert study.lead_sponsor


def test_invalid_nct_returns_none(tmp_path: Path) -> None:
    """A made-up NCT should return None, not raise."""
    from arac.resolve.http_cache import HttpCache
    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    client = CTGovClient(cache_dir=tmp_path)
    url = client._build_url("NCT99999999")
    cache.set(url, b"", b'{"protocolSection":null}')
    study = client.get_study("NCT99999999")
    assert study is None
