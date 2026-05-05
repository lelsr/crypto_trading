from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from activity_ranker import rank_activity_candidates  # noqa: E402
from models import ExchangeTicker  # noqa: E402


def ticker(
    exchange: str,
    symbol: str,
    quote_volume: float | None,
    *,
    status: str = "ok",
    latency_ms: int | None = 100,
    last_price: float | None = 1.0,
) -> ExchangeTicker:
    return ExchangeTicker(
        exchange=exchange,
        raw_symbol=symbol,
        unified_symbol=symbol.replace("-", "").replace("SWAP", "").replace("USDTUSDT", "USDT"),
        quote_volume_24h_usd=quote_volume,
        base_volume_24h=None,
        last_price=last_price,
        price_change_pct_24h=None,
        source_status=status,
        latency_ms=latency_ms,
        updated_at=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),
    )


def test_preselect_top_n_per_exchange_is_applied() -> None:
    candidates = rank_activity_candidates(
        [
            ticker("binance", "AAAUSDT", 300),
            ticker("binance", "BBBUSDT", 200),
            ticker("binance", "CCCUSDT", 100),
            ticker("okx", "DDDUSDT", 50),
        ],
        preselect_top_n_per_exchange=2,
    )

    symbols = {candidate.symbol for candidate in candidates}
    assert symbols == {"AAAUSDT", "BBBUSDT", "DDDUSDT"}
    assert "CCCUSDT" not in symbols


def test_same_symbol_is_merged_across_exchanges() -> None:
    candidates = rank_activity_candidates(
        [
            ticker("binance", "BTCUSDT", 1_000),
            ticker("okx", "BTCUSDT", 800),
        ],
        preselect_top_n_per_exchange=10,
    )

    assert len(candidates) == 1
    assert candidates[0].symbol == "BTCUSDT"
    assert candidates[0].exchanges == ["binance", "okx"]
    assert candidates[0].global_quote_volume_24h_usd == 1_800


def test_exchange_presence_score_adds_multi_exchange_bonus() -> None:
    candidates = rank_activity_candidates(
        [
            ticker("binance", "BTCUSDT", 1_000),
            ticker("okx", "BTCUSDT", 900),
            ticker("binance", "ETHUSDT", 950),
        ],
        preselect_top_n_per_exchange=10,
    )
    by_symbol = {candidate.symbol: candidate for candidate in candidates}

    assert by_symbol["BTCUSDT"].exchange_scores["exchange_presence_score"] == 100.0
    assert by_symbol["ETHUSDT"].exchange_scores["exchange_presence_score"] == 50.0


def test_missing_volume_does_not_crash_and_is_ranked_lower() -> None:
    candidates = rank_activity_candidates(
        [
            ticker("binance", "BTCUSDT", 1_000),
            ticker("binance", "UNKNOWNUSDT", None),
        ],
        preselect_top_n_per_exchange=10,
    )

    assert [candidate.symbol for candidate in candidates] == ["BTCUSDT", "UNKNOWNUSDT"]
    assert candidates[1].global_quote_volume_24h_usd is None


def test_failed_source_status_lowers_data_confidence_score() -> None:
    candidates = rank_activity_candidates(
        [
            ticker("binance", "GOODUSDT", 1_000, status="ok"),
            ticker("okx", "BADUSDT", 1_000, status="failed"),
        ],
        preselect_top_n_per_exchange=10,
    )
    by_symbol = {candidate.symbol: candidate for candidate in candidates}

    assert by_symbol["GOODUSDT"].exchange_scores["data_confidence_score"] > by_symbol["BADUSDT"].exchange_scores[
        "data_confidence_score"
    ]


def test_market_cap_fields_are_not_used_in_activity_ranking() -> None:
    candidates = rank_activity_candidates(
        [
            ticker("binance", "BTCUSDT", 1_000),
            ticker("binance", "DOGEUSDT", 999),
        ],
        preselect_top_n_per_exchange=10,
    )

    assert all(candidate.market_cap_usd is None for candidate in candidates)
    assert all(candidate.market_cap_status == "unknown" for candidate in candidates)


def test_primary_exchange_is_not_selected_in_activity_phase() -> None:
    candidates = rank_activity_candidates(
        [
            ticker("binance", "BTCUSDT", 1_000),
            ticker("okx", "BTCUSDT", 900),
        ],
        preselect_top_n_per_exchange=10,
    )

    assert candidates[0].primary_exchange is None


def test_output_is_sorted_by_activity_score_descending() -> None:
    candidates = rank_activity_candidates(
        [
            ticker("binance", "LOWUSDT", 100),
            ticker("binance", "HIGHUSDT", 1_000),
            ticker("okx", "HIGHUSDT", 900),
        ],
        preselect_top_n_per_exchange=10,
    )

    scores = [candidate.activity_score for candidate in candidates]
    assert scores == sorted(scores, reverse=True)
    assert candidates[0].symbol == "HIGHUSDT"


def test_ranking_is_not_simple_sum_of_volume() -> None:
    candidates = rank_activity_candidates(
        [
            ticker("binance", "SINGLEUSDT", 1_100),
            ticker("binance", "PRESENTUSDT", 600),
            ticker("okx", "PRESENTUSDT", 500),
        ],
        preselect_top_n_per_exchange=10,
    )
    by_symbol = {candidate.symbol: candidate for candidate in candidates}

    assert by_symbol["SINGLEUSDT"].global_quote_volume_24h_usd == by_symbol["PRESENTUSDT"].global_quote_volume_24h_usd
    assert by_symbol["PRESENTUSDT"].exchange_scores["exchange_presence_score"] > by_symbol["SINGLEUSDT"].exchange_scores[
        "exchange_presence_score"
    ]
    assert by_symbol["PRESENTUSDT"].activity_score != by_symbol["SINGLEUSDT"].global_quote_volume_24h_usd
