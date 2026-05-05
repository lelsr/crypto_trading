"""Strategy feedback aggregation helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyFeedbackSummary:
    signal_count: int
    tp1_hit_rate: float
    stop_hit_rate: float
    avg_mfe_pct: float
    avg_mae_pct: float
    manual_good_bad_ratio: float | None


def summarize_strategy_feedback(rows: list[dict]) -> StrategyFeedbackSummary:
    signal_count = len(rows)
    if signal_count == 0:
        return StrategyFeedbackSummary(
            signal_count=0,
            tp1_hit_rate=0.0,
            stop_hit_rate=0.0,
            avg_mfe_pct=0.0,
            avg_mae_pct=0.0,
            manual_good_bad_ratio=None,
        )

    tp1_count = sum(1 for row in rows if row.get("target_touched"))
    stop_count = sum(1 for row in rows if row.get("stop_touched"))
    mfe_values = [float(row["max_favorable_excursion"]) for row in rows if row.get("max_favorable_excursion") is not None]
    mae_values = [float(row["max_adverse_excursion"]) for row in rows if row.get("max_adverse_excursion") is not None]
    good_count = sum(1 for row in rows if row.get("manual_verdict") == "good")
    bad_count = sum(1 for row in rows if row.get("manual_verdict") == "bad")

    return StrategyFeedbackSummary(
        signal_count=signal_count,
        tp1_hit_rate=round(tp1_count / signal_count, 6),
        stop_hit_rate=round(stop_count / signal_count, 6),
        avg_mfe_pct=round(sum(mfe_values) / len(mfe_values), 6) if mfe_values else 0.0,
        avg_mae_pct=round(sum(mae_values) / len(mae_values), 6) if mae_values else 0.0,
        manual_good_bad_ratio=round(good_count / bad_count, 6) if bad_count else (float(good_count) if good_count else None),
    )
