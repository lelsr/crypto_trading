"""Local Streamlit dashboard for persisted signal data."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.sqlite_repo import SQLiteRepository
from lifecycle.strategy_feedback import summarize_strategy_feedback


def load_dashboard_data(repository: Any, *, limit: int = 50) -> dict[str, Any]:
    signals = repository.get_recent_signals(limit=limit)
    lifecycle_rows = repository.get_recent_signal_feedback_rows(limit=limit)
    exchange_health = repository.get_exchange_health()
    strategy_feedback = summarize_strategy_feedback(lifecycle_rows)
    return {
        "overview": {
            "signal_count": len(signals),
            "active_signal_count": sum(1 for signal in signals if signal.get("status") in {"created", "notified", "monitoring"}),
            "exchange_count": len({row.get("exchange") for row in exchange_health}),
            "tp1_hit_rate": strategy_feedback.tp1_hit_rate,
            "stop_hit_rate": strategy_feedback.stop_hit_rate,
        },
        "current_signals": signals,
        "signal_lifecycle": lifecycle_rows,
        "manual_reviews": [row for row in lifecycle_rows if row.get("manual_verdict")],
        "exchange_health": exchange_health,
        "strategy_feedback": strategy_feedback,
    }


def run_dashboard(db_path: str | Path = "data/signals.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="Crypto Perp Signal", layout="wide")
    st.title("Crypto Perp Signal")

    repository = SQLiteRepository(db_path)
    data = load_dashboard_data(repository)

    tabs = st.tabs(
        [
            "Overview",
            "Current Signals",
            "Signal Lifecycle",
            "Manual Review",
            "Exchange Health",
            "Strategy Feedback",
        ]
    )

    with tabs[0]:
        st.subheader("Overview")
        st.json(data["overview"])

    with tabs[1]:
        st.subheader("Current Signals")
        st.dataframe(data["current_signals"], use_container_width=True)

    with tabs[2]:
        st.subheader("Signal Lifecycle")
        st.dataframe(data["signal_lifecycle"], use_container_width=True)

    with tabs[3]:
        st.subheader("Manual Review")
        st.dataframe(data["manual_reviews"], use_container_width=True)

    with tabs[4]:
        st.subheader("Exchange Health")
        st.dataframe(data["exchange_health"], use_container_width=True)

    with tabs[5]:
        st.subheader("Strategy Feedback")
        st.json(data["strategy_feedback"].__dict__)


if __name__ == "__main__":
    run_dashboard()
