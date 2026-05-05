from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from domain.kline_policy import KlineFetchPlan
from domain.models import ExchangeTicker, KlineBar
from infrastructure.exchanges.base import ExchangeAdapter
from infrastructure.http_client import HttpClient
from infrastructure.kline_provider import KlineProvider


AS_OF = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


class StubKlineAdapter(ExchangeAdapter):
    exchange = "test_exchange"

    def __init__(self) -> None:
        pass

    def fetch_usdt_perp_tickers(self) -> list[ExchangeTicker]:
        return []

    def fetch_klines(self, symbol: str, timeframe: str, limit: int) -> list[KlineBar]:
        return [
            KlineBar(
                exchange=self.exchange,
                symbol=symbol,
                timeframe=timeframe,
                open_time=AS_OF - timedelta(minutes=15),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=500.0,
            )
        ]


def make_plan(symbol: str, exchange: str, timeframe: str) -> KlineFetchPlan:
    return KlineFetchPlan(
        symbol=symbol,
        primary_exchange=exchange,
        timeframe=timeframe,
        limit=200,
        cache_key=f"kline:{exchange}:{symbol}:{timeframe}:200",
        required=True,
        reason="test",
    )


def test_available_exchanges_per_symbol_returns_all_adapters() -> None:
    provider = KlineProvider([
        StubKlineAdapter(),
        StubKlineAdapter(),
    ])
    provider._by_exchange = {"okx": StubKlineAdapter(), "binance_futures": StubKlineAdapter()}

    result = provider.available_exchanges_per_symbol(["BTCUSDT", "ETHUSDT"])
    assert result == {"BTCUSDT": ["binance_futures", "okx"], "ETHUSDT": ["binance_futures", "okx"]}


def test_fetch_klines_routes_to_correct_adapter() -> None:
    okx = StubKlineAdapter()
    okx.exchange = "okx"
    binance = StubKlineAdapter()
    binance.exchange = "binance_futures"

    provider = KlineProvider([okx, binance])

    plan = make_plan("BTCUSDT", "okx", "15m")
    bars = provider.fetch_klines(plan)
    assert len(bars) == 1
    assert bars[0].exchange == "okx"
    assert bars[0].symbol == "BTCUSDT"
    assert bars[0].timeframe == "15m"

    plan_binance = make_plan("ETHUSDT", "binance_futures", "1h")
    bars_binance = provider.fetch_klines(plan_binance)
    assert bars_binance[0].exchange == "binance_futures"
    assert bars_binance[0].symbol == "ETHUSDT"


def test_fetch_klines_unknown_exchange_raises() -> None:
    provider = KlineProvider([StubKlineAdapter()])
    provider._by_exchange = {"okx": StubKlineAdapter()}

    plan = make_plan("BTCUSDT", "nonexistent", "15m")
    try:
        provider.fetch_klines(plan)
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_fetch_tickers_delegates_to_fetch_usdt_perp_tickers() -> None:
    class TickerAdapter(ExchangeAdapter):
        exchange = "test"

        def __init__(self) -> None:
            pass

        def fetch_usdt_perp_tickers(self) -> list[ExchangeTicker]:
            return [
                ExchangeTicker(
                    exchange=self.exchange,
                    raw_symbol="BTCUSDT",
                    unified_symbol="BTCUSDT",
                    quote_volume_24h_usd=1_000_000.0,
                    base_volume_24h=10_000.0,
                    last_price=50000.0,
                    price_change_pct_24h=2.5,
                    source_status="ok",
                    latency_ms=50,
                    updated_at=AS_OF,
                )
            ]

        def fetch_klines(self, symbol: str, timeframe: str, limit: int) -> list[KlineBar]:
            return []

    adapter = TickerAdapter()
    tickers = adapter.fetch_tickers()
    assert len(tickers) == 1
    assert tickers[0].unified_symbol == "BTCUSDT"
