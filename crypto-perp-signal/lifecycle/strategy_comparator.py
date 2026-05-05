"""Compare Phase 14 strategy performance rows in memory."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class StrategyComparison:
    strategy_name: str
    signal_count: int
    tp1_hit_rate: float
    stop_rate: float
    expectancy_r: float
    avg_mfe: float
    avg_mae: float


def compare_strategies(rows: Iterable[dict[str, Any]]) -> list[StrategyComparison]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_strategy_name(row)].append(row)
    comparisons = [_compare_group(name, group_rows) for name, group_rows in grouped.items()]
    return sorted(comparisons, key=lambda item: (-item.expectancy_r, -item.signal_count, item.strategy_name))


def _compare_group(strategy_name: str, rows: list[dict[str, Any]]) -> StrategyComparison:
    total = len(rows)
    return StrategyComparison(
        strategy_name=strategy_name,
        signal_count=total,
        tp1_hit_rate=_rate(sum(1 for row in rows if _tp1_hit(row)), total),
        stop_rate=_rate(sum(1 for row in rows if _is_stopped(row)), total),
        expectancy_r=_average([_expectancy_r(row) for row in rows]),
        avg_mfe=_average([_to_float(row.get("max_favorable_excursion")) for row in rows]),
        avg_mae=_average([_to_float(row.get("max_adverse_excursion")) for row in rows]),
    )


def _strategy_name(row: dict[str, Any]) -> str:
    explicit = row.get("strategy_name") or row.get("signal_profile")
    if explicit:
        return str(explicit)
    for reason in row.get("reasons") or []:
        if str(reason).startswith("signal_profile:"):
            return str(reason).split(":", 1)[1].strip() or "unknown"
    return "unknown"


def _tp1_hit(row: dict[str, Any]) -> bool:
    if bool(row.get("tp1_hit")) or bool(row.get("target_touched")):
        return True
    return _status(row) in {"tp1_hit", "tp2_hit", "tp3_hit"}


def _is_stopped(row: dict[str, Any]) -> bool:
    return bool(row.get("stop_touched")) or _status(row) == "stopped"


def _expectancy_r(row: dict[str, Any]) -> float:
    status = _status(row)
    if status == "tp3_hit" or bool(row.get("tp3_hit")):
        return 3.0
    if status == "tp2_hit" or bool(row.get("tp2_hit")):
        return 2.0
    if _tp1_hit(row):
        return 1.0
    if _is_stopped(row):
        return -1.0
    return 0.0


def _status(row: dict[str, Any]) -> str:
    return str(row.get("tracking_status") or row.get("status") or row.get("signal_status") or "")


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
