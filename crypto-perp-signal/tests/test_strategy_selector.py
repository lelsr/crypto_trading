from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "domain"))
sys.path.insert(0, str(PROJECT_ROOT / "domain" / "strategies"))

from lifecycle.signal_quality_analyzer import SignalQualitySummary  # noqa: E402
from lifecycle.strategy_selector import BREAKOUT, MEAN_REVERSION, TREND, select_strategy  # noqa: E402
from long_signal_breakout_v1 import generate_long_signal_breakout_v1  # noqa: E402
from long_signal_mean_reversion_v1 import generate_long_signal_mean_reversion_v1  # noqa: E402
from long_signal_trend_v2 import generate_long_signal_trend_v2  # noqa: E402
from models import IndicatorSnapshot  # noqa: E402
from structure_analyzer import StructureAnalysis  # noqa: E402


ANCHOR = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


def summary(*, total: int = 20, tp1: float = 0.4, expectancy: float = 0.0) -> SignalQualitySummary:
    return SignalQualitySummary(
        total_signals=total,
        level_counts={"A": 3, "B": 10, "C": 7},
        tp1_hit_rate=tp1,
        tp2_hit_rate=0.2,
        tp3_hit_rate=0.1,
        stop_hit_rate=0.25,
        expired_rate=0.1,
        avg_mfe_pct=4.0,
        avg_mae_pct=-1.5,
        median_mfe_pct=3.0,
        median_mae_pct=-1.0,
        avg_duration_minutes=120,
        manual_good_rate=0.5,
        manual_bad_rate=0.2,
        expectancy_r=expectancy,
    )


def snap(
    timeframe: str,
    *,
    close: float = 100.0,
    ema20: float = 99.5,
    ema60: float = 98.0,
    support_level: float | None = 96.0,
    recent_swing_low: float | None = 95.0,
    bollinger_upper: float = 112.0,
    bollinger_middle: float = 100.0,
    bollinger_lower: float = 94.0,
    volume_ma: float = 100.0,
) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        exchange="okx",
        symbol="BTCUSDT",
        timeframe=timeframe,
        calculated_at=ANCHOR,
        close=close,
        ema20=ema20,
        ema60=ema60,
        macd=1.0,
        macd_signal=0.5,
        macd_histogram=0.5,
        bollinger_upper=bollinger_upper,
        bollinger_middle=bollinger_middle,
        bollinger_lower=bollinger_lower,
        volume_ma=volume_ma,
        recent_swing_low=recent_swing_low,
        support_level=support_level,
    )


def structure(
    *,
    fifteen: IndicatorSnapshot | None = None,
    one_hour: IndicatorSnapshot | None = None,
    four_hour: IndicatorSnapshot | None = None,
    high_volatility: bool = False,
    trend_broken: bool = False,
    chase_risk: bool = False,
) -> StructureAnalysis:
    indicators = {
        "15m": fifteen or snap("15m"),
        "1h": one_hour or snap("1h"),
        "4h": four_hour or snap("4h"),
    }
    return StructureAnalysis(
        symbol="BTCUSDT",
        primary_exchange="okx",
        is_valid=True,
        reasons=["structure_analyzed"],
        timeframe_alignment={"15m": "anchor_closed_bar", "1h": "lagged_closed_bar", "4h": "lagged_closed_bar"},
        indicators=indicators,
        support_levels={key: value.support_level for key, value in indicators.items()},
        chase_risk=chase_risk,
        support_too_close=False,
        trend_broken=trend_broken,
        high_volatility=high_volatility,
    )


def test_trend_strategy_is_selected_when_expectancy_is_highest() -> None:
    selected = select_strategy(
        symbol="BTCUSDT",
        analysis=structure(),
        quality_summary={
            TREND: summary(expectancy=1.2),
            BREAKOUT: summary(expectancy=0.6, tp1=0.7),
            MEAN_REVERSION: summary(expectancy=0.4),
        },
    )

    assert selected.best_strategy_name == TREND


def test_breakout_strategy_is_selected_in_high_volatility_with_tp_edge() -> None:
    selected = select_strategy(
        symbol="BTCUSDT",
        analysis=structure(high_volatility=True),
        quality_summary={
            TREND: summary(expectancy=1.2),
            BREAKOUT: summary(expectancy=0.8, tp1=0.72),
            MEAN_REVERSION: summary(expectancy=0.4),
        },
    )

    assert selected.best_strategy_name == BREAKOUT


def test_mean_reversion_strategy_is_selected_in_range_bound_environment() -> None:
    selected = select_strategy(
        symbol="BTCUSDT",
        analysis=structure(four_hour=snap("4h", close=100.0, ema20=100.0, ema60=99.8)),
        quality_summary={
            TREND: summary(expectancy=1.2),
            BREAKOUT: summary(expectancy=0.9, tp1=0.8),
            MEAN_REVERSION: summary(expectancy=0.3),
        },
    )

    assert selected.best_strategy_name == MEAN_REVERSION


def test_each_phase_14_strategy_can_generate_legal_signal_or_return_none() -> None:
    trend_signal = generate_long_signal_trend_v2(
        structure(fifteen=snap("15m", close=99.6, ema20=99.5)),
        analysis_anchor_time=ANCHOR,
        previous_4h_ema20=98.8,
        target_resistance=120.0,
    )
    breakout_signal = generate_long_signal_breakout_v1(
        structure(fifteen=snap("15m", close=111.0, ema20=105.0, support_level=104.0, bollinger_upper=125.0)),
        analysis_anchor_time=ANCHOR,
        recent_15m_highs=[100 + index * 0.5 for index in range(20)],
        latest_15m_volume=180.0,
        target_resistance=125.0,
    )
    mean_reversion_signal = generate_long_signal_mean_reversion_v1(
        structure(
            fifteen=snap("15m", close=93.0, ema20=99.0, ema60=100.0, bollinger_lower=94.0, bollinger_middle=102.0, support_level=92.0, recent_swing_low=91.5),
            four_hour=snap("4h", close=100.0, ema20=100.0, ema60=99.8),
        ),
        analysis_anchor_time=ANCHOR,
        rsi_15m=25.0,
    )

    for signal in (trend_signal, breakout_signal, mean_reversion_signal):
        assert signal is not None
        assert signal.entry_zone_low <= signal.entry_zone_high
        assert signal.stop_loss < signal.entry_zone_low
        assert signal.invalidation
        assert any(reason.startswith("signal_level:") for reason in signal.reasons)
        assert any(reason.startswith("rr:") and float(reason.split(":", 1)[1]) >= 2.0 for reason in signal.reasons)


def test_strategy_returns_none_when_core_conditions_fail() -> None:
    blocked = generate_long_signal_trend_v2(
        structure(trend_broken=True),
        analysis_anchor_time=ANCHOR,
        previous_4h_ema20=98.8,
        target_resistance=120.0,
    )

    assert blocked is None
