from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from application.lifecycle_service import SignalLifecycleService  # noqa: E402
from domain.models import LongSignal  # noqa: E402
from infrastructure.sqlite_repo import SQLiteRepository  # noqa: E402


def aware_now() -> datetime:
    return datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


def make_signal(*, created_at: datetime | None = None) -> LongSignal:
    return LongSignal(
        symbol="BTCUSDT",
        primary_exchange="okx",
        score=86.0,
        entry_zone_low=100.0,
        entry_zone_high=102.0,
        stop_loss=96.0,
        stop_reason="4h support minus 0.3% buffer",
        timeframe_alignment={"15m": "anchor_closed_bar", "1h": "lagged_closed_bar", "4h": "lagged_closed_bar"},
        reasons=["signal_level:A"],
        invalidation="15m close below stop_loss OR trend_broken",
        created_at=created_at or aware_now(),
    )


def test_signal_lifecycle_tracks_tp_targets_mfe_mae_and_status(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "signals.db")
    scan_id = repo.create_scan_run(scan_id="scan-1", started_at=aware_now())
    signal_id = repo.insert_signal(scan_id=scan_id, signal=make_signal(), signal_id="sig-1")
    service = SignalLifecycleService(repo)

    service.mark_notified(signal_id=signal_id, updated_at=aware_now() + timedelta(minutes=1))
    service.start_monitoring(signal_id=signal_id, updated_at=aware_now() + timedelta(minutes=2))
    evaluation = service.update_from_prices(
        signal_id=signal_id,
        observed_prices=[100.5, 107.0, 99.0],
        as_of=aware_now() + timedelta(minutes=60),
    )

    assert evaluation.entry_ref == 101.0
    assert evaluation.risk_per_unit == 5.0
    assert evaluation.tp1 == 106.0
    assert evaluation.tp2 == 111.0
    assert evaluation.tp3 == 116.0
    assert evaluation.status == "tp1_hit"
    assert evaluation.target_touched is True
    assert evaluation.stop_touched is False
    assert evaluation.max_favorable_excursion_pct == 5.940594
    assert evaluation.max_adverse_excursion_pct == -1.980198

    signal = repo.get_signal(signal_id=signal_id)
    tracking = repo.get_latest_signal_tracking(signal_id=signal_id)

    assert signal is not None
    assert signal["status"] == "tp1_hit"
    assert tracking is not None
    assert tracking["status"] == "tp1_hit"
    assert tracking["target_touched"] is True


def test_signal_lifecycle_marks_stopped_and_expired(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "signals.db")
    scan_id = repo.create_scan_run(scan_id="scan-2", started_at=aware_now())
    stopped_id = repo.insert_signal(scan_id=scan_id, signal=make_signal(), signal_id="sig-stop")
    expired_id = repo.insert_signal(scan_id=scan_id, signal=make_signal(), signal_id="sig-expire")
    service = SignalLifecycleService(repo)

    stopped = service.update_from_prices(
        signal_id=stopped_id,
        observed_prices=[101.0, 95.5],
        as_of=aware_now() + timedelta(minutes=10),
    )
    expired = service.update_from_prices(
        signal_id=expired_id,
        observed_prices=[101.0, 102.0],
        as_of=aware_now() + timedelta(minutes=121),
        expires_after_minutes=120,
    )

    assert stopped.status == "stopped"
    assert stopped.stop_touched is True
    assert expired.status == "expired"
