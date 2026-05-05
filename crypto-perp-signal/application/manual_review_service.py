"""Application service for manual signal reviews."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from domain.models import ManualReview


class ManualReviewService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def submit_review(
        self,
        *,
        signal_id: str,
        manual_verdict: str,
        manual_notes: str,
        manual_tags: list[str],
        reviewed_at: datetime,
        review_id: str | None = None,
    ) -> ManualReview:
        if self.repository.get_signal(signal_id=signal_id) is None:
            raise KeyError(f"signal not found: {signal_id}")

        review = ManualReview(
            review_id=review_id or str(uuid4()),
            signal_id=signal_id,
            manual_verdict=manual_verdict,
            manual_notes=manual_notes,
            manual_tags=manual_tags,
            reviewed_at=reviewed_at,
        )
        self.repository.insert_manual_review(review)
        self.repository.update_signal_status(signal_id=signal_id, status="manual_reviewed")
        self.repository.insert_signal_tracking(
            signal_id=signal_id,
            status="manual_reviewed",
            updated_at=reviewed_at,
        )
        return review
