from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from kline_policy import align_closed_timeframes, build_kline_fetch_plan, validate_primary_exchange_klines  # noqa: E402
from models import KlineBar, UnifiedActivityCandidate  # noqa: E402


def candidate(symbol: str, primary_exchange: str | None) -> UnifiedActivityCandidate:
    return UnifiedActivityCandidate(
        symbol=symbol,
        exchanges=[primary_exchange] if primary_exchange else [],
        primary_exchange=primary_exchange,
        activity_score=80,
        global_quote_volume_24h_usd=1_000_000,
        market_cap_usd=100_000_000,
        market_cap_status="known",
        source_status="ok",
    )


def bar(exchange: str, symbol: str, timeframe: str, open_time: datetime, close: float = 100) -> KlineBar:
    return KlineBar(exchange, symbol, timeframe, open_time, close - 1, close + 1, close - 2, close, 10)


def test_build_kline_fetch_plan_only_for_final_top_m_and_primary_exchange() -> None:
    plans = build_kline_fetch_plan(
        [candidate("BTCUSDT", "okx"), candidate("ETHUSDT", None), candidate("SOLUSDT", "binance")],
        final_top_m_symbols={"BTCUSDT", "ETHUSDT"},
        timeframes=["15m", "1h", "4h"],
        limit=200,
    )

    assert len(plans) == 3
    assert {plan.symbol for plan in plans} == {"BTCUSDT"}
    assert all(plan.primary_exchange == "okx" for plan in plans)
    assert plans[0].cache_key == "kline:okx:BTCUSDT:15m:200"


def test_validate_primary_exchange_rejects_cross_exchange_klines() -> None:
    with pytest.raises(ValueError, match="non-primary exchange"):
        validate_primary_exchange_klines(
            symbol="BTCUSDT",
            primary_exchange="okx",
            bars_by_timeframe={"15m": [bar("binance", "BTCUSDT", "15m", datetime(2026, 5, 5, tzinfo=UTC))]},
        )


def test_align_closed_timeframes_uses_closed_anchor_and_lagged_higher_timeframes() -> None:
    as_of = datetime(2026, 5, 5, 10, 37, tzinfo=UTC)
    bars = {
        "15m": [
            bar("okx", "BTCUSDT", "15m", datetime(2026, 5, 5, 10, 15, tzinfo=UTC)),
            bar("okx", "BTCUSDT", "15m", datetime(2026, 5, 5, 10, 30, tzinfo=UTC)),
        ],
        "1h": [
            bar("okx", "BTCUSDT", "1h", datetime(2026, 5, 5, 9, 0, tzinfo=UTC)),
            bar("okx", "BTCUSDT", "1h", datetime(2026, 5, 5, 10, 0, tzinfo=UTC)),
        ],
        "4h": [
            bar("okx", "BTCUSDT", "4h", datetime(2026, 5, 5, 4, 0, tzinfo=UTC)),
            bar("okx", "BTCUSDT", "4h", datetime(2026, 5, 5, 8, 0, tzinfo=UTC)),
        ],
    }

    alignment = align_closed_timeframes(bars_by_timeframe=bars, as_of=as_of)

    assert alignment.analysis_anchor_time == datetime(2026, 5, 5, 10, 15, tzinfo=UTC)
    assert alignment.selected_open_times["1h"] == datetime(2026, 5, 5, 9, 0, tzinfo=UTC)
    assert alignment.alignment_status["1h"] == "lagged_closed_bar"
    assert alignment.selected_open_times["4h"] == datetime(2026, 5, 5, 4, 0, tzinfo=UTC)
    assert alignment.alignment_status["4h"] == "lagged_closed_bar"


def test_align_closed_timeframes_rejects_missing_timeframe() -> None:
    as_of = datetime(2026, 5, 5, 10, 37, tzinfo=UTC)
    alignment = align_closed_timeframes(
        bars_by_timeframe={
            "15m": [bar("okx", "BTCUSDT", "15m", as_of - timedelta(minutes=30))],
            "1h": [bar("okx", "BTCUSDT", "1h", as_of - timedelta(hours=2))],
        },
        as_of=as_of,
    )

    assert alignment.is_valid is False
    assert alignment.reason == "4h missing"
