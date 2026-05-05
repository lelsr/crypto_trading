from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from application.scan_orchestrator import ScanConfig, ScanOrchestrator
from domain.models import ExchangeTicker, KlineBar, LongSignal
from infrastructure.sqlite_repo import SQLiteRepository


AS_OF = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


class FakeExchangeAdapter:
    def __init__(self, exchange: str, tickers: list[ExchangeTicker] | None = None, fail: bool = False) -> None:
        self.exchange = exchange
        self._tickers = tickers or []
        self.fail = fail
        self.health = {"source_status": "ok" if not fail else "failed", "latency_ms": 10}

    def fetch_tickers(self) -> list[ExchangeTicker]:
        if self.fail:
            raise RuntimeError("ticker failed")
        return self._tickers


class FakeMarketCapProvider:
    def fetch_market_caps(self, symbols: list[str]) -> dict[str, float]:
        return {symbol: 100_000_000 for symbol in symbols}


class FakeKlineProvider:
    def __init__(self, available: dict[str, list[str]]) -> None:
        self.available = available
        self.plans = []

    def available_exchanges_per_symbol(self, symbols: list[str]) -> dict[str, list[str]]:
        return {symbol: self.available.get(symbol, []) for symbol in symbols}

    def fetch_klines(self, plan):
        self.plans.append(plan)
        return make_bars(plan.symbol, plan.primary_exchange, plan.timeframe, 120)


class NotifyResult:
    def __init__(self, status: str, reason: str) -> None:
        self.status = status
        self.reason = reason


def ticker(exchange: str, symbol: str, volume: float) -> ExchangeTicker:
    return ExchangeTicker(
        exchange=exchange,
        raw_symbol=symbol,
        unified_symbol=symbol,
        quote_volume_24h_usd=volume,
        base_volume_24h=volume / 100,
        last_price=100.0,
        price_change_pct_24h=1.0,
        source_status="ok",
        latency_ms=10,
        updated_at=AS_OF,
    )


def make_bars(symbol: str, exchange: str, timeframe: str, count: int) -> list[KlineBar]:
    minutes = {"15m": 15, "1h": 60, "4h": 240}[timeframe]
    start = AS_OF - timedelta(minutes=minutes * (count + 2))
    return [
        KlineBar(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            open_time=start + timedelta(minutes=minutes * index),
            open=100 + index * 0.01,
            high=101 + index * 0.01,
            low=99 + index * 0.01,
            close=100 + index * 0.01,
            volume=1000 + index,
        )
        for index in range(count)
    ]


def make_signal(symbol: str, level: str) -> LongSignal:
    return LongSignal(
        symbol=symbol,
        primary_exchange="okx",
        score=86.0 if level in {"A", "B"} else 72.0,
        entry_zone_low=100.0,
        entry_zone_high=102.0,
        stop_loss=96.0,
        stop_reason="4h support minus 0.3% buffer",
        timeframe_alignment={"15m": "ok", "1h": "ok", "4h": "ok"},
        reasons=[f"signal_level:{level}"],
        invalidation="15m close below stop_loss",
        created_at=AS_OF,
    )


def orchestrator(tmp_path: Path, *, kline_provider: FakeKlineProvider, notifier, final_top_m: int = 2) -> ScanOrchestrator:
    repo = SQLiteRepository(tmp_path / "signals.db")
    return ScanOrchestrator(
        repository=repo,
        exchange_adapters=[
            FakeExchangeAdapter("badex", fail=True),
            FakeExchangeAdapter("okx", [ticker("okx", "BTCUSDT", 1_000_000), ticker("okx", "ETHUSDT", 900_000)]),
        ],
        market_cap_provider=FakeMarketCapProvider(),
        kline_provider=kline_provider,
        notifier=notifier,
        config=ScanConfig(final_top_m=final_top_m, report_dir=tmp_path / "reports"),
    )


def test_single_exchange_failure_does_not_fail_scan_and_ab_signal_notifies(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_generate(analysis, *, analysis_anchor_time):
        class Decision:
            signal = make_signal(analysis.symbol, "A")
        return Decision()

    def fake_notify(signal, *, dashboard_url):
        calls.append(signal.symbol)
        return NotifyResult("sent", "ok")

    monkeypatch.setattr("application.scan_orchestrator.generate_long_signal_v1", fake_generate)
    kline_provider = FakeKlineProvider({"BTCUSDT": ["okx"], "ETHUSDT": ["okx"]})
    result = orchestrator(tmp_path, kline_provider=kline_provider, notifier=fake_notify).run_once(as_of=AS_OF)

    assert result.status == "completed"
    assert result.failed_exchanges == ["badex"]
    assert result.signal_count == 2
    assert calls == ["BTCUSDT", "ETHUSDT"]
    assert result.report.path.exists()


def test_no_signal_still_completes_scan(monkeypatch, tmp_path: Path) -> None:
    def fake_generate(analysis, *, analysis_anchor_time):
        class Decision:
            signal = None
        return Decision()

    monkeypatch.setattr("application.scan_orchestrator.generate_long_signal_v1", fake_generate)
    result = orchestrator(
        tmp_path,
        kline_provider=FakeKlineProvider({"BTCUSDT": ["okx"], "ETHUSDT": ["okx"]}),
        notifier=lambda signal, *, dashboard_url: NotifyResult("sent", "ok"),
    ).run_once(as_of=AS_OF)

    assert result.status == "completed"
    assert result.signal_count == 0
    assert set(result.skipped_symbols) == {"BTCUSDT", "ETHUSDT"}


def test_c_signal_does_not_push_when_notifier_skips(monkeypatch, tmp_path: Path) -> None:
    results = []

    def fake_generate(analysis, *, analysis_anchor_time):
        class Decision:
            signal = make_signal(analysis.symbol, "C")
        return Decision()

    def fake_notify(signal, *, dashboard_url):
        results.append(signal.reasons[0])
        return NotifyResult("skipped", "signal_level_not_pushable")

    monkeypatch.setattr("application.scan_orchestrator.generate_long_signal_v1", fake_generate)
    result = orchestrator(
        tmp_path,
        kline_provider=FakeKlineProvider({"BTCUSDT": ["okx"], "ETHUSDT": ["okx"]}),
        notifier=fake_notify,
        final_top_m=1,
    ).run_once(as_of=AS_OF)

    assert result.signal_count == 1
    assert results == ["signal_level:C"]
    assert result.notification_results[0]["status"] == "skipped"


def test_kline_plan_only_final_top_m_and_skips_missing_primary(monkeypatch, tmp_path: Path) -> None:
    def fake_generate(analysis, *, analysis_anchor_time):
        class Decision:
            signal = None
        return Decision()

    monkeypatch.setattr("application.scan_orchestrator.generate_long_signal_v1", fake_generate)
    kline_provider = FakeKlineProvider({"BTCUSDT": ["okx"]})
    result = orchestrator(tmp_path, kline_provider=kline_provider, notifier=lambda signal, *, dashboard_url: NotifyResult("sent", "ok")).run_once(as_of=AS_OF)

    assert {plan.symbol for plan in result.kline_plans} == {"BTCUSDT"}
    assert all(plan.primary_exchange == "okx" for plan in result.kline_plans)
    assert len(result.kline_plans) == 3
    assert "ETHUSDT" in result.skipped_symbols
