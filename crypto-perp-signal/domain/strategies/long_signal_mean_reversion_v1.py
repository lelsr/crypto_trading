"""Mean-reversion long signal strategy for Phase 14."""

from __future__ import annotations

from datetime import datetime

from models import IndicatorSnapshot, LongSignal
from structure_analyzer import StructureAnalysis


STRATEGY_NAME = "long_signal_mean_reversion_v1"


def generate_long_signal_mean_reversion_v1(
    analysis: StructureAnalysis,
    *,
    analysis_anchor_time: datetime,
    target_resistance: float | None = None,
    rsi_15m: float | None = None,
) -> LongSignal | None:
    snapshots = _required_snapshots(analysis)
    if snapshots is None:
        return None
    fifteen, one_hour, four_hour = snapshots
    if analysis.trend_broken or analysis.high_volatility:
        return None
    if _four_hour_strong_trend(four_hour):
        return None
    if fifteen.bollinger_lower is None or fifteen.bollinger_middle is None:
        return None
    if fifteen.close >= fifteen.bollinger_lower:
        return None
    if rsi_15m is not None and rsi_15m >= 30:
        return None

    entry_zone_low = fifteen.bollinger_lower * 0.995
    entry_zone_high = fifteen.bollinger_lower * 1.005
    stop = _mean_reversion_stop(entry_zone_low, fifteen)
    if stop is None:
        return None
    stop_loss, stop_reason, stop_source = stop
    target = target_resistance or fifteen.bollinger_middle
    rr = _risk_reward(entry_zone_high, stop_loss, target)
    if rr is None or rr < 2.0:
        return None

    score = _score(rr)
    level = _signal_level(score, rr)
    reasons = [
        f"signal_profile:{STRATEGY_NAME}",
        f"signal_level:{level}",
        f"rr:{rr:.2f}",
        "15m_close_below_lower_bollinger",
        "4h_not_strong_trend",
    ]
    if rsi_15m is not None:
        reasons.append("rsi_below_30")
    else:
        reasons.append("bb_oversold_substitute_for_rsi")
    return LongSignal(
        symbol=analysis.symbol,
        primary_exchange=analysis.primary_exchange,
        score=score,
        entry_zone_low=round(entry_zone_low, 8),
        entry_zone_high=round(entry_zone_high, 8),
        stop_loss=round(stop_loss, 8),
        stop_reason=stop_reason,
        timeframe_alignment=dict(analysis.timeframe_alignment),
        reasons=reasons,
        invalidation=f"15m close below stop_loss OR 15m close below {stop_source:.8g} OR high_volatility",
        created_at=analysis_anchor_time,
    )


def _required_snapshots(analysis: StructureAnalysis) -> tuple[IndicatorSnapshot, IndicatorSnapshot, IndicatorSnapshot] | None:
    try:
        return analysis.indicators["15m"], analysis.indicators["1h"], analysis.indicators["4h"]
    except KeyError:
        return None


def _four_hour_strong_trend(snapshot: IndicatorSnapshot) -> bool:
    if snapshot.ema20 is None or snapshot.ema60 is None:
        return False
    distance = abs(snapshot.ema20 - snapshot.ema60) / snapshot.close if snapshot.close else 0.0
    return snapshot.ema20 > snapshot.ema60 and snapshot.close > snapshot.ema20 and distance > 0.02


def _mean_reversion_stop(entry_zone_low: float, fifteen: IndicatorSnapshot) -> tuple[float, str, float] | None:
    candidates = [
        (fifteen.recent_swing_low, "15m swing low minus 0.3% buffer"),
        (fifteen.support_level, "15m support minus 0.3% buffer"),
        (fifteen.bollinger_lower * 0.985 if fifteen.bollinger_lower is not None else None, "15m Bollinger overshoot minus 0.3% buffer"),
    ]
    for source, reason in candidates:
        if source is not None and source < entry_zone_low:
            return source * 0.997, reason, source
    return None


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
        return 85.0
    if rr >= 2.5:
        return 78.0
    return 71.0


def _signal_level(score: float, rr: float) -> str:
    if score >= 85 and rr >= 3.0:
        return "A"
    if score >= 75 and rr >= 2.5:
        return "B"
    return "C"
