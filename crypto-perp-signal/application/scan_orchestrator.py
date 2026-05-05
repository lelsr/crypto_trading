"""Scan orchestration for one local signal scan cycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.feishu_notify import notify_signal
from application.report_service import ScanReport, write_scan_report
from domain.activity_ranker import rank_activity_candidates
from domain.events import ScanEvent
from domain.kline_policy import KlineFetchPlan, build_kline_fetch_plan
from domain.long_signal_v1 import generate_long_signal_v1
from domain.market_cap_filter import MarketCapFilterConfig, apply_market_cap_filter
from domain.primary_exchange_selector import select_primary_exchanges
from domain.structure_analyzer import analyze_structure


@dataclass(frozen=True)
class ScanConfig:
    preselect_top_n_per_exchange: int = 300
    final_top_m: int = 80
    timeframes: tuple[str, ...] = ("15m", "1h", "4h")
    kline_limit: int = 200
    report_dir: str | Path = "data/reports"
    market_cap_filter: MarketCapFilterConfig = MarketCapFilterConfig()
    dashboard_url: str = "http://localhost:8501"


@dataclass(frozen=True)
class ScanResult:
    scan_id: str
    status: str
    candidate_count: int
    signal_count: int
    failed_exchanges: list[str]
    skipped_symbols: list[str]
    notification_results: list[dict]
    report: ScanReport
    kline_plans: list[KlineFetchPlan]


class ScanOrchestrator:
    def __init__(
        self,
        *,
        repository: Any,
        exchange_adapters: list[Any],
        market_cap_provider: Any,
        kline_provider: Any,
        notifier: Any = notify_signal,
        config: ScanConfig | None = None,
    ) -> None:
        self.repository = repository
        self.exchange_adapters = exchange_adapters
        self.market_cap_provider = market_cap_provider
        self.kline_provider = kline_provider
        self.notifier = notifier
        self.config = config or ScanConfig()

    def run_once(self, *, as_of: datetime | None = None) -> ScanResult:
        as_of = as_of or datetime.now(UTC)
        scan_id = self.repository.create_scan_run(started_at=as_of)
        self._event(scan_id, "ScanStarted", "started", "scan started", {"config": self._config_payload()})
        failed_exchanges: list[str] = []
        skipped_symbols: list[str] = []
        notification_results: list[dict] = []
        signals = []

        try:
            tickers = []
            for adapter in self.exchange_adapters:
                try:
                    tickers.extend(adapter.fetch_tickers())
                    self._event(scan_id, "TickerFetched", "ok", f"{adapter.exchange} tickers fetched", {"exchange": adapter.exchange})
                except Exception as exc:
                    failed_exchanges.append(adapter.exchange)
                    self._event(scan_id, "TickerFetched", "failed", str(exc), {"exchange": adapter.exchange})

            candidates = rank_activity_candidates(
                tickers,
                preselect_top_n_per_exchange=self.config.preselect_top_n_per_exchange,
            )
            self._event(scan_id, "CandidatePoolBuilt", "ok", "candidate pool built", {"candidate_count": len(candidates)})

            market_caps = self.market_cap_provider.fetch_market_caps([candidate.symbol for candidate in candidates])
            filtered = apply_market_cap_filter(candidates, market_caps, self.config.market_cap_filter)
            final_candidates = filtered[: self.config.final_top_m]
            self._event(scan_id, "CandidatesFiltered", "ok", "candidates filtered", {"candidate_count": len(final_candidates)})

            exchange_health = {
                adapter.exchange: getattr(adapter, "health", {"source_status": "ok", "latency_ms": 0})
                for adapter in self.exchange_adapters
            }
            available = self.kline_provider.available_exchanges_per_symbol([candidate.symbol for candidate in final_candidates])
            _, final_with_primary = select_primary_exchanges(
                final_candidates,
                exchange_health=exchange_health,
                available_exchanges_per_symbol=available,
                decided_at=as_of,
            )
            self._event(scan_id, "PrimaryExchangeSelected", "ok", "primary exchanges selected", {})

            final_symbols = {candidate.symbol for candidate in final_with_primary}
            kline_plans = build_kline_fetch_plan(
                final_with_primary,
                final_top_m_symbols=final_symbols,
                timeframes=list(self.config.timeframes),
                limit=self.config.kline_limit,
            )

            planned_symbols = {plan.symbol for plan in kline_plans}
            for candidate in final_with_primary:
                if candidate.symbol not in planned_symbols:
                    skipped_symbols.append(candidate.symbol)

            for candidate in final_with_primary:
                if not candidate.primary_exchange:
                    continue
                symbol_plans = [plan for plan in kline_plans if plan.symbol == candidate.symbol]
                if not symbol_plans:
                    continue
                bars_by_timeframe = {
                    plan.timeframe: self.kline_provider.fetch_klines(plan)
                    for plan in symbol_plans
                }
                analysis = analyze_structure(
                    symbol=candidate.symbol,
                    primary_exchange=candidate.primary_exchange,
                    bars_by_timeframe=bars_by_timeframe,
                    as_of=as_of,
                )
                decision = generate_long_signal_v1(analysis, analysis_anchor_time=as_of)
                if decision.signal is None:
                    skipped_symbols.append(candidate.symbol)
                    continue
                signal_id = self.repository.insert_signal(scan_id=scan_id, signal=decision.signal)
                self.repository.insert_signal_tracking(signal_id=signal_id, status="created", updated_at=as_of)
                signals.append(decision.signal)
                notify_result = self.notifier(decision.signal, dashboard_url=self.config.dashboard_url)
                notification_results.append(
                    {
                        "symbol": decision.signal.symbol,
                        "status": getattr(notify_result, "status", "unknown"),
                        "reason": getattr(notify_result, "reason", "unknown"),
                    }
                )

            status = "completed"
            report = write_scan_report(
                report_dir=self.config.report_dir,
                scan_id=scan_id,
                candidate_count=len(final_candidates),
                signal_count=len(signals),
                failed_exchanges=failed_exchanges,
                skipped_symbols=sorted(set(skipped_symbols)),
                notification_results=notification_results,
            )
            self.repository.complete_scan_run(
                scan_id=scan_id,
                status=status,
                completed_at=as_of,
                summary={"signals": len(signals), "failed_exchanges": failed_exchanges},
            )
            self._event(scan_id, "ScanCompleted", "ok", "scan completed", {"signal_count": len(signals)})
            return ScanResult(
                scan_id=scan_id,
                status=status,
                candidate_count=len(final_candidates),
                signal_count=len(signals),
                failed_exchanges=failed_exchanges,
                skipped_symbols=sorted(set(skipped_symbols)),
                notification_results=notification_results,
                report=report,
                kline_plans=kline_plans,
            )
        except Exception as exc:
            report = write_scan_report(
                report_dir=self.config.report_dir,
                scan_id=scan_id,
                candidate_count=0,
                signal_count=0,
                failed_exchanges=failed_exchanges,
                skipped_symbols=skipped_symbols,
                notification_results=notification_results,
            )
            self.repository.complete_scan_run(scan_id=scan_id, status="failed", completed_at=as_of, error_message=str(exc))
            self._event(scan_id, "ScanFailed", "failed", str(exc), {})
            raise

    def _event(self, scan_id: str, event_type: str, status: str, message: str, payload: dict) -> None:
        event = ScanEvent.from_payload(
            scan_id=scan_id,
            event_type=event_type,
            timestamp=datetime.now(UTC),
            status=status,
            message=message,
            payload=payload,
        )
        self.repository.insert_event(event)

    def _config_payload(self) -> dict[str, Any]:
        return {
            "preselect_top_n_per_exchange": self.config.preselect_top_n_per_exchange,
            "final_top_m": self.config.final_top_m,
            "timeframes": list(self.config.timeframes),
            "kline_limit": self.config.kline_limit,
            "report_dir": str(self.config.report_dir),
            "market_cap_filter": asdict(self.config.market_cap_filter),
            "dashboard_url": self.config.dashboard_url,
        }
