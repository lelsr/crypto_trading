"""Market cap enrichment and filtering for activity candidates."""

from __future__ import annotations

from dataclasses import dataclass, replace

from models import UnifiedActivityCandidate


@dataclass(frozen=True)
class MarketCapFilterConfig:
    enabled: bool = True
    min_market_cap: float = 50_000_000
    max_market_cap: float = 5_000_000_000
    keep_unknown_market_cap: bool = True


def apply_market_cap_filter(
    candidates: list[UnifiedActivityCandidate],
    market_caps: dict[str, float | None],
    config: MarketCapFilterConfig,
) -> list[UnifiedActivityCandidate]:
    enriched = [_with_market_cap(candidate, market_caps.get(candidate.symbol)) for candidate in candidates]
    if not config.enabled:
        return _sort_by_activity(enriched)

    filtered = [
        candidate
        for candidate in enriched
        if _is_kept_by_market_cap(candidate, config)
    ]
    return _sort_by_activity(filtered)


def _with_market_cap(candidate: UnifiedActivityCandidate, market_cap: float | None) -> UnifiedActivityCandidate:
    if market_cap is None:
        return replace(
            candidate,
            market_cap_usd=None,
            market_cap_status="unknown",
        )
    return replace(
        candidate,
        market_cap_usd=float(market_cap),
        market_cap_status="known",
    )


def _is_kept_by_market_cap(candidate: UnifiedActivityCandidate, config: MarketCapFilterConfig) -> bool:
    if candidate.market_cap_usd is None:
        return config.keep_unknown_market_cap
    return config.min_market_cap <= candidate.market_cap_usd <= config.max_market_cap


def _sort_by_activity(candidates: list[UnifiedActivityCandidate]) -> list[UnifiedActivityCandidate]:
    return sorted(candidates, key=lambda candidate: (-candidate.activity_score, candidate.symbol))
