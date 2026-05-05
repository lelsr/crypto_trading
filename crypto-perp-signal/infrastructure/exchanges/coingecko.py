"""CoinGecko market cap adapter."""

from __future__ import annotations

from infrastructure.http_client import HttpClient


class CoinGeckoAdapter:
    source = "coingecko"
    base_url = "https://api.coingecko.com/api/v3"

    def __init__(self, http_client: HttpClient) -> None:
        self.http_client = http_client
        self.last_source_status = "skipped"
        self.last_latency_ms: int | None = None

    def fetch_market_caps(self, coin_ids: list[str], *, vs_currency: str = "usd") -> dict[str, float | None]:
        if not coin_ids:
            return {}
        result = self.http_client.get_json(
            f"{self.base_url}/coins/markets",
            params={
                "vs_currency": vs_currency,
                "ids": ",".join(coin_ids),
                "order": "market_cap_desc",
                "per_page": len(coin_ids),
                "page": 1,
                "sparkline": "false",
            },
            cache_key=f"{self.source}:market_caps:{vs_currency}:{','.join(sorted(coin_ids))}",
        )
        self.last_source_status = result.source_status
        self.last_latency_ms = result.latency_ms
        if not result.ok or not isinstance(result.data, list):
            return {coin_id: None for coin_id in coin_ids}
        caps = {coin_id: None for coin_id in coin_ids}
        for item in result.data:
            coin_id = item.get("id")
            if coin_id in caps:
                market_cap = item.get("market_cap")
                caps[coin_id] = float(market_cap) if market_cap is not None else None
        return caps
