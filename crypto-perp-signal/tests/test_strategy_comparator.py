from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from lifecycle.strategy_comparator import compare_strategies  # noqa: E402


def row(
    strategy: str,
    *,
    status: str = "monitoring",
    target_touched: bool = False,
    stop_touched: bool = False,
    mfe: float = 0.0,
    mae: float = 0.0,
) -> dict:
    return {
        "reasons": [f"signal_profile:{strategy}", "signal_level:B", "rr:2.5"],
        "tracking_status": status,
        "target_touched": target_touched,
        "stop_touched": stop_touched,
        "max_favorable_excursion": mfe,
        "max_adverse_excursion": mae,
    }


def test_comparator_outputs_multi_strategy_metrics() -> None:
    comparisons = compare_strategies(
        [
            row("long_signal_trend_v2", status="tp1_hit", target_touched=True, mfe=4.0, mae=-1.0),
            row("long_signal_trend_v2", status="stopped", stop_touched=True, mfe=1.0, mae=-3.0),
            row("long_signal_breakout_v1", status="tp2_hit", mfe=8.0, mae=-2.0),
            row("long_signal_mean_reversion_v1", status="expired", mfe=2.0, mae=-1.0),
        ]
    )
    by_name = {item.strategy_name: item for item in comparisons}

    assert by_name["long_signal_trend_v2"].signal_count == 2
    assert by_name["long_signal_trend_v2"].tp1_hit_rate == 0.5
    assert by_name["long_signal_trend_v2"].stop_rate == 0.5
    assert by_name["long_signal_trend_v2"].expectancy_r == 0.0
    assert by_name["long_signal_trend_v2"].avg_mfe == 2.5
    assert by_name["long_signal_trend_v2"].avg_mae == -2.0
    assert by_name["long_signal_breakout_v1"].expectancy_r == 2.0
    assert comparisons[0].strategy_name == "long_signal_breakout_v1"


def test_comparator_accepts_explicit_strategy_name() -> None:
    comparisons = compare_strategies(
        [
            {
                "strategy_name": "long_signal_breakout_v1",
                "tracking_status": "tp3_hit",
                "max_favorable_excursion": 12.0,
                "max_adverse_excursion": -1.5,
            }
        ]
    )

    assert comparisons[0].strategy_name == "long_signal_breakout_v1"
    assert comparisons[0].tp1_hit_rate == 1.0
    assert comparisons[0].expectancy_r == 3.0
