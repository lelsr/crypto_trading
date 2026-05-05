"""Kline provider that routes fetch plans to the correct exchange adapter."""

from __future__ import annotations

from domain.kline_policy import KlineFetchPlan
from domain.models import KlineBar
from infrastructure.exchanges.base import ExchangeAdapter


class KlineProvider:
    """Wraps exchange adapters to match the ScanOrchestrator kline interface."""

    def __init__(self, adapters: list[ExchangeAdapter]) -> None:
        self._by_exchange: dict[str, ExchangeAdapter] = {}
        for adapter in adapters:
            self._by_exchange[adapter.exchange] = adapter

    def available_exchanges_per_symbol(self, symbols: list[str]) -> dict[str, list[str]]:
        exchanges = sorted(self._by_exchange)
        return {symbol: exchanges for symbol in symbols}

    def fetch_klines(self, plan: KlineFetchPlan) -> list[KlineBar]:
        adapter = self._by_exchange.get(plan.primary_exchange)
        if adapter is None:
            raise KeyError(f"no adapter for primary_exchange={plan.primary_exchange}")
        return adapter.fetch_klines(plan.symbol, plan.timeframe, plan.limit)
