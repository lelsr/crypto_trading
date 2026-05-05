"""OKX swap market data adapter."""

from __future__ import annotations

from datetime import UTC, datetime

from domain.models import ExchangeTicker, KlineBar
from infrastructure.exchanges.base import ExchangeAdapter
from infrastructure.http_client import HttpClient


class OKXAdapter(ExchangeAdapter):
    exchange = "okx"
    base_url = "https://www.okx.com"

    def __init__(self, http_client: HttpClient) -> None:
        super().__init__(http_client)

    def fetch_usdt_perp_tickers(self) -> list[ExchangeTicker]:
        result = self.http_client.get_json(
            f"{self.base_url}/api/v5/market/tickers",
            params={"instType": "SWAP"},
            cache_key=f"{self.exchange}:swap_tickers",
        )
        self._record_health(result)
        data = result.data.get("data") if isinstance(result.data, dict) else None
        if not result.ok or not isinstance(data, list):
            return []
        tickers: list[ExchangeTicker] = []
        updated_at = datetime.now(UTC)
        for item in data:
            raw_symbol = str(item.get("instId", ""))
            if not raw_symbol.endswith("-USDT-SWAP"):
                continue
            tickers.append(
                ExchangeTicker(
                    exchange=self.exchange,
                    raw_symbol=raw_symbol,
                    unified_symbol=self.unify_usdt_symbol(raw_symbol),
                    quote_volume_24h_usd=self._float_or_none(item.get("volCcy24h")),
                    base_volume_24h=self._float_or_none(item.get("vol24h")),
                    last_price=self._float_or_none(item.get("last")),
                    price_change_pct_24h=None,
                    source_status=result.source_status,
                    latency_ms=result.latency_ms,
                    updated_at=updated_at,
                )
            )
        return tickers

    def fetch_klines(self, symbol: str, timeframe: str, limit: int) -> list[KlineBar]:
        inst_id = self._to_okx_inst_id(symbol)
        result = self.http_client.get_json(
            f"{self.base_url}/api/v5/market/candles",
            params={"instId": inst_id, "bar": timeframe, "limit": limit},
            cache_key=f"{self.exchange}:candles:{inst_id}:{timeframe}:{limit}",
        )
        self._record_health(result)
        data = result.data.get("data") if isinstance(result.data, dict) else None
        if not result.ok or not isinstance(data, list):
            return []
        bars: list[KlineBar] = []
        for row in data:
            if not isinstance(row, list) or len(row) < 6:
                continue
            bars.append(
                KlineBar(
                    exchange=self.exchange,
                    symbol=self.unify_usdt_symbol(inst_id),
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

    @staticmethod
    def _to_okx_inst_id(symbol: str) -> str:
        clean = symbol.upper().replace("-", "")
        if clean.endswith("USDT"):
            base = clean[:-4]
            return f"{base}-USDT-SWAP"
        return symbol
