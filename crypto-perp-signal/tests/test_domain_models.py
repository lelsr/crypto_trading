from __future__ import annotations

from datetime import UTC, datetime

import pytest

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from models import (  # noqa: E402
    ExchangeTicker,
    IndicatorSnapshot,
    KlineBar,
    LongSignal,
    ManualReview,
    PrimaryExchangeDecision,
    SignalLifecycleRecord,
    UnifiedActivityCandidate,
)


def aware_now() -> datetime:
    return datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


def test_exchange_ticker_accepts_missing_numeric_fields() -> None:
    ticker = ExchangeTicker(
        exchange="binance_futures",
        raw_symbol="BTCUSDT",
        unified_symbol="BTCUSDT",
        quote_volume_24h_usd=None,
        base_volume_24h=None,
        last_price=None,
        price_change_pct_24h=None,
        source_status="partial",
        latency_ms=120,
        updated_at=aware_now(),
    )

    assert ticker.unified_symbol == "BTCUSDT"
    assert ticker.quote_volume_24h_usd is None


def test_timezone_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="updated_at must be timezone-aware"):
        ExchangeTicker(
            exchange="okx",
            raw_symbol="BTC-USDT-SWAP",
            unified_symbol="BTCUSDT",
            quote_volume_24h_usd=1_000_000.0,
            base_volume_24h=10.0,
            last_price=100_000.0,
            price_change_pct_24h=1.2,
            source_status="ok",
            latency_ms=90,
            updated_at=datetime(2026, 5, 5, 12, 0),
        )


def test_unified_activity_candidate_allows_unknown_market_cap() -> None:
    candidate = UnifiedActivityCandidate(
        symbol="ETHUSDT",
        exchanges=["bybit", "okx"],
        primary_exchange=None,
        activity_score=72.5,
        global_quote_volume_24h_usd=500_000_000.0,
        market_cap_usd=None,
        market_cap_status="unknown",
        source_status="partial",
        exchange_scores={"bybit": 80.0, "okx": 65.0},
    )

    assert candidate.market_cap_status == "unknown"
    assert candidate.primary_exchange is None


def test_kline_and_indicator_models_keep_primary_exchange_context() -> None:
    bar = KlineBar(
        exchange="bybit",
        symbol="SOLUSDT",
        timeframe="15m",
        open_time=aware_now(),
        open=150.0,
        high=154.0,
        low=149.0,
        close=153.0,
        volume=100_000.0,
    )
    snapshot = IndicatorSnapshot(
        exchange=bar.exchange,
        symbol=bar.symbol,
        timeframe=bar.timeframe,
        calculated_at=aware_now(),
        close=bar.close,
        ema20=151.0,
        ema60=145.0,
        macd=1.2,
        macd_signal=0.8,
        macd_histogram=0.4,
        bollinger_upper=160.0,
        bollinger_middle=150.0,
        bollinger_lower=140.0,
        volume_ma=95_000.0,
        recent_swing_low=146.0,
        support_level=145.5,
    )

    assert snapshot.exchange == "bybit"
    assert snapshot.symbol == "SOLUSDT"


def test_primary_exchange_decision_records_score_breakdown() -> None:
    decision = PrimaryExchangeDecision(
        symbol="BTCUSDT",
        primary_exchange="binance_futures",
        primary_score=91.0,
        candidate_exchanges=["binance_futures", "bybit"],
        score_breakdown={
            "24h_quote_volume_rank_score": 95.0,
            "kline_availability_score": 90.0,
            "exchange_stability_score": 85.0,
        },
        reason="highest V1 primary score",
        decided_at=aware_now(),
    )

    assert decision.primary_exchange == "binance_futures"
    assert "kline_availability_score" in decision.score_breakdown


def test_long_signal_rejects_inverted_entry_zone() -> None:
    with pytest.raises(ValueError, match="entry_zone_low must be <= entry_zone_high"):
        LongSignal(
            symbol="BTCUSDT",
            primary_exchange="bybit",
            score=80.0,
            entry_zone_low=101.0,
            entry_zone_high=100.0,
            stop_loss=95.0,
            stop_reason="1h swing low",
            timeframe_alignment={"15m": "ok", "1h": "ok", "4h": "ok"},
            reasons=["pullback reclaimed EMA20"],
            invalidation="close below support",
            created_at=aware_now(),
        )


def test_signal_lifecycle_and_manual_review_models() -> None:
    lifecycle = SignalLifecycleRecord(
        signal_id="sig-1",
        symbol="BTCUSDT",
        primary_exchange="bybit",
        status="manual_reviewed",
        entry_zone_low=100.0,
        entry_zone_high=102.0,
        stop_loss=96.0,
        max_favorable_excursion=4.5,
        max_adverse_excursion=-1.2,
        stop_touched=False,
        target_touched=True,
        duration_minutes=180,
        manual_verdict="good",
        manual_notes="clean reclaim",
        manual_tags=["ema20_reclaim", "volume_ok"],
        created_at=aware_now(),
        updated_at=aware_now(),
        reviewed_at=aware_now(),
    )
    review = ManualReview(
        review_id="review-1",
        signal_id=lifecycle.signal_id,
        manual_verdict="good",
        manual_notes="good continuation",
        manual_tags=["trend"],
        reviewed_at=aware_now(),
    )

    assert lifecycle.status == "manual_reviewed"
    assert review.signal_id == "sig-1"
