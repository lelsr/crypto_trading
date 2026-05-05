"""Parameter suggestion engine for signal quality analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lifecycle.signal_quality_analyzer import FailurePattern, GroupStats, SignalQualitySummary


@dataclass(frozen=True)
class ParameterSuggestion:
    suggestion_type: str
    parameter_name: str
    current_value: Any
    suggested_value: Any
    confidence: str
    reason: str
    evidence: str
    sample_size: int
    apply_automatically: bool = False


def generate_parameter_suggestions(
    *,
    summary: SignalQualitySummary,
    groups: dict[str, list[GroupStats]],
    failure_patterns: list[FailurePattern],
    current_parameters: dict[str, Any] | None = None,
    min_sample_size: int = 10,
) -> list[ParameterSuggestion]:
    params = current_parameters or {}
    suggestions: list[ParameterSuggestion] = []

    level_a = _find_group(groups, "signal_level", "A")
    if level_a and level_a.count >= min_sample_size and level_a.stop_hit_rate > 0.4:
        suggestions.append(
            ParameterSuggestion(
                suggestion_type="raise_min_score",
                parameter_name="signals.min_score_to_generate",
                current_value=params.get("signals.min_score_to_generate", 70),
                suggested_value=max(int(params.get("signals.min_score_to_generate", 70)), 75),
                confidence="medium",
                reason="A-level signals are stopping too often.",
                evidence=f"A stop_hit_rate={level_a.stop_hit_rate:.2%} across {level_a.count} signals.",
                sample_size=level_a.count,
            )
        )
        suggestions.append(
            ParameterSuggestion(
                suggestion_type="raise_min_rr",
                parameter_name="long_signal_v1.min_rr",
                current_value=params.get("long_signal_v1.min_rr", 2.0),
                suggested_value=max(float(params.get("long_signal_v1.min_rr", 2.0)), 2.5),
                confidence="medium",
                reason="High-grade signals need stronger reward-to-risk confirmation before promotion.",
                evidence=f"A stop_hit_rate={level_a.stop_hit_rate:.2%} across {level_a.count} signals.",
                sample_size=level_a.count,
            )
        )

    if summary.total_signals >= min_sample_size and summary.expectancy_r < 0:
        suggestions.append(
            ParameterSuggestion(
                suggestion_type="tighten_threshold",
                parameter_name="long_signal_v1.gating",
                current_value=params.get("long_signal_v1.gating", "current"),
                suggested_value="stricter_manual_review_required",
                confidence="medium",
                reason="Overall expectancy is negative.",
                evidence=f"expectancy_r={summary.expectancy_r:.3f} across {summary.total_signals} signals.",
                sample_size=summary.total_signals,
            )
        )

    for stat in groups.get("primary_exchange", []):
        if stat.count >= min_sample_size and stat.stop_hit_rate > 0.45:
            suggestions.append(
                ParameterSuggestion(
                    suggestion_type="review_manually",
                    parameter_name=f"primary_exchange.stability_warning.{stat.group_value}",
                    current_value=params.get(f"primary_exchange.stability_warning.{stat.group_value}", False),
                    suggested_value=True,
                    confidence="medium",
                    reason="This exchange has an abnormal stop-hit rate in generated signals.",
                    evidence=f"{stat.group_value} stop_hit_rate={stat.stop_hit_rate:.2%} across {stat.count} signals.",
                    sample_size=stat.count,
                )
            )

    for stat in groups.get("symbol", []):
        if stat.count >= min_sample_size and stat.stop_hit_rate > 0.5:
            suggestions.append(
                ParameterSuggestion(
                    suggestion_type="increase_cooldown",
                    parameter_name=f"cooldown.symbol.{stat.group_value}",
                    current_value=params.get("cooldown_hours", 6),
                    suggested_value=min(int(params.get("cooldown_hours", 6)) + 2, 8),
                    confidence="medium",
                    reason="This symbol repeatedly fails within the analyzed sample.",
                    evidence=f"{stat.group_value} stop_hit_rate={stat.stop_hit_rate:.2%} across {stat.count} signals.",
                    sample_size=stat.count,
                )
            )

    for stat in groups.get("manual_tags", []):
        if stat.count < 3:
            continue
        if stat.group_value in {"too_extended", "late_entry"}:
            suggestions.append(
                ParameterSuggestion(
                    suggestion_type="adjust_chase_risk_threshold",
                    parameter_name="long_signal_v1.max_close_above_ema20_pct",
                    current_value=params.get("long_signal_v1.max_close_above_ema20_pct", 0.02),
                    suggested_value=min(float(params.get("long_signal_v1.max_close_above_ema20_pct", 0.02)), 0.015),
                    confidence="low" if stat.count < min_sample_size else "medium",
                    reason=f"Manual reviews frequently tag `{stat.group_value}`.",
                    evidence=f"{stat.group_value} appeared in {stat.count} reviewed signals.",
                    sample_size=stat.count,
                )
            )
        if stat.group_value == "false_breakout":
            suggestions.append(
                ParameterSuggestion(
                    suggestion_type="tighten_threshold",
                    parameter_name="long_signal_v1.breakout_confirmation",
                    current_value=params.get("long_signal_v1.breakout_confirmation", "current"),
                    suggested_value="require_stronger_close_confirmation",
                    confidence="low" if stat.count < min_sample_size else "medium",
                    reason="False breakout tags suggest entry confirmation is too permissive.",
                    evidence=f"false_breakout appeared in {stat.count} reviewed signals.",
                    sample_size=stat.count,
                )
            )

    for pattern in failure_patterns:
        if pattern.pattern_name.startswith("rr_ge_3_failed"):
            suggestions.append(
                ParameterSuggestion(
                    suggestion_type="raise_min_rr",
                    parameter_name="long_signal_v1.min_rr",
                    current_value=params.get("long_signal_v1.min_rr", 2.0),
                    suggested_value=max(float(params.get("long_signal_v1.min_rr", 2.0)), 2.5),
                    confidence=_confidence(pattern, min_sample_size),
                    reason="High-RR candidates are still failing, so target quality needs review.",
                    evidence=pattern.evidence,
                    sample_size=pattern.affected_count,
                )
            )
        elif pattern.pattern_name.startswith("low_mfe_high_mae"):
            suggestions.append(
                ParameterSuggestion(
                    suggestion_type="review_manually",
                    parameter_name="long_signal_v1.entry_timing",
                    current_value=params.get("long_signal_v1.entry_timing", "current"),
                    suggested_value="audit_entry_structure",
                    confidence=_confidence(pattern, min_sample_size),
                    reason="Signals move against the entry before producing useful upside.",
                    evidence=pattern.evidence,
                    sample_size=pattern.affected_count,
                )
            )

    return _dedupe_suggestions(suggestions)


def _find_group(groups: dict[str, list[GroupStats]], group_by: str, group_value: str) -> GroupStats | None:
    for stat in groups.get(group_by, []):
        if stat.group_value == group_value:
            return stat
    return None


def _confidence(pattern: FailurePattern, min_sample_size: int) -> str:
    if pattern.affected_count >= min_sample_size and pattern.severity == "high":
        return "high"
    if pattern.affected_count >= min_sample_size:
        return "medium"
    return "low"


def _dedupe_suggestions(suggestions: list[ParameterSuggestion]) -> list[ParameterSuggestion]:
    seen: set[tuple[str, str]] = set()
    unique: list[ParameterSuggestion] = []
    for suggestion in suggestions:
        key = (suggestion.suggestion_type, suggestion.parameter_name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(suggestion)
    return unique
