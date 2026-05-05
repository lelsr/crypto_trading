from __future__ import annotations

from datetime import UTC, datetime

import pytest

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from events import (  # noqa: E402
    CandidatePoolBuilt,
    CandidatesFiltered,
    IndicatorsComputed,
    KlinesFetched,
    ManualReviewSubmitted,
    MarketCapEnriched,
    PrimaryExchangeSelected,
    ScanCompleted,
    ScanEvent,
    ScanFailed,
    ScanStarted,
    SignalGenerated,
    SignalNotified,
    SignalTracked,
    TickerFetched,
)


def aware_now() -> datetime:
    return datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


def test_scan_event_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timestamp must be timezone-aware"):
        ScanEvent(
            scan_id="scan-1",
            event_type="ScanStarted",
            timestamp=datetime(2026, 5, 5, 12, 0),
            status="started",
            message="started",
        )


def test_scan_event_requires_valid_payload_json() -> None:
    with pytest.raises(ValueError, match="payload_json must be valid JSON"):
        ScanEvent(
            scan_id="scan-1",
            event_type="ScanStarted",
            timestamp=aware_now(),
            status="started",
            message="started",
            payload_json="{bad-json",
        )


def test_scan_event_from_payload_serializes_json() -> None:
    event = ScanEvent.from_payload(
        scan_id="scan-1",
        event_type="TickerFetched",
        timestamp=aware_now(),
        status="ok",
        message="ticker fetched",
        payload={"exchange": "bybit", "count": 300},
    )

    assert event.payload() == {"count": 300, "exchange": "bybit"}
    assert event.payload_json == '{"count": 300, "exchange": "bybit"}'


def test_all_required_event_types_are_available() -> None:
    event_classes = [
        ScanStarted,
        TickerFetched,
        CandidatePoolBuilt,
        MarketCapEnriched,
        CandidatesFiltered,
        PrimaryExchangeSelected,
        KlinesFetched,
        IndicatorsComputed,
        SignalGenerated,
        SignalNotified,
        SignalTracked,
        ManualReviewSubmitted,
        ScanCompleted,
        ScanFailed,
    ]

    event_types = {
        event_class(
            scan_id="scan-1",
            timestamp=aware_now(),
            status="ok",
            message="ok",
        ).event_type
        for event_class in event_classes
    }

    assert event_types == {
        "ScanStarted",
        "TickerFetched",
        "CandidatePoolBuilt",
        "MarketCapEnriched",
        "CandidatesFiltered",
        "PrimaryExchangeSelected",
        "KlinesFetched",
        "IndicatorsComputed",
        "SignalGenerated",
        "SignalNotified",
        "SignalTracked",
        "ManualReviewSubmitted",
        "ScanCompleted",
        "ScanFailed",
    }


def test_typed_event_contains_required_common_fields() -> None:
    event = KlinesFetched(
        scan_id="scan-2",
        timestamp=aware_now(),
        status="partial",
        message="primary exchange kline fetch partially succeeded",
        payload_json='{"symbol": "BTCUSDT", "primary_exchange": "bybit"}',
    )

    assert event.scan_id == "scan-2"
    assert event.event_type == "KlinesFetched"
    assert event.timestamp.tzinfo is not None
    assert event.status == "partial"
    assert event.message
    assert event.payload_json
    assert event.payload()["primary_exchange"] == "bybit"
