"""Select the best Phase 14 strategy from structure and quality context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from lifecycle.signal_quality_analyzer import SignalQualitySummary
from structure_analyzer import StructureAnalysis


TREND = "long_signal_trend_v2"
BREAKOUT = "long_signal_breakout_v1"
MEAN_REVERSION = "long_signal_mean_reversion_v1"


@dataclass(frozen=True)
class StrategySelection:
    symbol: str
    best_strategy_name: str
    reason: str


def select_strategy(
    *,
    symbol: str,
    analysis: StructureAnalysis,
    quality_summary: SignalQualitySummary | Mapping[str, SignalQualitySummary],
) -> StrategySelection:
    summaries = _as_summary_map(quality_summary)
    if _is_range_bound(analysis):
        return StrategySelection(symbol=symbol, best_strategy_name=MEAN_REVERSION, reason="range_bound_4h_prefers_mean_reversion")

    breakout_summary = summaries.get(BREAKOUT)
    if analysis.high_volatility and breakout_summary is not None and breakout_summary.tp1_hit_rate >= 0.55:
        return StrategySelection(symbol=symbol, best_strategy_name=BREAKOUT, reason="high_volatility_with_breakout_tp_rate_edge")

    best_by_expectancy = _best_expectancy(summaries)
    if best_by_expectancy is not None:
        return StrategySelection(
            symbol=symbol,
            best_strategy_name=best_by_expectancy,
            reason="highest_expectancy_r_from_quality_summary",
        )

    if _is_trending(analysis):
        return StrategySelection(symbol=symbol, best_strategy_name=TREND, reason="trend_environment_default")
    if analysis.high_volatility:
        return StrategySelection(symbol=symbol, best_strategy_name=BREAKOUT, reason="high_volatility_default")
    return StrategySelection(symbol=symbol, best_strategy_name=MEAN_REVERSION, reason="fallback_range_default")


def _as_summary_map(
    quality_summary: SignalQualitySummary | Mapping[str, SignalQualitySummary],
) -> dict[str, SignalQualitySummary]:
    if isinstance(quality_summary, SignalQualitySummary):
        return {TREND: quality_summary}
    return dict(quality_summary)


def _best_expectancy(summaries: Mapping[str, SignalQualitySummary]) -> str | None:
    if not summaries:
        return None
    best_name, best_summary = max(summaries.items(), key=lambda item: item[1].expectancy_r)
    if best_summary.total_signals <= 0:
        return None
    return best_name


def _is_trending(analysis: StructureAnalysis) -> bool:
    four_hour = analysis.indicators.get("4h")
    if four_hour is None or four_hour.ema20 is None or four_hour.ema60 is None:
        return False
    return four_hour.ema20 > four_hour.ema60 and four_hour.close >= four_hour.ema20


def _is_range_bound(analysis: StructureAnalysis) -> bool:
    four_hour = analysis.indicators.get("4h")
    if four_hour is None or four_hour.ema20 is None or four_hour.ema60 is None:
        return True
    distance = abs(four_hour.ema20 - four_hour.ema60) / four_hour.close if four_hour.close else 0.0
    return distance <= 0.005
