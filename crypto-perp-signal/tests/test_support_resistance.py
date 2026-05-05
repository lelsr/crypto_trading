from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from models import KlineBar  # noqa: E402
from support_resistance import find_recent_swing_low, find_swing_lows, identify_support_level  # noqa: E402


def make_bar(index: int, low: float, close: float | None = None, volume: float = 100) -> KlineBar:
    open_time = datetime(2026, 5, 5, 0, 0, tzinfo=UTC) + timedelta(minutes=15 * index)
    close = close if close is not None else low + 5
    return KlineBar("okx", "BTCUSDT", "15m", open_time, close - 1, close + 2, low, close, volume)


def test_find_recent_swing_low_uses_confirmed_window() -> None:
    lows = [10, 9, 8, 9, 10, 7, 8, 9]
    swings = find_swing_lows([make_bar(i, low) for i, low in enumerate(lows)], left=1, right=1)
    recent = find_recent_swing_low([make_bar(i, low) for i, low in enumerate(lows)], left=1, right=1)

    assert [swing.price for swing in swings] == [8, 7]
    assert recent.price == 7


def test_identify_support_clusters_nearby_swing_lows_below_price() -> None:
    lows = [100, 98, 95, 98, 101, 96, 95.2, 97, 105, 110, 108, 112, 115]
    bars = [make_bar(i, low, close=116 if i == len(lows) - 1 else low + 4, volume=100 + i) for i, low in enumerate(lows)]

    support = identify_support_level(bars, tolerance_pct=0.01)

    assert support.price is not None
    assert 94.5 <= support.price <= 96.5
    assert support.touch_count >= 2


def test_identify_support_returns_missing_when_no_data() -> None:
    support = identify_support_level([])

    assert support.price is None
    assert support.support_status == "missing"


def test_identify_support_returns_weak_when_no_cluster() -> None:
    bars = [make_bar(i, low, close=50) for i, low in enumerate([90, 91, 92, 93, 94, 95])]

    support = identify_support_level(bars)

    assert support.support_status in {"missing", "weak"}
