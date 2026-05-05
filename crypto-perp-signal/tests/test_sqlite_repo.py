from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from domain.events import ScanEvent  # noqa: E402
from domain.models import LongSignal, ManualReview  # noqa: E402
from infrastructure.sqlite_repo import SQLiteRepository, init_db, to_json  # noqa: E402


EXPECTED_TABLES = {
    "scan_runs",
    "events",
    "exchange_health",
    "ticker_snapshots",
    "activity_candidates",
    "market_caps",
    "primary_exchange_decisions",
    "kline_snapshots",
    "indicator_snapshots",
    "signals",
    "signal_tracking",
    "manual_reviews",
    "strategy_feedback",
}


def aware_now() -> datetime:
    return datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


def test_init_db_creates_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.db"

    init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()

    table_names = {row[0] for row in rows}
    assert EXPECTED_TABLES.issubset(table_names)


def test_scan_run_lifecycle_and_event_insert(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "signals.db")
    scan_id = repo.create_scan_run(
        scan_id="scan-1",
        started_at=aware_now(),
        config={"loop_minutes": 38, "timeframes": ["15m", "1h", "4h"]},
    )
    event = ScanEvent.from_payload(
        scan_id=scan_id,
        event_type="ScanStarted",
        timestamp=aware_now(),
        status="started",
        message="scan started",
        payload={"config_loaded": True},
    )

    repo.insert_event(event)
    repo.complete_scan_run(
        scan_id=scan_id,
        status="completed",
        completed_at=datetime(2026, 5, 5, 12, 1, tzinfo=UTC),
        summary={"signals": 0},
    )

    with sqlite3.connect(tmp_path / "signals.db") as conn:
        scan_row = conn.execute("SELECT status, duration_ms, summary_json FROM scan_runs").fetchone()
        event_row = conn.execute("SELECT event_type, payload_json FROM events").fetchone()

    assert scan_row == ("completed", 60_000, '{"signals": 0}')
    assert event_row[0] == "ScanStarted"
    assert json.loads(event_row[1]) == {"config_loaded": True}


def test_exchange_health_upsert_and_get(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "signals.db")

    repo.upsert_exchange_health(
        exchange="bybit",
        endpoint="tickers",
        source_status="failed",
        latency_ms=1_000,
        error_code="timeout",
        error_message="request timed out",
        metadata={"attempts": 3},
        updated_at=aware_now(),
    )
    repo.upsert_exchange_health(
        exchange="bybit",
        endpoint="tickers",
        source_status="ok",
        latency_ms=120,
        error_code=None,
        error_message=None,
        last_success_at=aware_now(),
        metadata={"attempts": 1},
        updated_at=aware_now(),
    )

    health = repo.get_exchange_health()

    assert len(health) == 1
    assert health[0]["exchange"] == "bybit"
    assert health[0]["source_status"] == "ok"
    assert health[0]["metadata"] == {"attempts": 1}


def test_insert_signal_and_recent_signals_round_trip_json(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "signals.db")
    scan_id = repo.create_scan_run(scan_id="scan-2", started_at=aware_now())
    signal = LongSignal(
        symbol="BTCUSDT",
        primary_exchange="bybit",
        score=82.5,
        entry_zone_low=100.0,
        entry_zone_high=102.0,
        stop_loss=96.0,
        stop_reason="1h swing low",
        timeframe_alignment={"15m": "reclaimed", "1h": "macd stronger", "4h": "support"},
        reasons=["pullback reclaimed EMA20", "volume not shrinking"],
        invalidation="close below support",
        created_at=aware_now(),
    )

    signal_id = repo.insert_signal(scan_id=scan_id, signal=signal, signal_id="sig-1")
    recent = repo.get_recent_signals(limit=5)

    assert signal_id == "sig-1"
    assert len(recent) == 1
    assert recent[0]["signal_id"] == "sig-1"
    assert recent[0]["timeframe_alignment"]["15m"] == "reclaimed"
    assert recent[0]["reasons"] == ["pullback reclaimed EMA20", "volume not shrinking"]


def test_insert_manual_review(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "signals.db")
    scan_id = repo.create_scan_run(scan_id="scan-3", started_at=aware_now())
    signal = LongSignal(
        symbol="ETHUSDT",
        primary_exchange="okx",
        score=75.0,
        entry_zone_low=3_000.0,
        entry_zone_high=3_030.0,
        stop_loss=2_920.0,
        stop_reason="4h support below",
        timeframe_alignment={"15m": "ok", "1h": "ok", "4h": "ok"},
        reasons=["support reclaim"],
        invalidation="close below 4h support",
        created_at=aware_now(),
    )
    repo.insert_signal(scan_id=scan_id, signal=signal, signal_id="sig-2")
    review = ManualReview(
        review_id="review-1",
        signal_id="sig-2",
        manual_verdict="good",
        manual_notes="clean continuation",
        manual_tags=["support", "continuation"],
        reviewed_at=aware_now(),
    )

    repo.insert_manual_review(review)

    with sqlite3.connect(tmp_path / "signals.db") as conn:
        row = conn.execute("SELECT manual_verdict, manual_tags_json FROM manual_reviews").fetchone()

    assert row[0] == "good"
    assert json.loads(row[1]) == ["support", "continuation"]


def test_to_json_rejects_unsafe_unserializable_payload() -> None:
    class NotSerializable:
        pass

    with pytest.raises(TypeError):
        to_json({"bad": NotSerializable()})
