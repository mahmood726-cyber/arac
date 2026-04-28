"""Disk cache for LLM responses, keyed by (model, system_hash, user_hash).

Same shape as resolve/http_cache.py but the key inputs are model + system + user
content (not URL + body). TTL longer (~90 days) since LLM responses are
deterministic enough for our extraction task that we can reuse aggressively.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class LLMCache:
    root: Path
    ttl_seconds: int = 90 * 24 * 3600  # 90 days

    def _key_path(self, model: str, system_prompt: str, user_input: str) -> Path:
        h = hashlib.sha256()
        h.update(model.encode("utf-8"))
        h.update(b"\x00")
        h.update(system_prompt.encode("utf-8"))
        h.update(b"\x00")
        h.update(user_input.encode("utf-8"))
        return self.root / f"{h.hexdigest()}.json"

    def get(self, model: str, system_prompt: str, user_input: str) -> Optional[str]:
        path = self._key_path(model, system_prompt, user_input)
        if not path.is_file():
            return None
        age = time.time() - path.stat().st_mtime
        if age > self.ttl_seconds:
            return None
        return path.read_text(encoding="utf-8")

    def set(self, model: str, system_prompt: str, user_input: str, response: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._key_path(model, system_prompt, user_input).write_text(response, encoding="utf-8")
