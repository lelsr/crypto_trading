from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from indicators import bollinger_bands, calculate_indicator_snapshot, ema_last, macd  # noqa: E402
from models import KlineBar  # noqa: E402


def bars(count: int, *, exchange: str = "okx", symbol: str = "BTCUSDT") -> list[KlineBar]:
    start = datetime(2026, 5, 5, 0, 0, tzinfo=UTC)
    return [
        KlineBar(exchange, symbol, "15m", start + timedelta(minutes=15 * i), i + 1, i + 2, i, i + 1, 100 + i)
        for i in range(count)
    ]


def test_ema_returns_none_when_insufficient_data() -> None:
    assert ema_last([1, 2, 3], 20) is None


def test_ema_macd_and_bollinger_calculate_values() -> None:
    values = [float(i) for i in range(1, 120)]

    assert ema_last(values, 20) is not None
    macd_value, signal, histogram = macd(values)
    assert macd_value is not None
    assert signal is not None
    assert histogram is not None
    upper, middle, lower = bollinger_bands(values)
    assert upper is not None
    assert middle is not None
    assert lower is not None
    assert upper > middle > lower


def test_indicator_requires_min_bars() -> None:
    assert ema_last([float(i) for i in range(49)], 20) is None
    assert ema_last([float(i) for i in range(50)], 20) is not None

    macd_value, signal, histogram = macd([float(i) for i in range(99)])
    assert macd_value is None
    assert signal is None
    assert histogram is None

    macd_value, signal, histogram = macd([float(i) for i in range(100)])
    assert macd_value is not None
    assert signal is not None
    assert histogram is not None


def test_indicator_snapshot_rejects_non_primary_exchange_input() -> None:
    mixed = bars(80)
    mixed[-1] = KlineBar("binance", "BTCUSDT", "15m", mixed[-1].open_time, 1, 2, 0, 1, 100)

    with pytest.raises(ValueError, match="non-primary exchange"):
        calculate_indicator_snapshot(mixed, primary_exchange="okx", timeframe="15m")


def test_indicator_snapshot_sorts_bars_and_outputs_snapshot() -> None:
    shuffled = list(reversed(bars(80)))

    snapshot = calculate_indicator_snapshot(shuffled, primary_exchange="okx", timeframe="15m")

    assert snapshot is not None
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.exchange == "okx"
    assert snapshot.ema20 is not None
    assert snapshot.ema60 is not None
    assert snapshot.volume_ma is not None
