"""Long signal strategy V1 using Phase 8 structure analysis output."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from models import IndicatorSnapshot, LongSignal
from structure_analyzer import StructureAnalysis


@dataclass(frozen=True)
class RecentSignalRef:
    symbol: str
    exchange: str
    signal_profile: str
    created_at: datetime
    invalidated: bool = False


@dataclass(frozen=True)
class LongSignalDecision:
    signal: LongSignal | None
    reasons: list[str]
    score: float | None = None
    rr: float | None = None
    signal_level: str | None = None
    should_push: bool = False


def generate_long_signal_v1(
    analysis: StructureAnalysis,
    *,
    analysis_anchor_time: datetime,
    signal_profile: str = "default",
    recent_signals: list[RecentSignalRef] | None = None,
    cooldown_hours: int = 6,
    previous_4h_ema20: float | None = None,
    target_resistance: float | None = None,
) -> LongSignalDecision:
    """Generate a long signal from already validated multi-timeframe structure."""

    recent_signals = recent_signals or []
    gate_reason = _first_gate_reason(
        analysis=analysis,
        analysis_anchor_time=analysis_anchor_time,
        signal_profile=signal_profile,
        recent_signals=recent_signals,
        cooldown_hours=cooldown_hours,
        previous_4h_ema20=previous_4h_ema20,
    )
    if gate_reason is not None:
        return LongSignalDecision(signal=None, reasons=[gate_reason])

    missing_reason = _missing_required_reason(analysis)
    if missing_reason is not None:
        return LongSignalDecision(signal=None, reasons=[missing_reason])

    indicators = analysis.indicators
    fifteen = indicators["15m"]
    one_hour = indicators["1h"]
    four_hour = indicators["4h"]

    entry_zone = _build_entry_zone(fifteen)
    if entry_zone is None:
        return LongSignalDecision(signal=None, reasons=["invalid_entry_zone"])
    entry_zone_low, entry_zone_high = entry_zone
    if (entry_zone_high - entry_zone_low) / entry_zone_high > 0.015:
        return LongSignalDecision(signal=None, reasons=["entry_zone_too_wide"])
    if fifteen.close > entry_zone_high * 1.02:
        return LongSignalDecision(signal=None, reasons=["price_above_entry_zone"])

    stop = _build_stop_loss(
        entry_zone_low=entry_zone_low,
        fifteen=fifteen,
        one_hour=one_hour,
        four_hour=four_hour,
    )
    if stop is None:
        return LongSignalDecision(signal=None, reasons=["missing_stop_source"])
    stop_loss, stop_reason, stop_source_price = stop

    stop_distance = (entry_zone_low - stop_loss) / entry_zone_low
    if stop_distance < 0.005:
        return LongSignalDecision(signal=None, reasons=["stop_too_close"])
    if stop_distance > 0.08:
        return LongSignalDecision(signal=None, reasons=["stop_too_far"])

    rr_result = _calculate_rr(
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        stop_loss=stop_loss,
        one_hour=one_hour,
        four_hour=four_hour,
        target_resistance=target_resistance,
    )
    if rr_result is None:
        return LongSignalDecision(signal=None, reasons=["missing_target_source"])
    rr, target_ref = rr_result
    if rr < 2.0:
        return LongSignalDecision(signal=None, reasons=["rr_below_2"], rr=round(rr, 6))

    score = _score_signal(
        analysis=analysis,
        stop_distance=stop_distance,
        rr=rr,
        previous_4h_ema20=previous_4h_ema20,
    )
    if score < 70:
        return LongSignalDecision(signal=None, reasons=["score_below_threshold"], score=score, rr=round(rr, 6))

    signal_level = _signal_level(score=score, rr=rr, stop_distance=stop_distance)
    should_push = signal_level in {"A", "B"}
    reasons = [
        "gates_passed",
        f"rr:{rr:.2f}",
        f"target_ref:{target_ref:.8g}",
        f"signal_level:{signal_level}",
        f"should_push:{str(should_push).lower()}",
    ]
    reasons.extend(_score_reasons(analysis))

    signal = LongSignal(
        symbol=analysis.symbol,
        primary_exchange=analysis.primary_exchange,
        score=score,
        entry_zone_low=round(entry_zone_low, 8),
        entry_zone_high=round(entry_zone_high, 8),
        stop_loss=round(stop_loss, 8),
        stop_reason=stop_reason,
        timeframe_alignment=dict(analysis.timeframe_alignment),
        reasons=reasons,
        invalidation=_invalidation_text(stop_source_price=stop_source_price),
        created_at=analysis_anchor_time,
    )
    return LongSignalDecision(
        signal=signal,
        reasons=reasons,
        score=score,
        rr=round(rr, 6),
        signal_level=signal_level,
        should_push=should_push,
    )


def _first_gate_reason(
    *,
    analysis: StructureAnalysis,
    analysis_anchor_time: datetime,
    signal_profile: str,
    recent_signals: list[RecentSignalRef],
    cooldown_hours: int,
    previous_4h_ema20: float | None,
) -> str | None:
    if analysis.trend_broken:
        return "trend_broken_gate"
    if analysis.high_volatility:
        return "high_volatility_gate"
    if analysis.chase_risk:
        return "chase_risk_gate"
    if analysis.support_too_close:
        return "support_too_close_gate"
    if _four_hour_bearish_gate(analysis.indicators.get("4h"), previous_4h_ema20):
        return "4h_bearish_gate"
    cooldown_reason = _cooldown_reason(
        symbol=analysis.symbol,
        exchange=analysis.primary_exchange,
        signal_profile=signal_profile,
        analysis_anchor_time=analysis_anchor_time,
        recent_signals=recent_signals,
        cooldown_hours=cooldown_hours,
    )
    return cooldown_reason


def _missing_required_reason(analysis: StructureAnalysis) -> str | None:
    required = {"15m", "1h", "4h"}
    missing = sorted(required - set(analysis.indicators))
    if missing:
        return f"missing_timeframe:{missing[0]}"
    for timeframe in sorted(required):
        snapshot = analysis.indicators[timeframe]
        for field_name in ("ema20", "ema60", "bollinger_lower", "bollinger_middle", "bollinger_upper"):
            if getattr(snapshot, field_name) is None:
                return f"insufficient_data:{timeframe}:{field_name}"
    for timeframe in ("1h", "4h"):
        snapshot = analysis.indicators[timeframe]
        if snapshot.macd is None or snapshot.macd_signal is None or snapshot.macd_histogram is None:
            return f"insufficient_data:{timeframe}:macd"
    if analysis.indicators["15m"].support_level is None:
        return "missing_support"
    if analysis.indicators["4h"].support_level is None:
        return "missing_support"
    return None


def _build_entry_zone(snapshot: IndicatorSnapshot) -> tuple[float, float] | None:
    if snapshot.ema20 is None or snapshot.bollinger_middle is None or snapshot.support_level is None:
        return None
    if snapshot.support_level >= snapshot.ema20 * 1.02:
        return None
    if snapshot.support_level >= snapshot.bollinger_middle * 1.02:
        return None
    structural_mid = median([snapshot.ema20, snapshot.bollinger_middle, snapshot.support_level * 1.005])
    entry_zone_low = max(snapshot.support_level * 1.002, structural_mid * 0.997)
    entry_zone_high = min(snapshot.ema20 * 1.003, snapshot.bollinger_middle * 1.003, structural_mid * 1.003)
    if entry_zone_low > entry_zone_high:
        return None
    return entry_zone_low, entry_zone_high


def _build_stop_loss(
    *,
    entry_zone_low: float,
    fifteen: IndicatorSnapshot,
    one_hour: IndicatorSnapshot,
    four_hour: IndicatorSnapshot,
) -> tuple[float, str, float] | None:
    candidates = [
        (four_hour.support_level, "4h support minus 0.3% buffer"),
        (one_hour.recent_swing_low, "1h swing low minus 0.3% buffer"),
        (fifteen.bollinger_lower, "15m Bollinger lower minus 0.3% buffer"),
    ]
    ema60_candidates = [value for value in (fifteen.ema60, one_hour.ema60) if value is not None and value < entry_zone_low]
    if ema60_candidates:
        candidates.append((max(ema60_candidates), "EMA60 minus 0.3% buffer"))

    for source_price, reason in candidates:
        if source_price is not None and source_price < entry_zone_low:
            return source_price * 0.997, reason, source_price
    return None


def _calculate_rr(
    *,
    entry_zone_low: float,
    entry_zone_high: float,
    stop_loss: float,
    one_hour: IndicatorSnapshot,
    four_hour: IndicatorSnapshot,
    target_resistance: float | None,
) -> tuple[float, float] | None:
    entry_for_rr = (entry_zone_low + entry_zone_high) / 2
    if target_resistance is not None and target_resistance > entry_zone_high:
        target_ref = target_resistance
        risk = entry_for_rr - stop_loss
        reward = target_ref - entry_for_rr
        if risk <= 0 or reward <= 0:
            return None
        return reward / risk, target_ref

    targets = []
    if one_hour.bollinger_upper is not None and one_hour.bollinger_upper > entry_zone_high:
        targets.append(one_hour.bollinger_upper)
    if four_hour.support_level is not None:
        measured_target = four_hour.close + (four_hour.close - four_hour.support_level)
        if measured_target > entry_zone_high:
            targets.append(measured_target)
    if not targets:
        return None
    target_ref = min(targets)
    risk = entry_for_rr - stop_loss
    reward = target_ref - entry_for_rr
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk, target_ref


def _score_signal(
    *,
    analysis: StructureAnalysis,
    stop_distance: float,
    rr: float,
    previous_4h_ema20: float | None,
) -> float:
    fifteen = analysis.indicators["15m"]
    one_hour = analysis.indicators["1h"]
    four_hour = analysis.indicators["4h"]
    score = 0.0

    if four_hour.ema60 is not None and four_hour.close >= four_hour.ema60:
        score += 10
    if four_hour.support_level is not None and four_hour.support_level < four_hour.close:
        score += 8
    if four_hour.support_level is not None and (four_hour.close - four_hour.support_level) / four_hour.close <= 0.03:
        score += 4
    if four_hour.ema20 is not None and four_hour.close >= four_hour.ema20:
        score += 3

    if one_hour.ema20 is not None and one_hour.close >= one_hour.ema20:
        score += 8
    if one_hour.ema20 is not None and one_hour.ema60 is not None and one_hour.ema20 >= one_hour.ema60:
        score += 6
    if one_hour.macd_histogram is not None and one_hour.macd_histogram > 0:
        score += 5
    if one_hour.macd is not None and one_hour.macd_signal is not None and one_hour.macd >= one_hour.macd_signal:
        score += 3

    if fifteen.ema20 is not None and fifteen.close >= fifteen.ema20:
        score += 8
    if fifteen.bollinger_middle is not None and fifteen.close >= fifteen.bollinger_middle:
        score += 5
    if fifteen.support_level is not None and fifteen.support_level < fifteen.close:
        score += 5
    if fifteen.support_level is not None and 0.005 <= (fifteen.close - fifteen.support_level) / fifteen.close <= 0.03:
        score += 4
    if fifteen.ema20 not in (None, 0) and abs(fifteen.close - fifteen.ema20) / fifteen.ema20 <= 0.01:
        score += 3

    if not analysis.chase_risk:
        score += 6
    if not analysis.support_too_close:
        score += 4
    if not analysis.trend_broken:
        score += 5
    if not analysis.high_volatility:
        score += 4
    if not _four_hour_bearish_gate(four_hour, previous_4h_ema20):
        score += 4
    if rr >= 2.0:
        score += 4
    if 0.01 <= stop_distance <= 0.05:
        score += 2

    return round(min(score, 100.0), 2)


def _score_reasons(analysis: StructureAnalysis) -> list[str]:
    reasons: list[str] = []
    four_hour = analysis.indicators["4h"]
    one_hour = analysis.indicators["1h"]
    fifteen = analysis.indicators["15m"]
    if four_hour.ema60 is not None and four_hour.close >= four_hour.ema60:
        reasons.append("4h_close_above_ema60")
    if one_hour.macd_histogram is not None and one_hour.macd_histogram > 0:
        reasons.append("1h_macd_histogram_positive")
    if fifteen.support_level is not None and fifteen.support_level < fifteen.close:
        reasons.append("15m_support_confirmed")
    return reasons


def _signal_level(*, score: float, rr: float, stop_distance: float) -> str:
    if score >= 85 and rr >= 3.0 and 0.01 <= stop_distance <= 0.05:
        return "A"
    if score >= 75 and rr >= 2.5:
        return "B"
    return "C"


def _four_hour_bearish_gate(snapshot: IndicatorSnapshot | None, previous_4h_ema20: float | None) -> bool:
    if snapshot is None or snapshot.ema20 is None or snapshot.ema60 is None or previous_4h_ema20 is None:
        return False
    return snapshot.close < snapshot.ema60 and snapshot.ema20 < snapshot.ema60 and snapshot.ema20 < previous_4h_ema20


def _cooldown_reason(
    *,
    symbol: str,
    exchange: str,
    signal_profile: str,
    analysis_anchor_time: datetime,
    recent_signals: list[RecentSignalRef],
    cooldown_hours: int,
) -> str | None:
    bounded_hours = min(max(cooldown_hours, 4), 8)
    window = timedelta(hours=bounded_hours)
    matching = [
        signal
        for signal in recent_signals
        if signal.symbol == symbol
        and signal.exchange == exchange
        and signal.signal_profile == signal_profile
        and not signal.invalidated
        and analysis_anchor_time >= signal.created_at
        and analysis_anchor_time - signal.created_at < window
    ]
    if not matching:
        return None
    latest = max(matching, key=lambda signal: signal.created_at)
    remaining = window - (analysis_anchor_time - latest.created_at)
    return f"cooldown_active:{int(remaining.total_seconds() // 60)}"


def _invalidation_text(*, stop_source_price: float) -> str:
    return (
        f"15m close below stop_loss OR 1h close below {stop_source_price:.8g} "
        "OR trend_broken OR high_volatility"
    )
