from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from market_cap_filter import MarketCapFilterConfig, apply_market_cap_filter  # noqa: E402
from models import UnifiedActivityCandidate  # noqa: E402


def candidate(symbol: str, score: float) -> UnifiedActivityCandidate:
    return UnifiedActivityCandidate(
        symbol=symbol,
        exchanges=["binance"],
        primary_exchange=None,
        activity_score=score,
        global_quote_volume_24h_usd=1_000_000,
        market_cap_usd=None,
        market_cap_status="unknown",
        source_status="ok",
        exchange_scores={},
    )


def test_disabled_filter_only_enriches_market_cap_without_filtering() -> None:
    result = apply_market_cap_filter(
        [candidate("LOWUSDT", 10), candidate("HIGHUSDT", 20)],
        {"LOWUSDT": 1_000, "HIGHUSDT": 10_000_000_000},
        MarketCapFilterConfig(enabled=False, min_market_cap=50_000_000, max_market_cap=5_000_000_000),
    )

    assert [item.symbol for item in result] == ["HIGHUSDT", "LOWUSDT"]
    assert result[0].market_cap_usd == 10_000_000_000
    assert result[1].market_cap_usd == 1_000


def test_market_cap_inside_range_is_kept() -> None:
    result = apply_market_cap_filter(
        [candidate("BTCUSDT", 90)],
        {"BTCUSDT": 100_000_000},
        MarketCapFilterConfig(enabled=True, min_market_cap=50_000_000, max_market_cap=5_000_000_000),
    )

    assert len(result) == 1
    assert result[0].market_cap_status == "known"
    assert result[0].market_cap_usd == 100_000_000


def test_market_cap_below_min_is_removed() -> None:
    result = apply_market_cap_filter(
        [candidate("TINYUSDT", 90)],
        {"TINYUSDT": 10_000_000},
        MarketCapFilterConfig(enabled=True, min_market_cap=50_000_000, max_market_cap=5_000_000_000),
    )

    assert result == []


def test_market_cap_above_max_is_removed() -> None:
    result = apply_market_cap_filter(
        [candidate("MEGAUSDT", 90)],
        {"MEGAUSDT": 10_000_000_000},
        MarketCapFilterConfig(enabled=True, min_market_cap=50_000_000, max_market_cap=5_000_000_000),
    )

    assert result == []


def test_unknown_market_cap_is_kept_when_configured() -> None:
    result = apply_market_cap_filter(
        [candidate("UNKNOWNUSDT", 70)],
        {"UNKNOWNUSDT": None},
        MarketCapFilterConfig(enabled=True, keep_unknown_market_cap=True),
    )

    assert len(result) == 1
    assert result[0].market_cap_usd is None
    assert result[0].market_cap_status == "unknown"
    assert result[0].activity_score == 70


def test_unknown_market_cap_is_removed_when_configured() -> None:
    result = apply_market_cap_filter(
        [candidate("UNKNOWNUSDT", 70)],
        {},
        MarketCapFilterConfig(enabled=True, keep_unknown_market_cap=False),
    )

    assert result == []


def test_filtered_result_is_resorted_by_activity_score_desc() -> None:
    result = apply_market_cap_filter(
        [
            candidate("MIDUSDT", 50),
            candidate("HIGHUSDT", 90),
            candidate("LOWUSDT", 10),
        ],
        {
            "MIDUSDT": 100_000_000,
            "HIGHUSDT": 100_000_000,
            "LOWUSDT": 100_000_000,
        },
        MarketCapFilterConfig(enabled=True),
    )

    assert [item.symbol for item in result] == ["HIGHUSDT", "MIDUSDT", "LOWUSDT"]


def test_empty_input_returns_empty_list() -> None:
    result = apply_market_cap_filter(
        [],
        {},
        MarketCapFilterConfig(enabled=True),
    )

    assert result == []
