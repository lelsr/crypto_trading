from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from models import KlineBar  # noqa: E402
from structure_analyzer import analyze_structure  # noqa: E402


def make_bars(timeframe: str, minutes: int, count: int, *, exchange: str = "okx", jump_last: bool = False) -> list[KlineBar]:
    start = datetime(2026, 5, 4, 0, 0, tzinfo=UTC)
    bars: list[KlineBar] = []
    for i in range(count):
        close = 100 + i * 0.1
        if jump_last and i == count - 1:
            close *= 1.08
        bars.append(
            KlineBar(
                exchange,
                "BTCUSDT",
                timeframe,
                start + timedelta(minutes=minutes * i),
                close - 0.5,
                close + 1,
                close - 1,
                close,
                100 + i,
            )
        )
    return bars


def stable_bars(timeframe: str, minutes: int, count: int, *, close: float = 100.0) -> list[KlineBar]:
    start = datetime(2026, 5, 4, 0, 0, tzinfo=UTC)
    return [
        KlineBar(
            "okx",
            "BTCUSDT",
            timeframe,
            start + timedelta(minutes=minutes * i),
            close - 0.1,
            close + 0.3,
            close - 0.2,
            close,
            100 + i,
        )
        for i in range(count)
    ]


def test_structure_analysis_rejects_cross_exchange_klines() -> None:
    bars_by_timeframe = {
        "15m": make_bars("15m", 15, 80, exchange="binance"),
        "1h": make_bars("1h", 60, 80),
        "4h": make_bars("4h", 240, 80),
    }

    with pytest.raises(ValueError, match="non-primary exchange"):
        analyze_structure(
            symbol="BTCUSDT",
            primary_exchange="okx",
            bars_by_timeframe=bars_by_timeframe,
            as_of=datetime(2026, 5, 6, 0, 0, tzinfo=UTC),
        )


def test_structure_analysis_flags_chase_risk_when_ema20_deviation_above_2_percent() -> None:
    bars_by_timeframe = {
        "15m": make_bars("15m", 15, 80, jump_last=True),
        "1h": make_bars("1h", 60, 80),
        "4h": make_bars("4h", 240, 80),
    }

    analysis = analyze_structure(
        symbol="BTCUSDT",
        primary_exchange="okx",
        bars_by_timeframe=bars_by_timeframe,
        as_of=datetime(2026, 5, 6, 0, 0, tzinfo=UTC),
    )

    assert analysis.chase_risk is True
    assert analysis.is_valid is False
    assert any("EMA20" in reason for reason in analysis.reasons)


def test_structure_analysis_requires_all_timeframes() -> None:
    analysis = analyze_structure(
        symbol="BTCUSDT",
        primary_exchange="okx",
        bars_by_timeframe={
            "15m": make_bars("15m", 15, 80),
            "1h": make_bars("1h", 60, 80),
        },
        as_of=datetime(2026, 5, 6, 0, 0, tzinfo=UTC),
    )

    assert analysis.is_valid is False
    assert "4h missing" in analysis.reasons


def test_structure_analysis_returns_valid_multi_timeframe_context() -> None:
    analysis = analyze_structure(
        symbol="BTCUSDT",
        primary_exchange="okx",
        bars_by_timeframe={
            "15m": make_bars("15m", 15, 80),
            "1h": make_bars("1h", 60, 80),
            "4h": make_bars("4h", 240, 80),
        },
        as_of=datetime(2026, 5, 6, 0, 0, tzinfo=UTC),
    )

    assert analysis.is_valid is True
    assert set(analysis.indicators) == {"15m", "1h", "4h"}
    assert analysis.timeframe_alignment["15m"] == "anchor_closed_bar"


def test_support_too_close_skipped() -> None:
    fifteen_minute = stable_bars("15m", 15, 120)
    for index in (40, 70, 100):
        original = fifteen_minute[index]
        fifteen_minute[index] = KlineBar(
            original.exchange,
            original.symbol,
            original.timeframe,
            original.open_time,
            original.open,
            original.high,
            99.6,
            original.close,
            original.volume,
        )

    analysis = analyze_structure(
        symbol="BTCUSDT",
        primary_exchange="okx",
        bars_by_timeframe={
            "15m": fifteen_minute,
            "1h": stable_bars("1h", 60, 120),
            "4h": stable_bars("4h", 240, 120),
        },
        as_of=datetime(2026, 5, 6, 0, 0, tzinfo=UTC),
    )

    assert analysis.support_too_close is True
    assert analysis.is_valid is False
    assert any("support" in reason for reason in analysis.reasons)


def test_trend_broken_blocks_signal() -> None:
    fifteen_minute = make_bars("15m", 15, 120)
    for offset, low in zip(range(3, 0, -1), [105.0, 104.0, 103.0]):
        index = len(fifteen_minute) - offset
        original = fifteen_minute[index]
        fifteen_minute[index] = KlineBar(
            original.exchange,
            original.symbol,
            original.timeframe,
            original.open_time,
            original.open,
            original.high,
            low,
            original.close,
            original.volume,
        )

    analysis = analyze_structure(
        symbol="BTCUSDT",
        primary_exchange="okx",
        bars_by_timeframe={
            "15m": fifteen_minute,
            "1h": make_bars("1h", 60, 120),
            "4h": make_bars("4h", 240, 120),
        },
        as_of=datetime(2026, 5, 6, 0, 0, tzinfo=UTC),
    )

    assert analysis.trend_broken is True
    assert analysis.is_valid is False
    assert any("trend_broken" in reason for reason in analysis.reasons)


def test_high_volatility_block_signal() -> None:
    fifteen_minute = make_bars("15m", 15, 120)
    original = fifteen_minute[-1]
    fifteen_minute[-1] = KlineBar(
        original.exchange,
        original.symbol,
        original.timeframe,
        original.open_time,
        original.open,
        original.close + 6.0,
        original.close - 1.0,
        original.close,
        original.volume,
    )

    analysis = analyze_structure(
        symbol="BTCUSDT",
        primary_exchange="okx",
        bars_by_timeframe={
            "15m": fifteen_minute,
            "1h": make_bars("1h", 60, 120),
            "4h": make_bars("4h", 240, 120),
        },
        as_of=datetime(2026, 5, 6, 0, 0, tzinfo=UTC),
    )

    assert analysis.high_volatility is True
    assert analysis.is_valid is False
    assert any("range" in reason for reason in analysis.reasons)
