from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from long_signal_v1 import RecentSignalRef, generate_long_signal_v1  # noqa: E402
from models import IndicatorSnapshot  # noqa: E402
from structure_analyzer import StructureAnalysis  # noqa: E402


ANCHOR = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


def snapshot(
    timeframe: str,
    *,
    close: float = 100.0,
    ema20: float = 99.5,
    ema60: float = 98.0,
    support_level: float | None = 98.2,
    recent_swing_low: float | None = 97.4,
    bollinger_upper: float = 105.0,
    bollinger_middle: float = 99.4,
    bollinger_lower: float = 96.0,
    macd: float = 1.2,
    macd_signal: float = 0.8,
    macd_histogram: float = 0.4,
) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        exchange="okx",
        symbol="BTCUSDT",
        timeframe=timeframe,
        calculated_at=ANCHOR,
        close=close,
        ema20=ema20,
        ema60=ema60,
        macd=macd,
        macd_signal=macd_signal,
        macd_histogram=macd_histogram,
        bollinger_upper=bollinger_upper,
        bollinger_middle=bollinger_middle,
        bollinger_lower=bollinger_lower,
        volume_ma=100.0,
        recent_swing_low=recent_swing_low,
        support_level=support_level,
    )


def structure(**overrides) -> StructureAnalysis:
    values = {
        "symbol": "BTCUSDT",
        "primary_exchange": "okx",
        "is_valid": True,
        "reasons": ["structure_analyzed"],
        "timeframe_alignment": {"15m": "anchor_closed_bar", "1h": "lagged_closed_bar", "4h": "lagged_closed_bar"},
        "indicators": {
            "15m": snapshot("15m"),
            "1h": snapshot("1h", ema20=99.3, ema60=97.8, support_level=97.8, recent_swing_low=97.2),
            "4h": snapshot("4h", ema20=99.0, ema60=98.0, support_level=96.0, recent_swing_low=95.5),
        },
        "support_levels": {"15m": 98.2, "1h": 97.8, "4h": 96.0},
        "chase_risk": False,
        "support_too_close": False,
        "trend_broken": False,
        "high_volatility": False,
    }
    values.update(overrides)
    return StructureAnalysis(**values)


def test_generates_long_signal_with_structural_entry_zone_rr_and_level_a() -> None:
    decision = generate_long_signal_v1(
        structure(),
        analysis_anchor_time=ANCHOR,
        previous_4h_ema20=99.2,
        target_resistance=112.0,
    )

    assert decision.signal is not None
    assert decision.signal.entry_zone_low > 98.2
    assert decision.signal.entry_zone_high < 100.0
    assert decision.signal.stop_reason == "4h support minus 0.3% buffer"
    assert decision.rr is not None and decision.rr >= 3.0
    assert decision.signal_level == "A"
    assert decision.should_push is True
    assert "signal_level:A" in decision.signal.reasons
    assert "should_push:true" in decision.signal.reasons
    assert any(reason.startswith("target_ref:112") for reason in decision.signal.reasons)
    assert "trend_broken" in decision.signal.invalidation
    assert "high_volatility" in decision.signal.invalidation


def test_trend_broken_gate_blocks_signal() -> None:
    decision = generate_long_signal_v1(
        structure(trend_broken=True),
        analysis_anchor_time=ANCHOR,
        previous_4h_ema20=99.2,
        target_resistance=112.0,
    )

    assert decision.signal is None
    assert decision.reasons == ["trend_broken_gate"]


def test_high_volatility_gate_blocks_signal() -> None:
    decision = generate_long_signal_v1(
        structure(high_volatility=True),
        analysis_anchor_time=ANCHOR,
        previous_4h_ema20=99.2,
        target_resistance=112.0,
    )

    assert decision.signal is None
    assert decision.reasons == ["high_volatility_gate"]


def test_four_hour_bearish_gate_blocks_signal() -> None:
    bearish = structure(
        indicators={
            "15m": snapshot("15m"),
            "1h": snapshot("1h", ema20=99.3, ema60=97.8, support_level=97.8, recent_swing_low=97.2),
            "4h": snapshot("4h", close=95.0, ema20=96.0, ema60=98.0, support_level=94.0),
        },
    )

    decision = generate_long_signal_v1(
        bearish,
        analysis_anchor_time=ANCHOR,
        previous_4h_ema20=96.5,
        target_resistance=112.0,
    )

    assert decision.signal is None
    assert decision.reasons == ["4h_bearish_gate"]


def test_rr_below_two_blocks_signal_using_entry_zone_midpoint() -> None:
    decision = generate_long_signal_v1(
        structure(),
        analysis_anchor_time=ANCHOR,
        previous_4h_ema20=99.2,
        target_resistance=102.0,
    )

    assert decision.signal is None
    assert decision.reasons == ["rr_below_2"]
    assert decision.rr is not None and decision.rr < 2.0


def test_cooldown_uses_symbol_exchange_and_signal_profile() -> None:
    recent = [
        RecentSignalRef(
            symbol="BTCUSDT",
            exchange="okx",
            signal_profile="default",
            created_at=ANCHOR - timedelta(hours=2),
        ),
        RecentSignalRef(
            symbol="BTCUSDT",
            exchange="bybit",
            signal_profile="default",
            created_at=ANCHOR - timedelta(hours=1),
        ),
    ]

    blocked = generate_long_signal_v1(
        structure(),
        analysis_anchor_time=ANCHOR,
        recent_signals=recent,
        signal_profile="default",
        previous_4h_ema20=99.2,
        target_resistance=112.0,
    )
    allowed = generate_long_signal_v1(
        structure(),
        analysis_anchor_time=ANCHOR,
        recent_signals=recent,
        signal_profile="aggressive",
        previous_4h_ema20=99.2,
        target_resistance=112.0,
    )

    assert blocked.signal is None
    assert blocked.reasons[0].startswith("cooldown_active:")
    assert allowed.signal is not None


def test_signal_level_c_does_not_push() -> None:
    weak = structure(
        indicators={
            "15m": snapshot("15m", close=99.3, ema20=99.5, bollinger_middle=99.6, support_level=98.2),
            "1h": snapshot("1h", close=99.4, ema20=99.3, ema60=97.8, support_level=97.8, recent_swing_low=97.2),
            "4h": snapshot("4h", close=99.0, ema20=99.5, ema60=98.0, support_level=96.0),
        },
    )

    decision = generate_long_signal_v1(
        weak,
        analysis_anchor_time=ANCHOR,
        previous_4h_ema20=99.8,
        target_resistance=107.5,
    )

    assert decision.signal is not None
    assert decision.signal_level == "C"
    assert decision.should_push is False
    assert "signal_level:C" in decision.signal.reasons
    assert "should_push:false" in decision.signal.reasons
