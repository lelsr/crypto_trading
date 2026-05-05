"""Binance USD-M futures market data adapter."""

from __future__ import annotations

from datetime import UTC, datetime

from domain.models import ExchangeTicker, KlineBar
from infrastructure.exchanges.base import ExchangeAdapter
from infrastructure.http_client import HttpClient


class BinanceFuturesAdapter(ExchangeAdapter):
    exchange = "binance_futures"
    base_url = "https://fapi.binance.com"

    def __init__(self, http_client: HttpClient) -> None:
        super().__init__(http_client)

    def fetch_usdt_perp_tickers(self) -> list[ExchangeTicker]:
        result = self.http_client.get_json(
            f"{self.base_url}/fapi/v1/ticker/24hr",
            cache_key=f"{self.exchange}:ticker_24hr",
        )
        self._record_health(result)
        if not result.ok or not isinstance(result.data, list):
            return []
        tickers: list[ExchangeTicker] = []
        updated_at = datetime.now(UTC)
        for item in result.data:
            raw_symbol = str(item.get("symbol", ""))
            if not raw_symbol.endswith("USDT"):
                continue
            tickers.append(
                ExchangeTicker(
                    exchange=self.exchange,
                    raw_symbol=raw_symbol,
                    unified_symbol=self.unify_usdt_symbol(raw_symbol),
                    quote_volume_24h_usd=self._float_or_none(item.get("quoteVolume")),
                    base_volume_24h=self._float_or_none(item.get("volume")),
                    last_price=self._float_or_none(item.get("lastPrice")),
                    price_change_pct_24h=self._float_or_none(item.get("priceChangePercent")),
                    source_status=result.source_status,
                    latency_ms=result.latency_ms,
                    updated_at=updated_at,
                )
            )
        return tickers

    def fetch_klines(self, symbol: str, timeframe: str, limit: int) -> list[KlineBar]:
        result = self.http_client.get_json(
            f"{self.base_url}/fapi/v1/klines",
            params={"symbol": symbol, "interval": timeframe, "limit": limit},
            cache_key=f"{self.exchange}:klines:{symbol}:{timeframe}:{limit}",
        )
        self._record_health(result)
        if not result.ok or not isinstance(result.data, list):
            return []
        bars: list[KlineBar] = []
        for row in result.data:
            if not isinstance(row, list) or len(row) < 6:
                continue
            bars.append(
                KlineBar(
                    exchange=self.exchange,
                    symbol=self.unify_usdt_symbol(symbol),
                    timeframe=timeframe,
                    open_time=self._ms_to_datetime(row[0]),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        return bars
