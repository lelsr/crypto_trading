"""Signal quality analysis helpers for V1 lifecycle data."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Iterable


LEVELS = ("A", "B", "C")
SCORE_BUCKETS = ("70-75", "75-85", "85+")


@dataclass(frozen=True)
class GroupStats:
    group_by: str
    group_value: str
    count: int
    tp1_hit_rate: float
    stop_hit_rate: float
    avg_mfe_pct: float
    avg_mae_pct: float
    expectancy_r: float
    manual_good_bad_ratio: float | None
    sample_status: str


@dataclass(frozen=True)
class FailurePattern:
    pattern_name: str
    affected_count: int
    affected_symbols: list[str]
    severity: str
    evidence: str
    suggested_action: str


@dataclass(frozen=True)
class SignalQualitySummary:
    total_signals: int
    level_counts: dict[str, int]
    tp1_hit_rate: float
    tp2_hit_rate: float
    tp3_hit_rate: float
    stop_hit_rate: float
    expired_rate: float
    avg_mfe_pct: float
    avg_mae_pct: float
    median_mfe_pct: float
    median_mae_pct: float
    avg_duration_minutes: float
    manual_good_rate: float
    manual_bad_rate: float
    expectancy_r: float


@dataclass(frozen=True)
class SignalQualityAnalysis:
    summary: SignalQualitySummary
    groups: dict[str, list[GroupStats]] = field(default_factory=dict)
    failure_patterns: list[FailurePattern] = field(default_factory=list)


def analyze_signal_quality(
    rows: list[dict[str, Any]],
    *,
    min_sample_size: int = 10,
) -> SignalQualityAnalysis:
    normalized = [_normalize_row(row) for row in rows]
    summary = summarize_signal_quality(normalized)
    groups = analyze_group_stats(normalized, min_sample_size=min_sample_size)
    failure_patterns = analyze_failure_patterns(normalized, groups=groups, min_sample_size=min_sample_size)
    return SignalQualityAnalysis(summary=summary, groups=groups, failure_patterns=failure_patterns)


def summarize_signal_quality(rows: list[dict[str, Any]]) -> SignalQualitySummary:
    rows = [_normalize_row(row) for row in rows]
    total = len(rows)
    if total == 0:
        return SignalQualitySummary(
            total_signals=0,
            level_counts={level: 0 for level in LEVELS},
            tp1_hit_rate=0.0,
            tp2_hit_rate=0.0,
            tp3_hit_rate=0.0,
            stop_hit_rate=0.0,
            expired_rate=0.0,
            avg_mfe_pct=0.0,
            avg_mae_pct=0.0,
            median_mfe_pct=0.0,
            median_mae_pct=0.0,
            avg_duration_minutes=0.0,
            manual_good_rate=0.0,
            manual_bad_rate=0.0,
            expectancy_r=0.0,
        )

    level_counts = {level: sum(1 for row in rows if row["signal_level"] == level) for level in LEVELS}
    mfe_values = _float_values(row.get("max_favorable_excursion") for row in rows)
    mae_values = _float_values(row.get("max_adverse_excursion") for row in rows)
    duration_values = _float_values(row.get("duration_minutes") for row in rows)

    return SignalQualitySummary(
        total_signals=total,
        level_counts=level_counts,
        tp1_hit_rate=_rate(sum(1 for row in rows if _tp_hit(row, 1)), total),
        tp2_hit_rate=_rate(sum(1 for row in rows if _tp_hit(row, 2)), total),
        tp3_hit_rate=_rate(sum(1 for row in rows if _tp_hit(row, 3)), total),
        stop_hit_rate=_rate(sum(1 for row in rows if _is_stopped(row)), total),
        expired_rate=_rate(sum(1 for row in rows if _status(row) == "expired"), total),
        avg_mfe_pct=_average(mfe_values),
        avg_mae_pct=_average(mae_values),
        median_mfe_pct=round(float(median(mfe_values)), 6) if mfe_values else 0.0,
        median_mae_pct=round(float(median(mae_values)), 6) if mae_values else 0.0,
        avg_duration_minutes=_average(duration_values),
        manual_good_rate=_rate(sum(1 for row in rows if row.get("manual_verdict") == "good"), total),
        manual_bad_rate=_rate(sum(1 for row in rows if row.get("manual_verdict") == "bad"), total),
        expectancy_r=_average([_expectancy_r(row) for row in rows]),
    )


def analyze_group_stats(
    rows: list[dict[str, Any]],
    *,
    min_sample_size: int = 10,
) -> dict[str, list[GroupStats]]:
    groupers = {
        "signal_level": lambda row: [row["signal_level"]],
        "primary_exchange": lambda row: [_clean_group_value(row.get("primary_exchange"))],
        "symbol": lambda row: [_clean_group_value(row.get("symbol"))],
        "stop_reason": lambda row: [_clean_group_value(row.get("stop_reason"))],
        "signal_profile": lambda row: [_clean_group_value(row.get("signal_profile", "long_v1"))],
        "manual_tags": lambda row: [_clean_group_value(tag) for tag in row.get("manual_tags", [])] or ["none"],
        "score_bucket": lambda row: [_score_bucket(row.get("score"))],
    }
    result: dict[str, list[GroupStats]] = {}
    for group_by, value_fn in groupers.items():
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            for value in value_fn(row):
                buckets[value].append(row)
        stats = [_build_group_stats(group_by, value, bucket_rows, min_sample_size) for value, bucket_rows in buckets.items()]
        result[group_by] = sorted(stats, key=lambda item: (-item.count, item.group_value))
    return result


def analyze_failure_patterns(
    rows: list[dict[str, Any]],
    *,
    groups: dict[str, list[GroupStats]] | None = None,
    min_sample_size: int = 10,
) -> list[FailurePattern]:
    groups = groups or analyze_group_stats(rows, min_sample_size=min_sample_size)
    patterns: list[FailurePattern] = []

    high_score_stopped = [row for row in rows if _score(row) >= 85 and _is_stopped(row)]
    if high_score_stopped:
        patterns.append(
            _pattern(
                "high_score_stopped",
                high_score_stopped,
                severity="high" if len(high_score_stopped) >= 2 else "medium",
                evidence=f"{len(high_score_stopped)} signals scored >= 85 and stopped.",
                suggested_action="Review score gates and consider raising minimum RR or score requirements.",
            )
        )

    a_stopped = [row for row in rows if row["signal_level"] == "A" and _is_stopped(row)]
    if a_stopped:
        patterns.append(
            _pattern(
                "a_level_stopped",
                a_stopped,
                severity="high",
                evidence=f"{len(a_stopped)} A-level signals stopped.",
                suggested_action="Audit A-level promotion criteria before making thresholds looser.",
            )
        )

    high_rr_failed = [row for row in rows if _rr(row) >= 3.0 and _is_stopped(row)]
    if high_rr_failed:
        patterns.append(
            _pattern(
                "rr_ge_3_failed",
                high_rr_failed,
                severity="medium",
                evidence=f"{len(high_rr_failed)} signals with rr >= 3.0 stopped.",
                suggested_action="Check whether target distance is too optimistic for current market structure.",
            )
        )

    for group_name, action in (
        ("stop_reason", "Review stop source priority or buffer for this stop reason."),
        ("primary_exchange", "Add a warning or lower stability confidence for this exchange."),
        ("symbol", "Increase cooldown or require manual review for repeatedly failing symbols."),
    ):
        for stat in groups.get(group_name, []):
            if stat.count >= min_sample_size and stat.stop_hit_rate >= 0.4:
                patterns.append(
                    FailurePattern(
                        pattern_name=f"{group_name}_concentrated_failure:{stat.group_value}",
                        affected_count=stat.count,
                        affected_symbols=sorted({str(row.get("symbol")) for row in rows if _clean_group_value(row.get(group_name)) == stat.group_value}),
                        severity="high" if stat.stop_hit_rate >= 0.6 else "medium",
                        evidence=f"{stat.group_value} stop_hit_rate={stat.stop_hit_rate:.2%} across {stat.count} signals.",
                        suggested_action=action,
                    )
                )

    tag_counter = Counter(tag for row in rows for tag in row.get("manual_tags", []))
    for tag in ("false_breakout", "late_entry", "too_extended"):
        count = tag_counter.get(tag, 0)
        if count >= 3:
            affected = [row for row in rows if tag in row.get("manual_tags", [])]
            patterns.append(
                _pattern(
                    f"manual_tag_frequent:{tag}",
                    affected,
                    severity="high" if count >= min_sample_size else "medium",
                    evidence=f"Manual tag `{tag}` appeared {count} times.",
                    suggested_action="Convert repeated manual review language into a stricter pre-signal filter candidate.",
                )
            )

    low_mfe_high_mae = [
        row
        for row in rows
        if _to_float(row.get("max_favorable_excursion")) <= 0.5
        and _to_float(row.get("max_adverse_excursion")) <= -2.0
    ]
    if low_mfe_high_mae:
        patterns.append(
            _pattern(
                "low_mfe_high_mae",
                low_mfe_high_mae,
                severity="medium",
                evidence=f"{len(low_mfe_high_mae)} signals had MFE <= 0.5% and MAE <= -2.0%.",
                suggested_action="Review entry timing; late entries and weak support should be tagged during manual review.",
            )
        )

    return patterns


def _build_group_stats(
    group_by: str,
    group_value: str,
    rows: list[dict[str, Any]],
    min_sample_size: int,
) -> GroupStats:
    total = len(rows)
    mfe_values = _float_values(row.get("max_favorable_excursion") for row in rows)
    mae_values = _float_values(row.get("max_adverse_excursion") for row in rows)
    good = sum(1 for row in rows if row.get("manual_verdict") == "good")
    bad = sum(1 for row in rows if row.get("manual_verdict") == "bad")
    return GroupStats(
        group_by=group_by,
        group_value=group_value,
        count=total,
        tp1_hit_rate=_rate(sum(1 for row in rows if _tp_hit(row, 1)), total),
        stop_hit_rate=_rate(sum(1 for row in rows if _is_stopped(row)), total),
        avg_mfe_pct=_average(mfe_values),
        avg_mae_pct=_average(mae_values),
        expectancy_r=_average([_expectancy_r(row) for row in rows]),
        manual_good_bad_ratio=round(good / bad, 6) if bad else (float(good) if good else None),
        sample_status="ok" if total >= min_sample_size else "low_sample",
    )


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["reasons"] = list(row.get("reasons") or [])
    normalized["manual_tags"] = list(row.get("manual_tags") or [])
    normalized["signal_level"] = row.get("signal_level") or _extract_signal_level(normalized["reasons"], row.get("score"))
    normalized["signal_profile"] = row.get("signal_profile") or _extract_signal_profile(normalized["reasons"])
    normalized["score_bucket"] = _score_bucket(row.get("score"))
    normalized["rr"] = row.get("rr") if row.get("rr") is not None else _extract_reason_float(normalized["reasons"], "rr:")
    return normalized


def _extract_signal_level(reasons: Iterable[str], score: Any) -> str:
    for reason in reasons:
        if reason.startswith("signal_level:"):
            level = reason.split(":", 1)[1].strip().upper()
            if level in LEVELS:
                return level
    value = _score({"score": score})
    if value >= 85:
        return "A"
    if value >= 75:
        return "B"
    return "C"


def _extract_signal_profile(reasons: Iterable[str]) -> str:
    for reason in reasons:
        if reason.startswith("signal_profile:"):
            return reason.split(":", 1)[1].strip() or "long_v1"
    return "long_v1"


def _extract_reason_float(reasons: Iterable[str], prefix: str) -> float | None:
    for reason in reasons:
        if reason.startswith(prefix):
            try:
                return float(reason.split(":", 1)[1])
            except ValueError:
                return None
    return None


def _status(row: dict[str, Any]) -> str:
    return str(row.get("tracking_status") or row.get("status") or row.get("signal_status") or "")


def _is_stopped(row: dict[str, Any]) -> bool:
    return bool(row.get("stop_touched")) or _status(row) == "stopped"


def _tp_hit(row: dict[str, Any], level: int) -> bool:
    if bool(row.get(f"tp{level}_hit")):
        return True
    status = _status(row)
    if status == f"tp{level}_hit":
        return True
    if level == 1 and (bool(row.get("target_touched")) or status in {"tp2_hit", "tp3_hit"}):
        return True
    if level in {2, 3} and status == "tp3_hit":
        return True
    return _mfe_reached_r(row, level)


def _mfe_reached_r(row: dict[str, Any], level: int) -> bool:
    mfe = _to_float(row.get("max_favorable_excursion"))
    entry = _entry_ref(row)
    stop = _to_float(row.get("stop_loss"))
    if entry <= 0 or stop <= 0 or entry <= stop:
        return False
    risk_pct = (entry - stop) / entry * 100
    return risk_pct > 0 and mfe >= risk_pct * level


def _expectancy_r(row: dict[str, Any]) -> float:
    if _tp_hit(row, 3):
        return 3.0
    if _tp_hit(row, 2):
        return 2.0
    if _tp_hit(row, 1):
        return 1.0
    if _is_stopped(row):
        return -1.0
    return 0.0


def _entry_ref(row: dict[str, Any]) -> float:
    low = _to_float(row.get("entry_zone_low"))
    high = _to_float(row.get("entry_zone_high"))
    if low > 0 and high > 0:
        return (low + high) / 2
    return high or low


def _score(row: dict[str, Any]) -> float:
    return _to_float(row.get("score"))


def _rr(row: dict[str, Any]) -> float:
    return _to_float(row.get("rr"))


def _score_bucket(score: Any) -> str:
    value = _to_float(score)
    if value >= 85:
        return "85+"
    if value >= 75:
        return "75-85"
    return "70-75"


def _clean_group_value(value: Any) -> str:
    if value is None or value == "":
        return "unknown"
    return str(value)


def _float_values(values: Iterable[Any]) -> list[float]:
    return [float(value) for value in values if value is not None]


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _rate(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _pattern(
    pattern_name: str,
    rows: list[dict[str, Any]],
    *,
    severity: str,
    evidence: str,
    suggested_action: str,
) -> FailurePattern:
    return FailurePattern(
        pattern_name=pattern_name,
        affected_count=len(rows),
        affected_symbols=sorted({str(row.get("symbol")) for row in rows if row.get("symbol")}),
        severity=severity,
        evidence=evidence,
        suggested_action=suggested_action,
    )
