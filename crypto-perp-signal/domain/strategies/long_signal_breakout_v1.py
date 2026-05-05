"""Breakout long signal strategy for Phase 14."""

from __future__ import annotations

from datetime import datetime

from models import IndicatorSnapshot, LongSignal
from structure_analyzer import StructureAnalysis


STRATEGY_NAME = "long_signal_breakout_v1"


def generate_long_signal_breakout_v1(
    analysis: StructureAnalysis,
    *,
    analysis_anchor_time: datetime,
    recent_15m_highs: list[float],
    latest_15m_volume: float,
    target_resistance: float | None = None,
) -> LongSignal | None:
    snapshots = _required_snapshots(analysis)
    if snapshots is None or len(recent_15m_highs) < 20:
        return None
    fifteen, one_hour, four_hour = snapshots
    breakout_level = max(recent_15m_highs[-20:])
    if fifteen.close <= breakout_level:
        return None
    if fifteen.volume_ma is None or latest_15m_volume <= fifteen.volume_ma * 1.5:
        return None
    if _one_hour_obvious_downtrend(one_hour):
        return None
    if analysis.trend_broken:
        return None

    entry_zone_low = breakout_level * 0.995
    entry_zone_high = breakout_level * 1.005
    stop = _breakout_stop(entry_zone_low, fifteen, one_hour)
    if stop is None:
        return None
    stop_loss, stop_reason, stop_source = stop
    target = target_resistance or _default_target(entry_zone_high, fifteen, four_hour)
    rr = _risk_reward(entry_zone_high, stop_loss, target)
    if rr is None or rr < 2.0:
        return None

    score = _score(rr, latest_15m_volume / fifteen.volume_ma)
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
            f"breakout_level:{breakout_level:.8g}",
            "15m_close_above_recent_20_high",
            "volume_expansion_above_1_5x_ma",
        ],
        invalidation=f"15m close below stop_loss OR close back below breakout level {breakout_level:.8g} OR 1h close below {stop_source:.8g}",
        created_at=analysis_anchor_time,
    )


def _required_snapshots(analysis: StructureAnalysis) -> tuple[IndicatorSnapshot, IndicatorSnapshot, IndicatorSnapshot] | None:
    try:
        return analysis.indicators["15m"], analysis.indicators["1h"], analysis.indicators["4h"]
    except KeyError:
        return None


def _one_hour_obvious_downtrend(snapshot: IndicatorSnapshot) -> bool:
    if snapshot.ema20 is None or snapshot.ema60 is None:
        return False
    return snapshot.close < snapshot.ema20 < snapshot.ema60


def _breakout_stop(
    entry_zone_low: float,
    fifteen: IndicatorSnapshot,
    one_hour: IndicatorSnapshot,
) -> tuple[float, str, float] | None:
    candidates = [
        (fifteen.support_level, "15m support minus 0.3% buffer"),
        (fifteen.ema20, "15m EMA20 minus 0.3% buffer"),
        (one_hour.recent_swing_low, "1h swing low minus 0.3% buffer"),
    ]
    for source, reason in candidates:
        if source is not None and source < entry_zone_low:
            return source * 0.997, reason, source
    return None


def _default_target(entry_zone_high: float, fifteen: IndicatorSnapshot, four_hour: IndicatorSnapshot) -> float | None:
    targets = []
    if fifteen.bollinger_upper is not None and fifteen.bollinger_upper > entry_zone_high:
        targets.append(fifteen.bollinger_upper)
    if four_hour.bollinger_upper is not None and four_hour.bollinger_upper > entry_zone_high:
        targets.append(four_hour.bollinger_upper)
    return min(targets) if targets else None


def _risk_reward(entry_zone_high: float, stop_loss: float, target: float | None) -> float | None:
    if target is None:
        return None
    risk = entry_zone_high - stop_loss
    reward = target - entry_zone_high
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


def _score(rr: float, volume_multiple: float) -> float:
    base = 76.0 if rr >= 2.5 else 72.0
    if rr >= 3.0:
        base = 86.0
    if volume_multiple >= 2.0:
        base += 4.0
    return min(base, 95.0)


def _signal_level(score: float, rr: float) -> str:
    if score >= 85 and rr >= 3.0:
        return "A"
    if score >= 75 and rr >= 2.5:
        return "B"
    return "C"
