from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from application.quality_report_service import QualityReportService


def test_quality_report_service_generates_markdown(tmp_path: Path) -> None:
    rows = [
        {
            "signal_id": "sig-1",
            "symbol": "BTCUSDT",
            "primary_exchange": "bybit",
            "score": 90,
            "entry_zone_low": 99.0,
            "entry_zone_high": 101.0,
            "stop_loss": 95.0,
            "stop_reason": "4h support minus 0.3% buffer",
            "reasons": ["signal_level:A", "rr:3.2"],
            "tracking_status": "stopped",
            "max_favorable_excursion": 0.5,
            "max_adverse_excursion": -5.0,
            "stop_touched": True,
            "target_touched": False,
            "duration_minutes": 80,
            "manual_verdict": "bad",
            "manual_tags": ["false_breakout"],
        }
    ]
    service = QualityReportService(report_dir=tmp_path)

    report = service.generate(
        rows=rows,
        timestamp=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),
    )

    assert report.path == tmp_path / "quality-report-20260505T120000Z.md"
    assert report.path.exists()
    assert "# Signal Quality Report" in report.content
    assert "## 7. Failure Patterns" in report.content
    assert "## 8. Parameter Suggestions" in report.content
    assert report.data["summary"]["total_signals"] == 1


def test_quality_report_service_can_read_from_repository_like_object(tmp_path: Path) -> None:
    class FakeRepository:
        def get_recent_signal_quality_rows(self, *, limit: int) -> list[dict]:
            assert limit == 5
            return []

    service = QualityReportService(repository=FakeRepository(), report_dir=tmp_path)

    report = service.generate(limit=5, timestamp=datetime(2026, 5, 5, 12, 1, tzinfo=UTC))

    assert "total_signals: 0" in report.content
    assert report.data["summary"]["total_signals"] == 0
