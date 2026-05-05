"""Domain data models for crypto perpetual signal scanning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


SignalStatus = Literal[
    "created",
    "notified",
    "monitoring",
    "tp1_hit",
    "stopped",
    "expired",
    "manual_reviewed",
]

ManualVerdict = Literal["good", "bad", "neutral", "missed", "false_breakout"]
MarketCapStatus = Literal["known", "unknown", "failed"]
SourceStatus = Literal["ok", "failed", "partial", "stale_cache", "skipped"]


def require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class ExchangeTicker:
    exchange: str
    raw_symbol: str
    unified_symbol: str
    quote_volume_24h_usd: float | None
    base_volume_24h: float | None
    last_price: float | None
    price_change_pct_24h: float | None
    source_status: SourceStatus | str
    latency_ms: int | None
    updated_at: datetime

    def __post_init__(self) -> None:
        require_timezone_aware(self.updated_at, "updated_at")


@dataclass(frozen=True)
class UnifiedActivityCandidate:
    symbol: str
    exchanges: list[str]
    primary_exchange: str | None
    activity_score: float
    global_quote_volume_24h_usd: float | None
    market_cap_usd: float | None
    market_cap_status: MarketCapStatus | str
    source_status: SourceStatus | str
    exchange_scores: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class KlineBar:
    exchange: str
    symbol: str
    timeframe: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        require_timezone_aware(self.open_time, "open_time")


@dataclass(frozen=True)
class IndicatorSnapshot:
    exchange: str
    symbol: str
    timeframe: str
    calculated_at: datetime
    close: float
    ema20: float | None
    ema60: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    bollinger_upper: float | None
    bollinger_middle: float | None
    bollinger_lower: float | None
    volume_ma: float | None
    recent_swing_low: float | None
    support_level: float | None

    def __post_init__(self) -> None:
        require_timezone_aware(self.calculated_at, "calculated_at")


@dataclass(frozen=True)
class PrimaryExchangeDecision:
    symbol: str
    primary_exchange: str
    primary_score: float
    candidate_exchanges: list[str]
    score_breakdown: dict[str, float]
    reason: str
    decided_at: datetime

    def __post_init__(self) -> None:
        require_timezone_aware(self.decided_at, "decided_at")


@dataclass(frozen=True)
class LongSignal:
    symbol: str
    primary_exchange: str
    score: float
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    stop_reason: str
    timeframe_alignment: dict[str, Any]
    reasons: list[str]
    invalidation: str
    created_at: datetime

    def __post_init__(self) -> None:
        require_timezone_aware(self.created_at, "created_at")
        if self.entry_zone_low > self.entry_zone_high:
            raise ValueError("entry_zone_low must be <= entry_zone_high")


@dataclass(frozen=True)
class SignalLifecycleRecord:
    signal_id: str
    symbol: str
    primary_exchange: str
    status: SignalStatus | str
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    max_favorable_excursion: float | None
    max_adverse_excursion: float | None
    stop_touched: bool
    target_touched: bool
    duration_minutes: int | None
    manual_verdict: ManualVerdict | str | None
    manual_notes: str | None
    manual_tags: list[str]
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None

    def __post_init__(self) -> None:
        require_timezone_aware(self.created_at, "created_at")
        require_timezone_aware(self.updated_at, "updated_at")
        if self.reviewed_at is not None:
            require_timezone_aware(self.reviewed_at, "reviewed_at")
        if self.entry_zone_low > self.entry_zone_high:
            raise ValueError("entry_zone_low must be <= entry_zone_high")


@dataclass(frozen=True)
class ManualReview:
    review_id: str
    signal_id: str
    manual_verdict: ManualVerdict | str
    manual_notes: str
    manual_tags: list[str]
    reviewed_at: datetime

    def __post_init__(self) -> None:
        require_timezone_aware(self.reviewed_at, "reviewed_at")
