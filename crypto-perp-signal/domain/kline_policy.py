"""Kline fetch planning and validation policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from models import KlineBar, UnifiedActivityCandidate, require_timezone_aware


TIMEFRAME_MINUTES = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
}


@dataclass(frozen=True)
class KlineFetchPlan:
    symbol: str
    primary_exchange: str
    timeframe: str
    limit: int
    cache_key: str
    required: bool
    reason: str


@dataclass(frozen=True)
class TimeframeAlignment:
    analysis_anchor_time: datetime
    selected_open_times: dict[str, datetime]
    alignment_status: dict[str, str]
    is_valid: bool
    reason: str


def build_kline_fetch_plan(
    candidates: list[UnifiedActivityCandidate],
    *,
    final_top_m_symbols: set[str],
    timeframes: list[str],
    limit: int,
) -> list[KlineFetchPlan]:
    plans: list[KlineFetchPlan] = []
    for candidate in candidates:
        if candidate.symbol not in final_top_m_symbols:
            continue
        if not candidate.primary_exchange:
            continue
        for timeframe in timeframes:
            plans.append(
                KlineFetchPlan(
                    symbol=candidate.symbol,
                    primary_exchange=candidate.primary_exchange,
                    timeframe=timeframe,
                    limit=limit,
                    cache_key=f"kline:{candidate.primary_exchange}:{candidate.symbol}:{timeframe}:{limit}",
                    required=True,
                    reason="final_top_m_primary_exchange_only",
                )
            )
    return plans


def validate_primary_exchange_klines(
    *,
    symbol: str,
    primary_exchange: str,
    bars_by_timeframe: dict[str, list[KlineBar]],
) -> None:
    for timeframe, bars in bars_by_timeframe.items():
        for bar in bars:
            if bar.symbol != symbol:
                raise ValueError(f"{timeframe} contains mismatched symbol: {bar.symbol}")
            if bar.exchange != primary_exchange:
                raise ValueError(f"{timeframe} contains non-primary exchange kline: {bar.exchange}")


def align_closed_timeframes(
    *,
    bars_by_timeframe: dict[str, list[KlineBar]],
    as_of: datetime,
    base_timeframe: str = "15m",
) -> TimeframeAlignment:
    require_timezone_aware(as_of, "as_of")
    if base_timeframe not in bars_by_timeframe:
        raise ValueError("base timeframe is missing")

    closed_by_timeframe = {
        timeframe: _closed_bars(bars, timeframe, as_of)
        for timeframe, bars in bars_by_timeframe.items()
    }
    base_closed = closed_by_timeframe.get(base_timeframe, [])
    if not base_closed:
        raise ValueError("no closed base timeframe bars")

    anchor = max(base_closed, key=lambda bar: bar.open_time).open_time
    selected: dict[str, datetime] = {base_timeframe: anchor}
    statuses: dict[str, str] = {base_timeframe: "anchor_closed_bar"}

    for timeframe in ("1h", "4h"):
        if timeframe not in closed_by_timeframe:
            return TimeframeAlignment(anchor, selected, statuses, False, f"{timeframe} missing")
        match = _bar_covering_anchor(closed_by_timeframe[timeframe], timeframe, anchor)
        if match is not None:
            selected[timeframe] = match.open_time
            statuses[timeframe] = "aligned_closed_bar"
            continue
        lagged = _latest_before_anchor(closed_by_timeframe[timeframe], anchor)
        if lagged is None:
            return TimeframeAlignment(anchor, selected, statuses, False, f"{timeframe} cannot align")
        selected[timeframe] = lagged.open_time
        statuses[timeframe] = "lagged_closed_bar"

    return TimeframeAlignment(anchor, selected, statuses, True, "aligned")


def _closed_bars(bars: list[KlineBar], timeframe: str, as_of: datetime) -> list[KlineBar]:
    minutes = TIMEFRAME_MINUTES[timeframe]
    return [
        bar
        for bar in bars
        if bar.open_time + timedelta(minutes=minutes) <= as_of
    ]


def _bar_covering_anchor(bars: list[KlineBar], timeframe: str, anchor: datetime) -> KlineBar | None:
    minutes = TIMEFRAME_MINUTES[timeframe]
    for bar in bars:
        if bar.open_time <= anchor < bar.open_time + timedelta(minutes=minutes):
            return bar
    return None


def _latest_before_anchor(bars: list[KlineBar], anchor: datetime) -> KlineBar | None:
    before = [bar for bar in bars if bar.open_time <= anchor]
    if not before:
        return None
    return max(before, key=lambda bar: bar.open_time)
