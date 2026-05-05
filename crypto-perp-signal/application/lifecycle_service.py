"""Application service for signal lifecycle transitions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from lifecycle.signal_tracker import TrackingEvaluation, evaluate_signal_tracking


class SignalLifecycleService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def mark_notified(self, *, signal_id: str, updated_at: datetime) -> None:
        self.repository.update_signal_status(signal_id=signal_id, status="notified")
        self.repository.insert_signal_tracking(
            signal_id=signal_id,
            status="notified",
            updated_at=updated_at,
        )

    def start_monitoring(self, *, signal_id: str, updated_at: datetime) -> None:
        self.repository.update_signal_status(signal_id=signal_id, status="monitoring")
        self.repository.insert_signal_tracking(
            signal_id=signal_id,
            status="monitoring",
            updated_at=updated_at,
        )

    def update_from_prices(
        self,
        *,
        signal_id: str,
        observed_prices: list[float],
        as_of: datetime,
        expires_after_minutes: int = 24 * 60,
    ) -> TrackingEvaluation:
        signal = self.repository.get_signal(signal_id=signal_id)
        if signal is None:
            raise KeyError(f"signal not found: {signal_id}")

        evaluation = evaluate_signal_tracking(
            signal=signal,
            observed_prices=observed_prices,
            as_of=as_of,
            expires_after_minutes=expires_after_minutes,
        )
        self.repository.update_signal_status(signal_id=signal_id, status=evaluation.status)
        self.repository.insert_signal_tracking(
            signal_id=signal_id,
            status=evaluation.status,
            max_favorable_excursion=evaluation.max_favorable_excursion_pct,
            max_adverse_excursion=evaluation.max_adverse_excursion_pct,
            stop_touched=evaluation.stop_touched,
            target_touched=evaluation.target_touched,
            duration_minutes=evaluation.duration_minutes,
            updated_at=evaluation.updated_at,
        )
        return evaluation
