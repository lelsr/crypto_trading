"""Multi-timeframe structure analysis helpers."""

from __future__ import annotations

from dataclasses import dataclass

from indicators import calculate_indicator_snapshot
from indicators import ema_series
from kline_policy import align_closed_timeframes, validate_primary_exchange_klines
from models import IndicatorSnapshot, KlineBar
from support_resistance import identify_support_level


@dataclass(frozen=True)
class StructureAnalysis:
    symbol: str
    primary_exchange: str
    is_valid: bool
    reasons: list[str]
    timeframe_alignment: dict[str, str]
    indicators: dict[str, IndicatorSnapshot]
    support_levels: dict[str, float | None]
    chase_risk: bool
    support_too_close: bool
    trend_broken: bool
    high_volatility: bool


def analyze_structure(
    *,
    symbol: str,
    primary_exchange: str,
    bars_by_timeframe: dict[str, list[KlineBar]],
    as_of,
    max_ema20_deviation_pct: float = 0.02,
    min_support_distance_pct: float = 0.005,
    max_15m_range_pct: float = 0.05,
) -> StructureAnalysis:
    validate_primary_exchange_klines(
        symbol=symbol,
        primary_exchange=primary_exchange,
        bars_by_timeframe=bars_by_timeframe,
    )
    alignment = align_closed_timeframes(bars_by_timeframe=bars_by_timeframe, as_of=as_of)
    reasons: list[str] = []
    if not alignment.is_valid:
        return StructureAnalysis(
            symbol=symbol,
            primary_exchange=primary_exchange,
            is_valid=False,
            reasons=[alignment.reason],
            timeframe_alignment=alignment.alignment_status,
            indicators={},
            support_levels={},
            chase_risk=False,
            support_too_close=False,
            trend_broken=False,
            high_volatility=False,
        )

    indicators: dict[str, IndicatorSnapshot] = {}
    support_levels: dict[str, float | None] = {}
    selected_bars_by_timeframe: dict[str, list[KlineBar]] = {}
    for timeframe, bars in bars_by_timeframe.items():
        selected_open = alignment.selected_open_times.get(timeframe)
        if selected_open is None:
            continue
        selected_bars = [bar for bar in bars if bar.open_time <= selected_open]
        selected_bars_by_timeframe[timeframe] = selected_bars
        snapshot = calculate_indicator_snapshot(
            selected_bars,
            primary_exchange=primary_exchange,
            timeframe=timeframe,
            calculated_at=alignment.analysis_anchor_time,
        )
        if snapshot is None:
            reasons.append(f"{timeframe} insufficient_data")
            continue
        support = identify_support_level(selected_bars)
        indicators[timeframe] = snapshot
        support_levels[timeframe] = support.price

    required = {"15m", "1h", "4h"}
    missing = sorted(required - set(indicators))
    if missing:
        reasons.extend([f"{timeframe} missing_indicator" for timeframe in missing])

    chase_risk = _is_chasing(indicators.get("15m"), max_ema20_deviation_pct)
    if chase_risk:
        reasons.append("15m close deviates from EMA20 by more than 2%")

    support_too_close = _is_support_too_close(
        entry_snapshot=indicators.get("15m"),
        support_price=support_levels.get("15m"),
        min_distance_pct=min_support_distance_pct,
    )
    if support_too_close:
        reasons.append("15m support is less than 0.5% below entry")

    trend_broken = _is_trend_broken(
        bars_15m=selected_bars_by_timeframe.get("15m", []),
        bars_1h=selected_bars_by_timeframe.get("1h", []),
    )
    if trend_broken:
        reasons.append("trend_broken blocks long signal")

    high_volatility = _is_high_volatility(
        selected_bars_by_timeframe.get("15m", []),
        max_range_pct=max_15m_range_pct,
    )
    if high_volatility:
        reasons.append("15m range is above 5% of close")

    return StructureAnalysis(
        symbol=symbol,
        primary_exchange=primary_exchange,
        is_valid=not missing and not chase_risk and not support_too_close and not trend_broken and not high_volatility,
        reasons=reasons or ["structure_analyzed"],
        timeframe_alignment=alignment.alignment_status,
        indicators=indicators,
        support_levels=support_levels,
        chase_risk=chase_risk,
        support_too_close=support_too_close,
        trend_broken=trend_broken,
        high_volatility=high_volatility,
    )


def _is_chasing(snapshot: IndicatorSnapshot | None, max_deviation_pct: float) -> bool:
    if snapshot is None or snapshot.ema20 in (None, 0):
        return False
    return (snapshot.close - snapshot.ema20) / snapshot.ema20 > max_deviation_pct


def _is_support_too_close(
    *,
    entry_snapshot: IndicatorSnapshot | None,
    support_price: float | None,
    min_distance_pct: float,
) -> bool:
    if entry_snapshot is None or support_price is None or entry_snapshot.close <= 0:
        return False
    return (entry_snapshot.close - support_price) / entry_snapshot.close < min_distance_pct


def _is_trend_broken(*, bars_15m: list[KlineBar], bars_1h: list[KlineBar]) -> bool:
    sorted_15m = sorted(bars_15m, key=lambda bar: bar.open_time)
    if len(sorted_15m) >= 3:
        recent_lows = [bar.low for bar in sorted_15m[-3:]]
        if recent_lows[0] > recent_lows[1] > recent_lows[2]:
            return True

    sorted_1h = sorted(bars_1h, key=lambda bar: bar.open_time)
    closes = [bar.close for bar in sorted_1h]
    ema20_values = [value for value in ema_series(closes, 20) if value is not None]
    ema60_values = [value for value in ema_series(closes, 60) if value is not None]
    if len(ema20_values) < 2 or not ema60_values:
        return False
    return ema20_values[-1] < ema60_values[-1] and ema20_values[-1] < ema20_values[-2]


def _is_high_volatility(bars_15m: list[KlineBar], *, max_range_pct: float) -> bool:
    if not bars_15m:
        return False
    latest = sorted(bars_15m, key=lambda bar: bar.open_time)[-1]
    if latest.close <= 0:
        return False
    return (latest.high - latest.low) / latest.close > max_range_pct
