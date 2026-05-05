"""Small JSON file cache used for HTTP fallback data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CacheEntry:
    key: str
    value: Any
    created_at: datetime


class CacheStore:
    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, *, max_age_seconds: int | None = None) -> CacheEntry | None:
        path = self._path_for_key(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            created_at = datetime.fromisoformat(payload["created_at"])
            if created_at.tzinfo is None or created_at.utcoffset() is None:
                return None
            if max_age_seconds is not None:
                age = (datetime.now(UTC) - created_at).total_seconds()
                if age > max_age_seconds:
                    return None
            return CacheEntry(key=key, value=payload["value"], created_at=created_at)
        except (OSError, KeyError, json.JSONDecodeError, ValueError, TypeError):
            return None

    def set(self, key: str, value: Any, *, created_at: datetime | None = None) -> None:
        created_at = created_at or datetime.now(UTC)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        path = self._path_for_key(key)
        payload = {
            "key": key,
            "created_at": created_at.isoformat(),
            "value": value,
        }
        path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")

    def _path_for_key(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"
