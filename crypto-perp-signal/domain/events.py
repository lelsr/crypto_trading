"""Domain event models for scan orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal
from uuid import uuid4

from models import require_timezone_aware


EventStatus = Literal["started", "ok", "partial", "failed", "skipped"]


@dataclass(frozen=True)
class ScanEvent:
    scan_id: str
    event_type: str
    timestamp: datetime
    status: EventStatus | str
    message: str
    payload_json: str = "{}"
    event_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        require_timezone_aware(self.timestamp, "timestamp")
        try:
            json.loads(self.payload_json)
        except json.JSONDecodeError as exc:
            raise ValueError("payload_json must be valid JSON") from exc

    @classmethod
    def from_payload(
        cls,
        *,
        scan_id: str,
        event_type: str,
        timestamp: datetime,
        status: EventStatus | str,
        message: str,
        payload: dict[str, Any] | list[Any] | None = None,
    ) -> "ScanEvent":
        return cls(
            scan_id=scan_id,
            event_type=event_type,
            timestamp=timestamp,
            status=status,
            message=message,
            payload_json=json.dumps(payload or {}, ensure_ascii=True, sort_keys=True),
        )

    def payload(self) -> Any:
        return json.loads(self.payload_json)


class _TypedScanEvent(ScanEvent):
    EVENT_TYPE: ClassVar[str]

    def __init__(
        self,
        *,
        scan_id: str,
        timestamp: datetime,
        status: EventStatus | str,
        message: str,
        payload_json: str = "{}",
    ) -> None:
        super().__init__(
            scan_id=scan_id,
            event_type=self.EVENT_TYPE,
            timestamp=timestamp,
            status=status,
            message=message,
            payload_json=payload_json,
        )


class ScanStarted(_TypedScanEvent):
    EVENT_TYPE = "ScanStarted"


class TickerFetched(_TypedScanEvent):
    EVENT_TYPE = "TickerFetched"


class CandidatePoolBuilt(_TypedScanEvent):
    EVENT_TYPE = "CandidatePoolBuilt"


class MarketCapEnriched(_TypedScanEvent):
    EVENT_TYPE = "MarketCapEnriched"


class CandidatesFiltered(_TypedScanEvent):
    EVENT_TYPE = "CandidatesFiltered"


class PrimaryExchangeSelected(_TypedScanEvent):
    EVENT_TYPE = "PrimaryExchangeSelected"


class KlinesFetched(_TypedScanEvent):
    EVENT_TYPE = "KlinesFetched"


class IndicatorsComputed(_TypedScanEvent):
    EVENT_TYPE = "IndicatorsComputed"


class SignalGenerated(_TypedScanEvent):
    EVENT_TYPE = "SignalGenerated"


class SignalNotified(_TypedScanEvent):
    EVENT_TYPE = "SignalNotified"


class SignalTracked(_TypedScanEvent):
    EVENT_TYPE = "SignalTracked"


class ManualReviewSubmitted(_TypedScanEvent):
    EVENT_TYPE = "ManualReviewSubmitted"


class ScanCompleted(_TypedScanEvent):
    EVENT_TYPE = "ScanCompleted"


class ScanFailed(_TypedScanEvent):
    EVENT_TYPE = "ScanFailed"
