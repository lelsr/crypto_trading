from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from lifecycle.signal_quality_analyzer import analyze_signal_quality, summarize_signal_quality


def quality_row(
    *,
    signal_id: str = "sig",
    symbol: str = "BTCUSDT",
    exchange: str = "bybit",
    score: float = 82.0,
    level: str = "B",
    status: str = "monitoring",
    mfe: float = 0.0,
    mae: float = 0.0,
    stop_touched: bool = False,
    target_touched: bool = False,
    manual_verdict: str | None = None,
    manual_tags: list[str] | None = None,
    stop_reason: str = "1h swing low minus 0.3% buffer",
) -> dict:
    return {
        "signal_id": signal_id,
        "symbol": symbol,
        "primary_exchange": exchange,
        "score": score,
        "entry_zone_low": 99.0,
        "entry_zone_high": 101.0,
        "stop_loss": 95.0,
        "stop_reason": stop_reason,
        "reasons": [f"signal_level:{level}", "signal_profile:long_v1", "rr:3.2"],
        "tracking_status": status,
        "max_favorable_excursion": mfe,
        "max_adverse_excursion": mae,
        "stop_touched": stop_touched,
        "target_touched": target_touched,
        "duration_minutes": 120,
        "manual_verdict": manual_verdict,
        "manual_tags": manual_tags or [],
    }


def test_signal_quality_handles_empty_input() -> None:
    summary = summarize_signal_quality([])

    assert summary.total_signals == 0
    assert summary.tp1_hit_rate == 0.0
    assert summary.expectancy_r == 0.0


def test_signal_quality_calculates_rates_mfe_mae_and_expectancy() -> None:
    rows = [
        quality_row(signal_id="sig-1", level="B", target_touched=True, mfe=6.0, mae=-1.0, manual_verdict="good"),
        quality_row(signal_id="sig-2", level="C", status="stopped", stop_touched=True, mfe=1.0, mae=-5.0, manual_verdict="bad"),
        quality_row(signal_id="sig-3", level="A", status="tp3_hit", mfe=16.0, mae=-2.0, manual_verdict="good"),
    ]

    summary = summarize_signal_quality(rows)

    assert summary.total_signals == 3
    assert summary.tp1_hit_rate == 0.666667
    assert summary.tp2_hit_rate == 0.333333
    assert summary.tp3_hit_rate == 0.333333
    assert summary.stop_hit_rate == 0.333333
    assert summary.avg_mfe_pct == 7.666667
    assert summary.avg_mae_pct == -2.666667
    assert summary.median_mfe_pct == 6.0
    assert summary.median_mae_pct == -2.0
    assert summary.manual_good_rate == 0.666667
    assert summary.manual_bad_rate == 0.333333
    assert summary.expectancy_r == 1.0


def test_signal_quality_group_stats_and_low_sample() -> None:
    rows = [
        quality_row(signal_id="sig-a", level="A", score=90, target_touched=True, mfe=8.0),
        quality_row(signal_id="sig-b", level="B", score=80, status="stopped", stop_touched=True, mfe=1.0, mae=-4.0),
        quality_row(signal_id="sig-c", level="C", score=72, status="expired", mfe=2.0, mae=-1.0),
    ]

    analysis = analyze_signal_quality(rows, min_sample_size=10)
    level_stats = {stat.group_value: stat for stat in analysis.groups["signal_level"]}
    bucket_stats = {stat.group_value: stat for stat in analysis.groups["score_bucket"]}

    assert level_stats["A"].count == 1
    assert level_stats["B"].stop_hit_rate == 1.0
    assert level_stats["A"].sample_status == "low_sample"
    assert bucket_stats["85+"].count == 1
    assert bucket_stats["75-85"].count == 1
    assert bucket_stats["70-75"].count == 1


def test_manual_tags_and_a_level_stopped_failure_patterns() -> None:
    rows = [
        quality_row(signal_id="sig-1", level="A", score=92, status="stopped", stop_touched=True, manual_tags=["false_breakout"]),
        quality_row(signal_id="sig-2", level="B", status="stopped", stop_touched=True, manual_tags=["false_breakout"]),
        quality_row(signal_id="sig-3", level="C", manual_tags=["false_breakout"]),
    ]

    analysis = analyze_signal_quality(rows, min_sample_size=10)
    pattern_names = {pattern.pattern_name: pattern for pattern in analysis.failure_patterns}

    assert pattern_names["a_level_stopped"].severity == "high"
    assert pattern_names["a_level_stopped"].affected_count == 1
    assert pattern_names["manual_tag_frequent:false_breakout"].affected_count == 3
