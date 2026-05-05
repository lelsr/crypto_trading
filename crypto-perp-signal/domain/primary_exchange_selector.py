"""Primary exchange selection for kline analysis."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from models import PrimaryExchangeDecision, UnifiedActivityCandidate


@dataclass(frozen=True)
class PrimaryExchangeScoreWeights:
    exchange_rank_score: float = 0.60
    kline_availability_score: float = 0.20
    exchange_stability_score: float = 0.20


def select_primary_exchanges(
    candidates: list[UnifiedActivityCandidate],
    *,
    exchange_health: dict[str, dict[str, Any]],
    available_exchanges_per_symbol: dict[str, list[str]],
    weights: PrimaryExchangeScoreWeights | None = None,
    decided_at: datetime | None = None,
) -> tuple[dict[str, PrimaryExchangeDecision | None], list[UnifiedActivityCandidate]]:
    weights = weights or PrimaryExchangeScoreWeights()
    decided_at = decided_at or datetime.now(UTC)
    if decided_at.tzinfo is None or decided_at.utcoffset() is None:
        raise ValueError("decided_at must be timezone-aware")

    decisions: dict[str, PrimaryExchangeDecision | None] = {}
    updated_candidates: list[UnifiedActivityCandidate] = []
    for candidate in candidates:
        decision = _select_for_candidate(
            candidate,
            exchange_health=exchange_health,
            available_exchanges=available_exchanges_per_symbol.get(candidate.symbol, []),
            weights=weights,
            decided_at=decided_at,
        )
        decisions[candidate.symbol] = decision
        updated_candidates.append(
            replace(candidate, primary_exchange=decision.primary_exchange if decision else None)
        )
    return decisions, updated_candidates


def _select_for_candidate(
    candidate: UnifiedActivityCandidate,
    *,
    exchange_health: dict[str, dict[str, Any]],
    available_exchanges: list[str],
    weights: PrimaryExchangeScoreWeights,
    decided_at: datetime,
) -> PrimaryExchangeDecision | None:
    available = set(available_exchanges)
    score_rows: dict[str, dict[str, float]] = {}
    for exchange in candidate.exchanges:
        kline_availability_score = 100.0 if exchange in available else 0.0
        if kline_availability_score <= 0:
            continue
        exchange_rank_score = _exchange_rank_score(candidate, exchange)
        exchange_stability_score = _exchange_stability_score(exchange_health.get(exchange, {}))
        primary_score = (
            exchange_rank_score * weights.exchange_rank_score
            + kline_availability_score * weights.kline_availability_score
            + exchange_stability_score * weights.exchange_stability_score
        )
        score_rows[exchange] = {
            "primary_score": round(primary_score, 6),
            "exchange_rank_score": round(exchange_rank_score, 6),
            "kline_availability_score": round(kline_availability_score, 6),
            "exchange_stability_score": round(exchange_stability_score, 6),
        }

    if not score_rows:
        return None

    selected_exchange = sorted(
        score_rows,
        key=lambda exchange: (-score_rows[exchange]["primary_score"], exchange),
    )[0]
    return PrimaryExchangeDecision(
        symbol=candidate.symbol,
        primary_exchange=selected_exchange,
        primary_score=score_rows[selected_exchange]["primary_score"],
        candidate_exchanges=sorted(score_rows),
        score_breakdown=_flatten_score_rows(score_rows),
        reason=_build_reason(selected_exchange, score_rows[selected_exchange]),
        decided_at=decided_at,
    )


def _exchange_rank_score(candidate: UnifiedActivityCandidate, exchange: str) -> float:
    keys = (
        f"{exchange}.exchange_rank_score",
        f"exchange_rank_score:{exchange}",
        f"{exchange}:exchange_rank_score",
        "exchange_rank_score",
    )
    for key in keys:
        if key in candidate.exchange_scores:
            return float(candidate.exchange_scores[key])
    if len(candidate.exchanges) == 1:
        return 100.0
    return 50.0


def _exchange_stability_score(health: dict[str, Any]) -> float:
    if "success_rate" in health:
        score = float(health["success_rate"]) * 100
    else:
        status_scores = {
            "ok": 100.0,
            "partial": 65.0,
            "stale_cache": 45.0,
            "skipped": 20.0,
            "failed": 0.0,
        }
        score = status_scores.get(str(health.get("source_status", "partial")), 65.0)

    latency_ms = health.get("latency_ms")
    if latency_ms is None:
        score -= 5.0
    elif latency_ms > 2_000:
        score -= 25.0
    elif latency_ms > 1_000:
        score -= 15.0
    elif latency_ms > 500:
        score -= 5.0

    recent_failures = int(health.get("recent_failures", 0) or 0)
    score -= min(recent_failures * 10.0, 50.0)
    return max(min(score, 100.0), 0.0)


def _flatten_score_rows(score_rows: dict[str, dict[str, float]]) -> dict[str, float]:
    flattened: dict[str, float] = {}
    for exchange, row in score_rows.items():
        for key, value in row.items():
            flattened[f"{exchange}.{key}"] = value
    return flattened


def _build_reason(selected_exchange: str, selected_scores: dict[str, float]) -> str:
    return (
        f"selected {selected_exchange} by primary_score={selected_scores['primary_score']:.2f}; "
        f"rank={selected_scores['exchange_rank_score']:.2f}, "
        f"kline={selected_scores['kline_availability_score']:.2f}, "
        f"stability={selected_scores['exchange_stability_score']:.2f}"
    )
