"""Markdown quality report generation for signal evolution analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lifecycle.parameter_optimizer import ParameterSuggestion, generate_parameter_suggestions
from lifecycle.signal_quality_analyzer import SignalQualityAnalysis, analyze_signal_quality


@dataclass(frozen=True)
class QualityReport:
    path: Path
    content: str
    data: dict[str, Any]


class QualityReportService:
    def __init__(self, *, repository: Any | None = None, report_dir: str | Path = "data/reports/quality") -> None:
        self.repository = repository
        self.report_dir = Path(report_dir)

    def generate(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        limit: int = 200,
        min_sample_size: int = 10,
        current_parameters: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> QualityReport:
        if rows is None:
            if self.repository is None:
                rows = []
            elif hasattr(self.repository, "get_recent_signal_quality_rows"):
                rows = self.repository.get_recent_signal_quality_rows(limit=limit)
            else:
                rows = self.repository.get_recent_signal_feedback_rows(limit=limit)

        analysis = analyze_signal_quality(rows, min_sample_size=min_sample_size)
        suggestions = generate_parameter_suggestions(
            summary=analysis.summary,
            groups=analysis.groups,
            failure_patterns=analysis.failure_patterns,
            current_parameters=current_parameters,
            min_sample_size=min_sample_size,
        )
        data = build_quality_report_data(analysis=analysis, suggestions=suggestions)
        content = build_quality_report_markdown(data)
        path = write_quality_report_content(self.report_dir, content, timestamp=timestamp)
        return QualityReport(path=path, content=content, data=data)


def build_quality_report_data(
    *,
    analysis: SignalQualityAnalysis,
    suggestions: list[ParameterSuggestion],
) -> dict[str, Any]:
    return {
        "summary": asdict(analysis.summary),
        "groups": {
            name: [asdict(stat) for stat in stats]
            for name, stats in analysis.groups.items()
        },
        "failure_patterns": [asdict(pattern) for pattern in analysis.failure_patterns],
        "parameter_suggestions": [asdict(suggestion) for suggestion in suggestions],
    }


def build_quality_report_markdown(data: dict[str, Any]) -> str:
    summary = data["summary"]
    lines = [
        "# Signal Quality Report",
        "",
        "## 1. Overview",
        f"- total_signals: {summary['total_signals']}",
        f"- expectancy_r: {summary['expectancy_r']}",
        f"- stop_hit_rate: {_pct(summary['stop_hit_rate'])}",
        f"- tp1_hit_rate: {_pct(summary['tp1_hit_rate'])}",
        "",
        "## 2. Signal Quality Metrics",
        f"- tp2_hit_rate: {_pct(summary['tp2_hit_rate'])}",
        f"- tp3_hit_rate: {_pct(summary['tp3_hit_rate'])}",
        f"- expired_rate: {_pct(summary['expired_rate'])}",
        f"- avg_mfe_pct: {summary['avg_mfe_pct']}",
        f"- avg_mae_pct: {summary['avg_mae_pct']}",
        f"- median_mfe_pct: {summary['median_mfe_pct']}",
        f"- median_mae_pct: {summary['median_mae_pct']}",
        f"- avg_duration_minutes: {summary['avg_duration_minutes']}",
        f"- manual_good_rate: {_pct(summary['manual_good_rate'])}",
        f"- manual_bad_rate: {_pct(summary['manual_bad_rate'])}",
        "",
        "## 3. A/B/C Level Performance",
    ]
    lines.extend(_group_table(data, "signal_level"))
    lines.extend(["", "## 4. Exchange Performance"])
    lines.extend(_group_table(data, "primary_exchange"))
    lines.extend(["", "## 5. Symbol Performance"])
    lines.extend(_group_table(data, "symbol"))
    lines.extend(["", "## 6. Stop Reason Performance"])
    lines.extend(_group_table(data, "stop_reason"))
    lines.extend(["", "## 7. Failure Patterns"])
    patterns = data["failure_patterns"]
    if patterns:
        for pattern in patterns:
            lines.append(
                f"- {pattern['pattern_name']} [{pattern['severity']}]: "
                f"{pattern['evidence']} Action: {pattern['suggested_action']}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## 8. Parameter Suggestions"])
    suggestions = data["parameter_suggestions"]
    if suggestions:
        for suggestion in suggestions:
            lines.append(
                f"- {suggestion['suggestion_type']} `{suggestion['parameter_name']}`: "
                f"{suggestion['current_value']} -> {suggestion['suggested_value']} "
                f"({suggestion['confidence']}, sample={suggestion['sample_size']}, "
                f"auto={suggestion['apply_automatically']}). {suggestion['reason']}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## 9. Low Sample Warnings"])
    low_samples = [
        stat
        for stats in data["groups"].values()
        for stat in stats
        if stat["sample_status"] == "low_sample"
    ]
    if low_samples:
        for stat in low_samples[:20]:
            lines.append(f"- {stat['group_by']}={stat['group_value']} count={stat['count']}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## 10. Manual Review Next Steps",
            "- Prioritize high-severity failure patterns before changing thresholds.",
            "- Review low-sample groups as observations only.",
            "- Keep all parameter changes manual until a later confirmed phase.",
            "",
        ]
    )
    return "\n".join(lines)


def write_quality_report_content(
    report_dir: str | Path,
    content: str,
    *,
    timestamp: datetime | None = None,
) -> Path:
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    timestamp = timestamp or datetime.now(UTC)
    filename = f"quality-report-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.md"
    path = report_path / filename
    path.write_text(content, encoding="utf-8")
    return path


def _group_table(data: dict[str, Any], group_name: str) -> list[str]:
    rows = data["groups"].get(group_name, [])
    if not rows:
        return ["- none"]
    lines = ["| group | count | tp1 | stop | avg_mfe | avg_mae | expectancy_r | sample |", "|---|---:|---:|---:|---:|---:|---:|---|"]
    for row in rows[:20]:
        lines.append(
            f"| {row['group_value']} | {row['count']} | {_pct(row['tp1_hit_rate'])} | "
            f"{_pct(row['stop_hit_rate'])} | {row['avg_mfe_pct']} | {row['avg_mae_pct']} | "
            f"{row['expectancy_r']} | {row['sample_status']} |"
        )
    return lines


def _pct(value: float) -> str:
    return f"{float(value) * 100:.2f}%"
