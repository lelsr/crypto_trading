from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.dashboard import load_dashboard_data  # noqa: E402


class FakeRepository:
    def get_recent_signals(self, *, limit: int = 50):
        return [
            {"signal_id": "sig-1", "symbol": "BTCUSDT", "status": "monitoring"},
            {"signal_id": "sig-2", "symbol": "ETHUSDT", "status": "stopped"},
        ][:limit]

    def get_recent_signal_feedback_rows(self, *, limit: int = 50):
        return [
            {
                "signal_id": "sig-1",
                "target_touched": True,
                "stop_touched": False,
                "max_favorable_excursion": 5.0,
                "max_adverse_excursion": -1.0,
                "manual_verdict": "good",
            },
            {
                "signal_id": "sig-2",
                "target_touched": False,
                "stop_touched": True,
                "max_favorable_excursion": 1.0,
                "max_adverse_excursion": -3.0,
                "manual_verdict": "bad",
            },
        ][:limit]

    def get_exchange_health(self):
        return [
            {"exchange": "okx", "endpoint": "tickers", "source_status": "ok", "latency_ms": 120},
            {"exchange": "bybit", "endpoint": "tickers", "source_status": "failed", "latency_ms": None},
        ]


def test_dashboard_data_loads_all_sections_without_streamlit_ui() -> None:
    data = load_dashboard_data(FakeRepository(), limit=10)

    assert set(data) == {
        "overview",
        "current_signals",
        "signal_lifecycle",
        "manual_reviews",
        "exchange_health",
        "strategy_feedback",
    }
    assert data["overview"]["signal_count"] == 2
    assert data["overview"]["active_signal_count"] == 1
    assert data["overview"]["exchange_count"] == 2
    assert data["current_signals"][0]["symbol"] == "BTCUSDT"
    assert len(data["manual_reviews"]) == 2
    assert data["strategy_feedback"].tp1_hit_rate == 0.5
    assert data["strategy_feedback"].stop_hit_rate == 0.5
