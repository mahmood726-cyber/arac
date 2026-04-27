"""HTTP cache: file-based, TTL-based, idempotent on equal (url, body)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from arac.resolve.http_cache import HttpCache


def test_cache_miss_then_hit(tmp_path: Path) -> None:
    cache = HttpCache(root=tmp_path, ttl_seconds=60)
    key = ("https://example.com/api", b'{"q": "x"}')

    assert cache.get(*key) is None  # miss

    cache.set(*key, b"response-bytes-1")
    assert cache.get(*key) == b"response-bytes-1"  # hit


def test_cache_distinct_keys(tmp_path: Path) -> None:
    cache = HttpCache(root=tmp_path, ttl_seconds=60)
    cache.set("https://a", b"", b"resp-a")
    cache.set("https://b", b"", b"resp-b")
    assert cache.get("https://a", b"") == b"resp-a"
    assert cache.get("https://b", b"") == b"resp-b"


def test_cache_ttl_expires(tmp_path: Path) -> None:
    cache = HttpCache(root=tmp_path, ttl_seconds=0)  # expires immediately
    cache.set("https://x", b"", b"resp")
    time.sleep(0.05)
    assert cache.get("https://x", b"") is None


def test_cache_persists_across_instances(tmp_path: Path) -> None:
    c1 = HttpCache(root=tmp_path, ttl_seconds=60)
    c1.set("https://x", b"", b"resp")

    c2 = HttpCache(root=tmp_path, ttl_seconds=60)
    assert c2.get("https://x", b"") == b"resp"
