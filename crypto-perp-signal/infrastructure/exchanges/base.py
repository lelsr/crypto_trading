"""Exchange adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from domain.models import ExchangeTicker, KlineBar
from infrastructure.http_client import HttpClient, HttpResult


@dataclass(frozen=True)
class AdapterHealth:
    exchange: str
    source_status: str
    latency_ms: int | None
    message: str
    checked_at: datetime


class ExchangeAdapter(ABC):
    exchange: str

    def __init__(self, http_client: HttpClient) -> None:
        self.http_client = http_client
        self._last_health = AdapterHealth(
            exchange=self.exchange,
            source_status="skipped",
            latency_ms=None,
            message="not checked",
            checked_at=datetime.now(UTC),
        )

    @abstractmethod
    def fetch_usdt_perp_tickers(self) -> list[ExchangeTicker]:
        raise NotImplementedError

    def fetch_tickers(self) -> list[ExchangeTicker]:
        return self.fetch_usdt_perp_tickers()

    @abstractmethod
    def fetch_klines(self, symbol: str, timeframe: str, limit: int) -> list[KlineBar]:
        raise NotImplementedError

    def fetch_funding_rate(self, symbol: str) -> dict[str, Any] | None:
        return None

    def fetch_open_interest(self, symbol: str) -> dict[str, Any] | None:
        return None

    def health_check(self) -> AdapterHealth:
        return self._last_health

    def _record_health(self, result: HttpResult, message: str | None = None) -> None:
        self._last_health = AdapterHealth(
            exchange=self.exchange,
            source_status=result.source_status,
            latency_ms=result.latency_ms,
            message=message or result.error_message or result.source_status,
            checked_at=datetime.now(UTC),
        )

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _ms_to_datetime(value: Any) -> datetime:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)

    @staticmethod
    def unify_usdt_symbol(raw_symbol: str) -> str:
        symbol = raw_symbol.upper()
        for suffix in ("-USDT-SWAP", "_USDT", "-USDT", "USDTM"):
            symbol = symbol.replace(suffix, "USDT")
        symbol = symbol.replace("-", "").replace("_", "")
        return symbol
