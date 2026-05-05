from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from application.manual_review_service import ManualReviewService  # noqa: E402
from domain.models import LongSignal  # noqa: E402
from infrastructure.sqlite_repo import SQLiteRepository  # noqa: E402


def aware_now() -> datetime:
    return datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


def make_signal() -> LongSignal:
    return LongSignal(
        symbol="ETHUSDT",
        primary_exchange="bybit",
        score=78.0,
        entry_zone_low=3_000.0,
        entry_zone_high=3_030.0,
        stop_loss=2_920.0,
        stop_reason="1h swing low minus 0.3% buffer",
        timeframe_alignment={"15m": "ok", "1h": "ok", "4h": "ok"},
        reasons=["signal_level:B"],
        invalidation="15m close below stop_loss",
        created_at=aware_now(),
    )


def test_manual_review_service_saves_review_and_marks_signal_reviewed(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "signals.db")
    scan_id = repo.create_scan_run(scan_id="scan-1", started_at=aware_now())
    signal_id = repo.insert_signal(scan_id=scan_id, signal=make_signal(), signal_id="sig-1")
    service = ManualReviewService(repo)

    review = service.submit_review(
        signal_id=signal_id,
        manual_verdict="good",
        manual_notes="clean follow-through after TP1",
        manual_tags=["tp1", "clean_reclaim"],
        reviewed_at=aware_now(),
        review_id="review-1",
    )

    signal = repo.get_signal(signal_id=signal_id)
    tracking = repo.get_latest_signal_tracking(signal_id=signal_id)
    feedback_rows = repo.get_recent_signal_feedback_rows(limit=5)

    assert review.review_id == "review-1"
    assert signal is not None
    assert signal["status"] == "manual_reviewed"
    assert tracking is not None
    assert tracking["status"] == "manual_reviewed"
    assert feedback_rows[0]["manual_verdict"] == "good"
    assert feedback_rows[0]["manual_tags"] == ["tp1", "clean_reclaim"]
