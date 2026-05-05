"""Signal lifecycle tracking calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TrackingEvaluation:
    signal_id: str
    status: str
    entry_ref: float
    risk_per_unit: float
    tp1: float
    tp2: float
    tp3: float
    max_favorable_excursion_pct: float
    max_adverse_excursion_pct: float
    stop_touched: bool
    target_touched: bool
    duration_minutes: int
    updated_at: datetime


def evaluate_signal_tracking(
    *,
    signal: dict,
    observed_prices: list[float],
    as_of: datetime,
    expires_after_minutes: int = 24 * 60,
) -> TrackingEvaluation:
    if not observed_prices:
        raise ValueError("observed_prices must not be empty")

    entry_ref = (float(signal["entry_zone_low"]) + float(signal["entry_zone_high"])) / 2
    stop_loss = float(signal["stop_loss"])
    risk_per_unit = entry_ref - stop_loss
    if risk_per_unit <= 0:
        raise ValueError("signal stop_loss must be below entry_ref")

    tp1 = entry_ref + risk_per_unit
    tp2 = entry_ref + risk_per_unit * 2
    tp3 = entry_ref + risk_per_unit * 3

    high = max(observed_prices)
    low = min(observed_prices)
    mfe_pct = (high - entry_ref) / entry_ref * 100
    mae_pct = (low - entry_ref) / entry_ref * 100
    stop_touched = low <= stop_loss
    target_touched = high >= tp1
    duration_minutes = _duration_minutes(signal["created_at"], as_of)

    if stop_touched:
        status = "stopped"
    elif target_touched:
        status = "tp1_hit"
    elif duration_minutes >= expires_after_minutes:
        status = "expired"
    else:
        status = "monitoring"

    return TrackingEvaluation(
        signal_id=signal["signal_id"],
        status=status,
        entry_ref=round(entry_ref, 8),
        risk_per_unit=round(risk_per_unit, 8),
        tp1=round(tp1, 8),
        tp2=round(tp2, 8),
        tp3=round(tp3, 8),
        max_favorable_excursion_pct=round(mfe_pct, 6),
        max_adverse_excursion_pct=round(mae_pct, 6),
        stop_touched=stop_touched,
        target_touched=target_touched,
        duration_minutes=duration_minutes,
        updated_at=as_of,
    )


def _duration_minutes(created_at: str, as_of: datetime) -> int:
    created = datetime.fromisoformat(created_at)
    return max(0, int((as_of - created).total_seconds() // 60))
