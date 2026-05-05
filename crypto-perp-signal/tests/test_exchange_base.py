from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.exchanges.binance_futures import BinanceFuturesAdapter
from infrastructure.exchanges.coingecko import CoinGeckoAdapter
from infrastructure.exchanges.okx import OKXAdapter
from infrastructure.http_client import HttpResult


class FakeHttpClient:
    def __init__(self, result: HttpResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def get_json(self, url: str, **kwargs: object) -> HttpResult:
        self.calls.append({"url": url, **kwargs})
        return self.result


def test_binance_tickers_parse_unified_exchange_ticker() -> None:
    adapter = BinanceFuturesAdapter(
        FakeHttpClient(
            HttpResult(
                ok=True,
                status_code=200,
                data=[
                    {
                        "symbol": "BTCUSDT",
                        "quoteVolume": "1000000",
                        "volume": "10",
                        "lastPrice": "100000",
                        "priceChangePercent": "2.5",
                    },
                    {"symbol": "ETHUSDC", "quoteVolume": "10"},
                ],
                source_status="ok",
                latency_ms=50,
            )
        )
    )

    tickers = adapter.fetch_usdt_perp_tickers()

    assert len(tickers) == 1
    assert tickers[0].exchange == "binance_futures"
    assert tickers[0].unified_symbol == "BTCUSDT"
    assert tickers[0].quote_volume_24h_usd == 1_000_000.0
    assert tickers[0].latency_ms == 50


def test_binance_klines_parse_kline_bars() -> None:
    adapter = BinanceFuturesAdapter(
        FakeHttpClient(
            HttpResult(
                ok=True,
                status_code=200,
                data=[[1710000000000, "1", "2", "0.5", "1.5", "100"]],
                source_status="ok",
                latency_ms=40,
            )
        )
    )

    bars = adapter.fetch_klines("BTCUSDT", "15m", 200)

    assert len(bars) == 1
    assert bars[0].exchange == "binance_futures"
    assert bars[0].symbol == "BTCUSDT"
    assert bars[0].close == 1.5


def test_okx_tickers_and_klines_parse_unified_models() -> None:
    ticker_adapter = OKXAdapter(
        FakeHttpClient(
            HttpResult(
                ok=True,
                status_code=200,
                data={
                    "data": [
                        {
                            "instId": "BTC-USDT-SWAP",
                            "volCcy24h": "2000000",
                            "vol24h": "20",
                            "last": "100500",
                        }
                    ]
                },
                source_status="ok",
                latency_ms=60,
            )
        )
    )
    kline_adapter = OKXAdapter(
        FakeHttpClient(
            HttpResult(
                ok=True,
                status_code=200,
                data={"data": [["1710000000000", "1", "2", "0.5", "1.5", "100"]]},
                source_status="ok",
                latency_ms=70,
            )
        )
    )

    tickers = ticker_adapter.fetch_usdt_perp_tickers()
    bars = kline_adapter.fetch_klines("BTCUSDT", "15m", 200)

    assert tickers[0].exchange == "okx"
    assert tickers[0].unified_symbol == "BTCUSDT"
    assert bars[0].exchange == "okx"
    assert bars[0].symbol == "BTCUSDT"


def test_adapter_failure_returns_empty_list_and_health_status() -> None:
    adapter = BinanceFuturesAdapter(
        FakeHttpClient(
            HttpResult(
                ok=False,
                status_code=503,
                data=None,
                source_status="failed",
                latency_ms=1_000,
                error_message="service unavailable",
            )
        )
    )

    assert adapter.fetch_usdt_perp_tickers() == []
    health = adapter.health_check()
    assert health.source_status == "failed"
    assert health.latency_ms == 1_000


def test_coingecko_market_caps_return_none_for_missing_or_failed() -> None:
    adapter = CoinGeckoAdapter(
        FakeHttpClient(
            HttpResult(
                ok=True,
                status_code=200,
                data=[{"id": "bitcoin", "market_cap": 1_000_000_000}],
                source_status="ok",
                latency_ms=80,
            )
        )
    )

    caps = adapter.fetch_market_caps(["bitcoin", "missing"])

    assert caps == {"bitcoin": 1_000_000_000.0, "missing": None}
    assert adapter.last_source_status == "ok"
