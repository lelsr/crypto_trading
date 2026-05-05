from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from models import UnifiedActivityCandidate  # noqa: E402
from primary_exchange_selector import select_primary_exchanges  # noqa: E402


DECIDED_AT = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


def candidate(
    symbol: str,
    exchanges: list[str],
    *,
    activity_score: float = 80.0,
    exchange_scores: dict[str, float] | None = None,
) -> UnifiedActivityCandidate:
    return UnifiedActivityCandidate(
        symbol=symbol,
        exchanges=exchanges,
        primary_exchange=None,
        activity_score=activity_score,
        global_quote_volume_24h_usd=1_000_000,
        market_cap_usd=100_000_000,
        market_cap_status="known",
        source_status="ok",
        exchange_scores=exchange_scores or {},
    )


def test_each_symbol_gets_one_primary_exchange() -> None:
    decisions, updated = select_primary_exchanges(
        [
            candidate("BTCUSDT", ["binance", "okx"], exchange_scores={"binance.exchange_rank_score": 90, "okx.exchange_rank_score": 80}),
            candidate("ETHUSDT", ["okx"], exchange_scores={"okx.exchange_rank_score": 100}),
        ],
        exchange_health={"binance": {"success_rate": 0.99, "latency_ms": 100}, "okx": {"success_rate": 0.95, "latency_ms": 120}},
        available_exchanges_per_symbol={"BTCUSDT": ["binance", "okx"], "ETHUSDT": ["okx"]},
        decided_at=DECIDED_AT,
    )

    assert decisions["BTCUSDT"] is not None
    assert decisions["ETHUSDT"] is not None
    assert len({item.symbol: item.primary_exchange for item in updated}) == 2
    assert all(item.primary_exchange is not None for item in updated)


def test_selector_does_not_pin_binance() -> None:
    decisions, updated = select_primary_exchanges(
        [
            candidate(
                "BTCUSDT",
                ["binance", "okx"],
                exchange_scores={"binance.exchange_rank_score": 70, "okx.exchange_rank_score": 95},
            )
        ],
        exchange_health={"binance": {"success_rate": 0.60, "latency_ms": 1_500}, "okx": {"success_rate": 0.99, "latency_ms": 80}},
        available_exchanges_per_symbol={"BTCUSDT": ["binance", "okx"]},
        decided_at=DECIDED_AT,
    )

    assert decisions["BTCUSDT"].primary_exchange == "okx"
    assert updated[0].primary_exchange == "okx"


def test_no_default_binance() -> None:
    decisions, updated = select_primary_exchanges(
        [
            candidate(
                "BTCUSDT",
                ["binance", "okx"],
                exchange_scores={"binance.exchange_rank_score": 100, "okx.exchange_rank_score": 92},
            )
        ],
        exchange_health={
            "binance": {"success_rate": 0.20, "latency_ms": 3_000, "recent_failures": 5},
            "okx": {"success_rate": 1.0, "latency_ms": 80, "recent_failures": 0},
        },
        available_exchanges_per_symbol={"BTCUSDT": ["binance", "okx"]},
        decided_at=DECIDED_AT,
    )

    assert decisions["BTCUSDT"].primary_exchange == "okx"
    assert updated[0].primary_exchange == "okx"
    assert decisions["BTCUSDT"].score_breakdown["binance.exchange_rank_score"] > decisions["BTCUSDT"].score_breakdown[
        "okx.exchange_rank_score"
    ]


def test_exchange_health_affects_selection() -> None:
    decisions, _ = select_primary_exchanges(
        [
            candidate(
                "SOLUSDT",
                ["binance", "okx"],
                exchange_scores={"binance.exchange_rank_score": 100, "okx.exchange_rank_score": 95},
            )
        ],
        exchange_health={
            "binance": {"success_rate": 0.30, "latency_ms": 2_500, "recent_failures": 4},
            "okx": {"success_rate": 0.99, "latency_ms": 100, "recent_failures": 0},
        },
        available_exchanges_per_symbol={"SOLUSDT": ["binance", "okx"]},
        decided_at=DECIDED_AT,
    )

    assert decisions["SOLUSDT"].primary_exchange == "okx"
    assert decisions["SOLUSDT"].score_breakdown["binance.exchange_stability_score"] < decisions["SOLUSDT"].score_breakdown[
        "okx.exchange_stability_score"
    ]


def test_exchange_without_kline_availability_is_not_selected() -> None:
    decisions, _ = select_primary_exchanges(
        [
            candidate(
                "DOGEUSDT",
                ["binance", "okx"],
                exchange_scores={"binance.exchange_rank_score": 100, "okx.exchange_rank_score": 70},
            )
        ],
        exchange_health={"binance": {"success_rate": 1.0, "latency_ms": 50}, "okx": {"success_rate": 0.90, "latency_ms": 100}},
        available_exchanges_per_symbol={"DOGEUSDT": ["okx"]},
        decided_at=DECIDED_AT,
    )

    assert decisions["DOGEUSDT"].primary_exchange == "okx"
    assert decisions["DOGEUSDT"].candidate_exchanges == ["okx"]


def test_kline_availability_overrides_volume() -> None:
    decisions, updated = select_primary_exchanges(
        [
            candidate(
                "BTCUSDT",
                ["binance", "okx"],
                exchange_scores={"binance.exchange_rank_score": 100, "okx.exchange_rank_score": 92},
            )
        ],
        exchange_health={
            "binance": {"success_rate": 1.0, "latency_ms": 50, "recent_failures": 0},
            "okx": {"success_rate": 1.0, "latency_ms": 60, "recent_failures": 0},
        },
        available_exchanges_per_symbol={"BTCUSDT": ["okx"]},
        decided_at=DECIDED_AT,
    )

    assert decisions["BTCUSDT"].primary_exchange == "okx"
    assert updated[0].primary_exchange == "okx"
    assert decisions["BTCUSDT"].candidate_exchanges == ["okx"]


def test_multi_exchange_selects_highest_primary_score() -> None:
    decisions, _ = select_primary_exchanges(
        [
            candidate(
                "ADAUSDT",
                ["binance", "okx", "bybit"],
                exchange_scores={
                    "binance.exchange_rank_score": 70,
                    "okx.exchange_rank_score": 80,
                    "bybit.exchange_rank_score": 95,
                },
            )
        ],
        exchange_health={
            "binance": {"success_rate": 0.95, "latency_ms": 90},
            "okx": {"success_rate": 0.95, "latency_ms": 90},
            "bybit": {"success_rate": 0.98, "latency_ms": 90},
        },
        available_exchanges_per_symbol={"ADAUSDT": ["binance", "okx", "bybit"]},
        decided_at=DECIDED_AT,
    )

    assert decisions["ADAUSDT"].primary_exchange == "bybit"
    assert decisions["ADAUSDT"].primary_score == decisions["ADAUSDT"].score_breakdown["bybit.primary_score"]


def test_no_available_exchange_returns_none_and_candidate_unfilled() -> None:
    decisions, updated = select_primary_exchanges(
        [candidate("XUSDT", ["binance", "okx"])],
        exchange_health={"binance": {"success_rate": 1.0}, "okx": {"success_rate": 1.0}},
        available_exchanges_per_symbol={"XUSDT": []},
        decided_at=DECIDED_AT,
    )

    assert decisions["XUSDT"] is None
    assert updated[0].primary_exchange is None


def test_activity_score_is_not_modified() -> None:
    original = candidate("MATICUSDT", ["binance"], activity_score=77.7)

    _, updated = select_primary_exchanges(
        [original],
        exchange_health={"binance": {"success_rate": 1.0, "latency_ms": 50}},
        available_exchanges_per_symbol={"MATICUSDT": ["binance"]},
        decided_at=DECIDED_AT,
    )

    assert updated[0].activity_score == 77.7
    assert original.activity_score == 77.7


def test_candidates_are_backfilled_with_selected_primary_exchange() -> None:
    _, updated = select_primary_exchanges(
        [candidate("BTCUSDT", ["okx"], exchange_scores={"okx.exchange_rank_score": 100})],
        exchange_health={"okx": {"source_status": "ok", "latency_ms": 50}},
        available_exchanges_per_symbol={"BTCUSDT": ["okx"]},
        decided_at=DECIDED_AT,
    )

    assert updated[0].primary_exchange == "okx"
