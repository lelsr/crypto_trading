from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.cache_store import CacheStore


def test_cache_store_round_trips_json_payload(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    created_at = datetime.now(UTC)

    store.set("binance:ticker", {"symbols": ["BTCUSDT"]}, created_at=created_at)
    entry = store.get("binance:ticker", max_age_seconds=60)

    assert entry is not None
    assert entry.value == {"symbols": ["BTCUSDT"]}
    assert entry.created_at == created_at


def test_cache_store_returns_none_for_expired_entry(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    old_time = datetime.now(UTC) - timedelta(seconds=120)

    store.set("old", {"ok": True}, created_at=old_time)

    assert store.get("old", max_age_seconds=1) is None


def test_cache_store_ignores_corrupt_payload(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    path = store._path_for_key("bad")
    path.write_text("{bad-json", encoding="utf-8")

    assert store.get("bad") is None
