"""File-based HTTP response cache, keyed by (url, body) with a TTL.

Layout: each entry is one file under <root>/<sha256-of-key>.bin, with the
modification time used as the cache timestamp. Keep it dumb — no metadata file,
no manifest, no eviction. The cache directory is the cache.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class HttpCache:
    root: Path
    ttl_seconds: int

    def _key_path(self, url: str, body: bytes) -> Path:
        h = hashlib.sha256()
        h.update(url.encode("utf-8"))
        h.update(b"\x00")
        h.update(body)
        return self.root / f"{h.hexdigest()}.bin"

    def get(self, url: str, body: bytes) -> Optional[bytes]:
        path = self._key_path(url, body)
        if not path.is_file():
            return None
        age = time.time() - path.stat().st_mtime
        if age > self.ttl_seconds:
            return None
        return path.read_bytes()

    def set(self, url: str, body: bytes, response: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._key_path(url, body).write_bytes(response)
