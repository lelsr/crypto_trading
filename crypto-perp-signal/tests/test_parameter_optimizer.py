from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from lifecycle.parameter_optimizer import generate_parameter_suggestions
from lifecycle.signal_quality_analyzer import analyze_signal_quality


def stopped_a_row(index: int) -> dict:
    return {
        "signal_id": f"sig-{index}",
        "symbol": "BTCUSDT",
        "primary_exchange": "bybit",
        "score": 90,
        "entry_zone_low": 99.0,
        "entry_zone_high": 101.0,
        "stop_loss": 95.0,
        "stop_reason": "4h support minus 0.3% buffer",
        "reasons": ["signal_level:A", "rr:3.5"],
        "tracking_status": "stopped",
        "max_favorable_excursion": 0.5,
        "max_adverse_excursion": -5.0,
        "stop_touched": True,
        "target_touched": False,
        "duration_minutes": 60,
        "manual_verdict": "bad",
        "manual_tags": ["too_extended"],
    }


def test_high_failure_rate_generates_parameter_suggestions_without_auto_apply() -> None:
    analysis = analyze_signal_quality([stopped_a_row(index) for index in range(10)], min_sample_size=10)

    suggestions = generate_parameter_suggestions(
        summary=analysis.summary,
        groups=analysis.groups,
        failure_patterns=analysis.failure_patterns,
        current_parameters={"long_signal_v1.min_rr": 2.0, "signals.min_score_to_generate": 70},
        min_sample_size=10,
    )

    suggestion_types = {suggestion.suggestion_type for suggestion in suggestions}
    assert "raise_min_score" in suggestion_types
    assert "raise_min_rr" in suggestion_types
    assert "review_manually" in suggestion_types
    assert all(suggestion.apply_automatically is False for suggestion in suggestions)


def test_manual_tags_can_suggest_chase_risk_threshold_review() -> None:
    rows = [stopped_a_row(index) for index in range(3)]
    analysis = analyze_signal_quality(rows, min_sample_size=10)

    suggestions = generate_parameter_suggestions(
        summary=analysis.summary,
        groups=analysis.groups,
        failure_patterns=analysis.failure_patterns,
        current_parameters={"long_signal_v1.max_close_above_ema20_pct": 0.02},
        min_sample_size=10,
    )

    chase_suggestions = [
        suggestion for suggestion in suggestions if suggestion.suggestion_type == "adjust_chase_risk_threshold"
    ]
    assert chase_suggestions
    assert chase_suggestions[0].confidence == "low"
    assert chase_suggestions[0].suggested_value == 0.015
