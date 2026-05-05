from __future__ import annotations

from lifecycle.strategy_feedback import summarize_strategy_feedback


def test_strategy_feedback_summarizes_recent_signal_outcomes() -> None:
    rows = [
        {
            "target_touched": True,
            "stop_touched": False,
            "max_favorable_excursion": 6.0,
            "max_adverse_excursion": -1.0,
            "manual_verdict": "good",
        },
        {
            "target_touched": False,
            "stop_touched": True,
            "max_favorable_excursion": 1.5,
            "max_adverse_excursion": -4.0,
            "manual_verdict": "bad",
        },
        {
            "target_touched": True,
            "stop_touched": False,
            "max_favorable_excursion": 4.5,
            "max_adverse_excursion": -2.0,
            "manual_verdict": "good",
        },
    ]

    summary = summarize_strategy_feedback(rows)

    assert summary.signal_count == 3
    assert summary.tp1_hit_rate == 0.666667
    assert summary.stop_hit_rate == 0.333333
    assert summary.avg_mfe_pct == 4.0
    assert summary.avg_mae_pct == -2.333333
    assert summary.manual_good_bad_ratio == 2.0


def test_strategy_feedback_handles_empty_input() -> None:
    summary = summarize_strategy_feedback([])

    assert summary.signal_count == 0
    assert summary.tp1_hit_rate == 0.0
    assert summary.stop_hit_rate == 0.0
    assert summary.avg_mfe_pct == 0.0
    assert summary.avg_mae_pct == 0.0
    assert summary.manual_good_bad_ratio is None
