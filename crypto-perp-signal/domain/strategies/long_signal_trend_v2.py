"""Trend-following long signal strategy for Phase 14."""

from __future__ import annotations

from datetime import datetime

from models import IndicatorSnapshot, LongSignal
from structure_analyzer import StructureAnalysis


STRATEGY_NAME = "long_signal_trend_v2"


def generate_long_signal_trend_v2(
    analysis: StructureAnalysis,
    *,
    analysis_anchor_time: datetime,
    previous_4h_ema20: float | None,
    target_resistance: float | None = None,
) -> LongSignal | None:
    if _blocked_by_common_risk(analysis):
        return None
    snapshots = _required_snapshots(analysis)
    if snapshots is None:
        return None
    fifteen, one_hour, four_hour = snapshots
    if four_hour.ema20 is None or four_hour.ema60 is None or one_hour.ema20 is None or one_hour.ema60 is None:
        return None
    if previous_4h_ema20 is None:
        return None
    if not (four_hour.ema20 > four_hour.ema60 and four_hour.ema20 > previous_4h_ema20):
        return None
    if not one_hour.ema20 > one_hour.ema60:
        return None
    if fifteen.ema20 is None or fifteen.close <= 0:
        return None
    if abs(fifteen.close - fifteen.ema20) / fifteen.ema20 > 0.01:
        return None

    entry_zone_low = fifteen.ema20 * 0.99
    entry_zone_high = fifteen.ema20 * 1.01
    stop = _trend_stop(entry_zone_low, fifteen, one_hour, four_hour)
    if stop is None:
        return None
    stop_loss, stop_reason, stop_source = stop
    rr = _risk_reward(entry_zone_high, stop_loss, target_resistance or _default_target(entry_zone_high, four_hour))
    if rr is None or rr < 2.0:
        return None

    score = _score(rr)
    level = _signal_level(score, rr)
    return LongSignal(
        symbol=analysis.symbol,
        primary_exchange=analysis.primary_exchange,
        score=score,
        entry_zone_low=round(entry_zone_low, 8),
        entry_zone_high=round(entry_zone_high, 8),
        stop_loss=round(stop_loss, 8),
        stop_reason=stop_reason,
        timeframe_alignment=dict(analysis.timeframe_alignment),
        reasons=[
            f"signal_profile:{STRATEGY_NAME}",
            f"signal_level:{level}",
            f"rr:{rr:.2f}",
            "4h_ema20_above_ema60_with_positive_slope",
            "1h_ema20_above_ema60",
            "15m_pullback_to_ema20",
        ],
        invalidation=f"15m close below stop_loss OR 1h close below {stop_source:.8g} OR trend_broken OR high_volatility",
        created_at=analysis_anchor_time,
    )


def _blocked_by_common_risk(analysis: StructureAnalysis) -> bool:
    return analysis.chase_risk or analysis.trend_broken or analysis.high_volatility


def _required_snapshots(analysis: StructureAnalysis) -> tuple[IndicatorSnapshot, IndicatorSnapshot, IndicatorSnapshot] | None:
    try:
        return analysis.indicators["15m"], analysis.indicators["1h"], analysis.indicators["4h"]
    except KeyError:
        return None


def _trend_stop(
    entry_zone_low: float,
    fifteen: IndicatorSnapshot,
    one_hour: IndicatorSnapshot,
    four_hour: IndicatorSnapshot,
) -> tuple[float, str, float] | None:
    candidates = [
        (four_hour.support_level, "4h support minus 0.3% buffer"),
        (one_hour.recent_swing_low, "1h swing low minus 0.3% buffer"),
        (fifteen.bollinger_lower, "15m Bollinger lower minus 0.3% buffer"),
        (one_hour.ema60, "1h EMA60 minus 0.3% buffer"),
    ]
    for source, reason in candidates:
        if source is not None and source < entry_zone_low:
            return source * 0.997, reason, source
    return None


def _default_target(entry_zone_high: float, four_hour: IndicatorSnapshot) -> float | None:
    if four_hour.support_level is None:
        return None
    target = four_hour.close + (four_hour.close - four_hour.support_level)
    return target if target > entry_zone_high else None


def _risk_reward(entry_zone_high: float, stop_loss: float, target: float | None) -> float | None:
    if target is None:
        return None
    risk = entry_zone_high - stop_loss
    reward = target - entry_zone_high
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


def _score(rr: float) -> float:
    if rr >= 3.0:
        return 88.0
    if rr >= 2.5:
        return 80.0
    return 72.0


def _signal_level(score: float, rr: float) -> str:
    if score >= 85 and rr >= 3.0:
        return "A"
    if score >= 75 and rr >= 2.5:
        return "B"
    return "C"
