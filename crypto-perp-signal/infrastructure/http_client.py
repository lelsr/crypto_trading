"""HTTP client with timeout, retry, rate limit, and fallback cache."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from infrastructure.cache_store import CacheStore

try:
    import requests
    RequestException = requests.RequestException
except ModuleNotFoundError:
    requests = None  # type: ignore[assignment]
    RequestException = Exception


@dataclass(frozen=True)
class HttpResult:
    ok: bool
    status_code: int | None
    data: Any
    source_status: str
    latency_ms: int | None
    error_message: str | None = None
    from_cache: bool = False


class HttpClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 10,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 1.5,
        min_interval_seconds: float = 0.0,
        cache_store: CacheStore | None = None,
        cache_ttl_seconds: int = 300,
        session: Any | None = None,
        sleep_func: Any = time.sleep,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = max(1, retry_attempts)
        self.retry_backoff_seconds = retry_backoff_seconds
        self.min_interval_seconds = min_interval_seconds
        self.cache_store = cache_store
        self.cache_ttl_seconds = cache_ttl_seconds
        if session is None and requests is None:
            raise RuntimeError("requests is required when no HTTP session is injected")
        self.session = session or requests.Session()
        self.sleep_func = sleep_func
        self._last_request_at = 0.0

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cache_key: str | None = None,
    ) -> HttpResult:
        self._rate_limit()
        started = time.monotonic()
        last_error: str | None = None
        last_status: int | None = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                last_status = response.status_code
                latency_ms = int((time.monotonic() - started) * 1000)
                if 200 <= response.status_code < 300:
                    data = response.json()
                    if cache_key and self.cache_store:
                        self.cache_store.set(cache_key, data)
                    return HttpResult(
                        ok=True,
                        status_code=response.status_code,
                        data=data,
                        source_status="ok",
                        latency_ms=latency_ms,
                    )
                last_error = f"HTTP {response.status_code}"
                if response.status_code < 500 and response.status_code != 429:
                    break
            except (RequestException, ValueError) as exc:
                last_error = str(exc)

            if attempt < self.retry_attempts:
                self.sleep_func(self.retry_backoff_seconds * attempt)

        cached = self._fallback_cache(cache_key)
        if cached is not None:
            return HttpResult(
                ok=True,
                status_code=last_status,
                data=cached,
                source_status="stale_cache",
                latency_ms=int((time.monotonic() - started) * 1000),
                error_message=last_error,
                from_cache=True,
            )
        return HttpResult(
            ok=False,
            status_code=last_status,
            data=None,
            source_status="failed",
            latency_ms=int((time.monotonic() - started) * 1000),
            error_message=last_error,
        )

    def _fallback_cache(self, cache_key: str | None) -> Any | None:
        if not cache_key or not self.cache_store:
            return None
        entry = self.cache_store.get(cache_key, max_age_seconds=self.cache_ttl_seconds)
        return entry.value if entry else None

    def _rate_limit(self) -> None:
        if self.min_interval_seconds <= 0:
            self._last_request_at = time.monotonic()
            return
        now = time.monotonic()
        elapsed = now - self._last_request_at
        if self._last_request_at and elapsed < self.min_interval_seconds:
            self.sleep_func(self.min_interval_seconds - elapsed)
        self._last_request_at = time.monotonic()
