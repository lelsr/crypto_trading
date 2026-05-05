"""Activity ranking for unified USDT perpetual candidates."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from models import ExchangeTicker, UnifiedActivityCandidate


@dataclass(frozen=True)
class ActivityScoreWeights:
    exchange_rank_score: float = 0.50
    normalized_quote_volume_score: float = 0.25
    exchange_presence_score: float = 0.15
    data_confidence_score: float = 0.10


def rank_activity_candidates(
    exchange_tickers: list[ExchangeTicker],
    *,
    preselect_top_n_per_exchange: int = 300,
    weights: ActivityScoreWeights | None = None,
) -> list[UnifiedActivityCandidate]:
    weights = weights or ActivityScoreWeights()
    preselected = _preselect_by_exchange(exchange_tickers, preselect_top_n_per_exchange)
    if not preselected:
        return []

    max_quote_volume = max(
        (ticker.quote_volume_24h_usd or 0.0 for ticker in preselected),
        default=0.0,
    )
    max_exchange_presence = len({ticker.exchange for ticker in preselected}) or 1
    rank_scores = _exchange_rank_scores(preselected)

    grouped: dict[str, list[ExchangeTicker]] = defaultdict(list)
    for ticker in preselected:
        grouped[ticker.unified_symbol].append(ticker)

    candidates: list[UnifiedActivityCandidate] = []
    for symbol, tickers in grouped.items():
        exchange_rank_score = _average([rank_scores[(ticker.exchange, ticker.unified_symbol)] for ticker in tickers])
        normalized_quote_volume_score = _normalized_volume_score(tickers, max_quote_volume)
        exchange_presence_score = min(len({ticker.exchange for ticker in tickers}) / max_exchange_presence, 1.0) * 100
        data_confidence_score = _average([_data_confidence_score(ticker) for ticker in tickers])
        activity_score = (
            exchange_rank_score * weights.exchange_rank_score
            + normalized_quote_volume_score * weights.normalized_quote_volume_score
            + exchange_presence_score * weights.exchange_presence_score
            + data_confidence_score * weights.data_confidence_score
        )
        global_quote_volume = _sum_optional(ticker.quote_volume_24h_usd for ticker in tickers)
        source_status = _combined_source_status([ticker.source_status for ticker in tickers])
        candidates.append(
            UnifiedActivityCandidate(
                symbol=symbol,
                exchanges=sorted({ticker.exchange for ticker in tickers}),
                primary_exchange=None,
                activity_score=round(activity_score, 6),
                global_quote_volume_24h_usd=global_quote_volume,
                market_cap_usd=None,
                market_cap_status="unknown",
                source_status=source_status,
                exchange_scores={
                    "exchange_rank_score": round(exchange_rank_score, 6),
                    "normalized_quote_volume_score": round(normalized_quote_volume_score, 6),
                    "exchange_presence_score": round(exchange_presence_score, 6),
                    "data_confidence_score": round(data_confidence_score, 6),
                },
            )
        )

    return sorted(candidates, key=lambda item: (-item.activity_score, item.symbol))


def _preselect_by_exchange(tickers: list[ExchangeTicker], top_n: int) -> list[ExchangeTicker]:
    if top_n <= 0:
        return []
    grouped: dict[str, list[ExchangeTicker]] = defaultdict(list)
    for ticker in tickers:
        grouped[ticker.exchange].append(ticker)
    preselected: list[ExchangeTicker] = []
    for exchange_tickers in grouped.values():
        preselected.extend(
            sorted(
                exchange_tickers,
                key=lambda ticker: (ticker.quote_volume_24h_usd is not None, ticker.quote_volume_24h_usd or 0.0),
                reverse=True,
            )[:top_n]
        )
    return preselected


def _exchange_rank_scores(tickers: list[ExchangeTicker]) -> dict[tuple[str, str], float]:
    grouped: dict[str, list[ExchangeTicker]] = defaultdict(list)
    for ticker in tickers:
        grouped[ticker.exchange].append(ticker)
    scores: dict[tuple[str, str], float] = {}
    for exchange, exchange_tickers in grouped.items():
        sorted_tickers = sorted(
            exchange_tickers,
            key=lambda ticker: (ticker.quote_volume_24h_usd is not None, ticker.quote_volume_24h_usd or 0.0),
            reverse=True,
        )
        total = len(sorted_tickers)
        for index, ticker in enumerate(sorted_tickers):
            score = 100.0 if total == 1 else (1 - index / (total - 1)) * 100
            scores[(exchange, ticker.unified_symbol)] = score
    return scores


def _normalized_volume_score(tickers: list[ExchangeTicker], max_quote_volume: float) -> float:
    if max_quote_volume <= 0:
        return 0.0
    best_volume = max((ticker.quote_volume_24h_usd or 0.0 for ticker in tickers), default=0.0)
    return min(best_volume / max_quote_volume, 1.0) * 100


def _data_confidence_score(ticker: ExchangeTicker) -> float:
    status_scores = {
        "ok": 100.0,
        "partial": 65.0,
        "stale_cache": 45.0,
        "skipped": 20.0,
        "failed": 0.0,
    }
    score = status_scores.get(str(ticker.source_status), 35.0)
    if ticker.quote_volume_24h_usd is None:
        score -= 25.0
    if ticker.last_price is None:
        score -= 10.0
    if ticker.latency_ms is None:
        score -= 10.0
    elif ticker.latency_ms > 2_000:
        score -= 20.0
    elif ticker.latency_ms > 1_000:
        score -= 10.0
    return max(score, 0.0)


def _combined_source_status(statuses: list[str]) -> str:
    unique = set(statuses)
    if unique == {"ok"}:
        return "ok"
    if "ok" in unique:
        return "partial"
    if "stale_cache" in unique:
        return "stale_cache"
    if "partial" in unique:
        return "partial"
    return "failed"


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sum_optional(values: object) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return float(sum(present))
