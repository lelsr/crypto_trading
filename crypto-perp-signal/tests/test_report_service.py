from __future__ import annotations

from application.report_service import build_scan_report, write_scan_report


def test_report_generation_writes_markdown(tmp_path) -> None:
    report = write_scan_report(
        report_dir=tmp_path,
        scan_id="scan-1",
        candidate_count=2,
        signal_count=1,
        failed_exchanges=["badex"],
        skipped_symbols=["ETHUSDT"],
        notification_results=[{"symbol": "BTCUSDT", "status": "sent", "reason": "ok"}],
    )

    assert report.path.exists()
    assert "# Scan Report scan-1" in report.content
    assert "candidate_count: 2" in report.content
    assert "badex" in report.content
    assert "ETHUSDT" in report.content
    assert report.path.read_text(encoding="utf-8") == report.content


def test_build_report_handles_empty_sections() -> None:
    content = build_scan_report(
        scan_id="scan-empty",
        candidate_count=0,
        signal_count=0,
        failed_exchanges=[],
        skipped_symbols=[],
        notification_results=[],
    )

    assert "failed_exchanges: none" in content
    assert "skipped_symbols: none" in content
    assert "- none" in content
