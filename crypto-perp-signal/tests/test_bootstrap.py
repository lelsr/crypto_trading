from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_cycle import MarketCapBridge


class FakeCoinGecko:
    def __init__(self, caps: dict[str, float | None]) -> None:
        self._caps = caps
        self.calls: list[list[str]] = []

    def fetch_market_caps(self, coin_ids: list[str]) -> dict[str, float | None]:
        self.calls.append(coin_ids)
        return {cid: self._caps.get(cid) for cid in coin_ids}


def test_market_cap_bridge_maps_symbols_to_coin_ids() -> None:
    coingecko = FakeCoinGecko({"bitcoin": 500_000_000_000, "ethereum": 200_000_000_000})
    bridge = MarketCapBridge({"btcusdt": "bitcoin", "ethusdt": "ethereum"}, coingecko)

    result = bridge.fetch_market_caps(["BTCUSDT", "ETHUSDT"])
    assert result == {"BTCUSDT": 500_000_000_000, "ETHUSDT": 200_000_000_000}


def test_market_cap_bridge_case_insensitive() -> None:
    coingecko = FakeCoinGecko({"bitcoin": 500_000_000_000})
    bridge = MarketCapBridge({"BTCUSDT": "bitcoin"}, coingecko)

    result = bridge.fetch_market_caps(["btcusdt"])
    assert result == {"btcusdt": 500_000_000_000}


def test_market_cap_bridge_unknown_symbol_returns_none() -> None:
    coingecko = FakeCoinGecko({"bitcoin": 500_000_000_000})
    bridge = MarketCapBridge({"btcusdt": "bitcoin"}, coingecko)

    result = bridge.fetch_market_caps(["BTCUSDT", "UNKNOWNSYMBOL"])
    assert result == {"BTCUSDT": 500_000_000_000, "UNKNOWNSYMBOL": None}


def test_market_cap_bridge_coingecko_failure_does_not_crash() -> None:
    coingecko = FakeCoinGecko({"bitcoin": 500_000_000_000})
    bridge = MarketCapBridge({"btcusdt": "bitcoin"}, coingecko)

    result = bridge.fetch_market_caps(["UNKNOWNSYMBOL"])
    assert result == {"UNKNOWNSYMBOL": None}


def test_market_cap_bridge_empty_symbols() -> None:
    coingecko = FakeCoinGecko({})
    bridge = MarketCapBridge({}, coingecko)

    result = bridge.fetch_market_caps([])
    assert result == {}


def test_build_orchestrator_constructs_without_error() -> None:
    from scripts.run_cycle import build_orchestrator
    orchestrator = build_orchestrator()
    assert orchestrator is not None
    assert len(orchestrator.exchange_adapters) == 2
    assert orchestrator.exchange_adapters[0].exchange == "binance_futures"
    assert orchestrator.exchange_adapters[1].exchange == "okx"
    assert orchestrator.repository is not None
    assert orchestrator.kline_provider is not None
    assert orchestrator.market_cap_provider is not None
    assert orchestrator.config.final_top_m == 80
