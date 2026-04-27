"""Europe PMC client: search by Author + Year, return top hit."""

from __future__ import annotations

from pathlib import Path

import pytest

from arac.resolve.europepmc import EuropePMCClient, EuropePMCHit


CASSETTE_DIR = Path(__file__).parent / "cassettes"


@pytest.mark.vcr(cassette_library_dir=str(CASSETTE_DIR), record_mode="none")
def test_search_smith_2010_returns_hit(tmp_path: Path) -> None:
    client = EuropePMCClient(cache_dir=tmp_path)
    hit = client.search_author_year("Smith", 2010)
    assert hit is None or isinstance(hit, EuropePMCHit)
    if hit is not None:
        assert hit.pmid
        assert hit.title
        assert hit.year == 2010


def test_no_results_returns_none(tmp_path: Path) -> None:
    """If the query returns 0 results, the client returns None (not raise)."""
    from arac.resolve.http_cache import HttpCache
    cache = HttpCache(root=tmp_path, ttl_seconds=3600)
    client = EuropePMCClient(cache_dir=tmp_path)
    url = client._build_url("ZZZNOTAREALAUTHOR", 9999)
    cache.set(url, b"", b'{"resultList":{"result":[]}}')
    hit = client.search_author_year("ZZZNOTAREALAUTHOR", 9999)
    assert hit is None
