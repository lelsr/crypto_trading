"""CLI entrypoint for manual or looped scan cycles."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "domain") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "domain"))

import yaml

from app.scheduler import LoopScheduler
from application.scan_orchestrator import ScanConfig, ScanOrchestrator
from domain.market_cap_filter import MarketCapFilterConfig
from infrastructure.cache_store import CacheStore
from infrastructure.exchanges.binance_futures import BinanceFuturesAdapter
from infrastructure.exchanges.coingecko import CoinGeckoAdapter
from infrastructure.exchanges.okx import OKXAdapter
from infrastructure.http_client import HttpClient
from infrastructure.kline_provider import KlineProvider
from infrastructure.sqlite_repo import SQLiteRepository


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        env_path = PROJECT_ROOT / ".env.local"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


def _load_settings(config_path: str | Path | None = None) -> dict[str, Any]:
    if config_path is None:
        config_path = PROJECT_ROOT / "config" / "settings.yaml"
    path = Path(config_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _load_coin_id_map() -> dict[str, str]:
    map_path = PROJECT_ROOT / "config" / "coin_id_map.yaml"
    if not map_path.exists():
        return {}
    with map_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class MarketCapBridge:
    """Maps unified symbols (BTCUSDT) to CoinGecko coin IDs (bitcoin)."""

    def __init__(self, coin_id_map: dict[str, str], coingecko: CoinGeckoAdapter) -> None:
        self._map = {k.lower(): v for k, v in coin_id_map.items()}
        self._coingecko = coingecko

    def fetch_market_caps(self, symbols: list[str]) -> dict[str, float | None]:
        symbol_to_coin_id: dict[str, str | None] = {}
        coin_ids: list[str] = []
        for symbol in symbols:
            cid = self._map.get(symbol.lower())
            symbol_to_coin_id[symbol] = cid
            if cid:
                coin_ids.append(cid)

        coin_id_results = self._coingecko.fetch_market_caps(coin_ids)

        results: dict[str, float | None] = {}
        for symbol in symbols:
            cid = symbol_to_coin_id.get(symbol)
            if cid:
                results[symbol] = coin_id_results.get(cid)
            else:
                results[symbol] = None
        return results


def build_orchestrator(config_path: str | Path | None = None) -> ScanOrchestrator:
    _load_env()
    settings = _load_settings(config_path)

    storage = settings.get("storage", {})
    stability = settings.get("stability", {})
    perf = settings.get("performance_budget", {})
    universe = settings.get("universe", {})
    klines_cfg = settings.get("klines", {})
    mcap_cfg = settings.get("market_cap_filter", {})
    feishu_cfg = settings.get("feishu", {})

    db_path = PROJECT_ROOT / storage.get("sqlite_path", "data/signals.db")
    cache_dir = PROJECT_ROOT / storage.get("cache_dir", "data/cache")
    report_dir = PROJECT_ROOT / storage.get("report_dir", "data/reports")

    http = HttpClient(
        timeout_seconds=stability.get("request_timeout_seconds", 10),
        retry_attempts=stability.get("retry_attempts", 3),
        retry_backoff_seconds=stability.get("retry_backoff_seconds", 1.5),
        cache_store=CacheStore(cache_dir),
        cache_ttl_seconds=300,
    )

    adapters = [
        BinanceFuturesAdapter(http),
        OKXAdapter(http),
    ]

    coin_id_map = _load_coin_id_map()
    coingecko = CoinGeckoAdapter(http)
    market_cap_provider = MarketCapBridge(coin_id_map, coingecko)

    kline_provider = KlineProvider(adapters)
    repository = SQLiteRepository(db_path)

    config = ScanConfig(
        preselect_top_n_per_exchange=universe.get("preselect_top_n_per_exchange", 300),
        final_top_m=universe.get("final_top_m_after_market_cap", 80),
        timeframes=tuple(klines_cfg.get("timeframes", ["15m", "1h", "4h"])),
        kline_limit=klines_cfg.get("limit", 200),
        report_dir=str(report_dir),
        market_cap_filter=MarketCapFilterConfig(
            enabled=mcap_cfg.get("enabled", True),
            min_market_cap=mcap_cfg.get("min_market_cap", 50_000_000),
            max_market_cap=mcap_cfg.get("max_market_cap", 5_000_000_000),
            keep_unknown_market_cap=mcap_cfg.get("keep_unknown_market_cap", True),
        ),
        dashboard_url=feishu_cfg.get("dashboard_local_url", "http://localhost:8501"),
    )

    return ScanOrchestrator(
        repository=repository,
        exchange_adapters=adapters,
        market_cap_provider=market_cap_provider,
        kline_provider=kline_provider,
        config=config,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run crypto perp signal scan cycle")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="run one scan cycle")
    mode.add_argument("--loop", action="store_true", help="run scan cycles continuously")
    parser.add_argument("--config", default="config/settings.yaml", help="path to settings yaml")
    parser.add_argument("--loop-minutes", type=int, default=38, help="loop interval in minutes")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, orchestrator: Any | None = None) -> int:
    args = parse_args(argv)
    if orchestrator is None:
        orchestrator = build_orchestrator(config_path=args.config)

    scheduler = LoopScheduler(orchestrator=orchestrator, loop_minutes=args.loop_minutes)
    if args.once:
        scheduler.run_once()
        return 0
    scheduler.run_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
