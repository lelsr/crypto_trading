"""Markdown scan report generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScanReport:
    path: Path
    content: str


def build_scan_report(
    *,
    scan_id: str,
    candidate_count: int,
    signal_count: int,
    failed_exchanges: list[str],
    skipped_symbols: list[str],
    notification_results: list[dict],
) -> str:
    lines = [
        f"# Scan Report {scan_id}",
        "",
        f"- scan_id: `{scan_id}`",
        f"- candidate_count: {candidate_count}",
        f"- signal_count: {signal_count}",
        f"- failed_exchanges: {', '.join(failed_exchanges) if failed_exchanges else 'none'}",
        f"- skipped_symbols: {', '.join(skipped_symbols) if skipped_symbols else 'none'}",
        "",
        "## Notification Results",
    ]
    if notification_results:
        for result in notification_results:
            lines.append(
                f"- {result.get('symbol', 'unknown')}: {result.get('status')} "
                f"({result.get('reason', 'unknown')})"
            )
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def write_scan_report(
    *,
    report_dir: str | Path,
    scan_id: str,
    candidate_count: int,
    signal_count: int,
    failed_exchanges: list[str],
    skipped_symbols: list[str],
    notification_results: list[dict],
) -> ScanReport:
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    content = build_scan_report(
        scan_id=scan_id,
        candidate_count=candidate_count,
        signal_count=signal_count,
        failed_exchanges=failed_exchanges,
        skipped_symbols=skipped_symbols,
        notification_results=notification_results,
    )
    path = report_path / f"{scan_id}.md"
    path.write_text(content, encoding="utf-8")
    return ScanReport(path=path, content=content)
