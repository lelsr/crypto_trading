from __future__ import annotations

from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.cache_store import CacheStore
from infrastructure.http_client import HttpClient


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = responses
        self.calls = 0

    def get(self, *args: object, **kwargs: object) -> FakeResponse:
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_http_client_success_writes_cache(tmp_path: Path) -> None:
    cache = CacheStore(tmp_path)
    session = FakeSession([FakeResponse(200, {"ok": True})])
    client = HttpClient(
        timeout_seconds=1,
        retry_attempts=1,
        cache_store=cache,
        session=session,
        sleep_func=lambda seconds: None,
    )

    result = client.get_json("https://example.test", cache_key="key")

    assert result.ok is True
    assert result.source_status == "ok"
    assert cache.get("key") is not None


def test_http_client_retries_5xx_then_succeeds() -> None:
    session = FakeSession([FakeResponse(500, {"error": "bad"}), FakeResponse(200, {"ok": True})])
    client = HttpClient(
        timeout_seconds=1,
        retry_attempts=2,
        session=session,
        sleep_func=lambda seconds: None,
    )

    result = client.get_json("https://example.test")

    assert result.ok is True
    assert session.calls == 2


def test_http_client_uses_fallback_cache_on_failure(tmp_path: Path) -> None:
    cache = CacheStore(tmp_path)
    cache.set("fallback", {"cached": True})
    session = FakeSession([FakeResponse(503, {"error": "down"})])
    client = HttpClient(
        timeout_seconds=1,
        retry_attempts=1,
        cache_store=cache,
        session=session,
        sleep_func=lambda seconds: None,
    )

    result = client.get_json("https://example.test", cache_key="fallback")

    assert result.ok is True
    assert result.source_status == "stale_cache"
    assert result.from_cache is True
    assert result.data == {"cached": True}


def test_http_client_failure_without_cache_is_structured() -> None:
    session = FakeSession([FakeResponse(400, {"error": "bad request"})])
    client = HttpClient(
        timeout_seconds=1,
        retry_attempts=3,
        session=session,
        sleep_func=lambda seconds: None,
    )

    result = client.get_json("https://example.test")

    assert result.ok is False
    assert result.source_status == "failed"
    assert result.status_code == 400
    assert session.calls == 1


def test_http_client_applies_simple_rate_limit() -> None:
    sleeps: list[float] = []
    session = FakeSession([FakeResponse(200, {"a": 1}), FakeResponse(200, {"b": 2})])
    client = HttpClient(
        timeout_seconds=1,
        retry_attempts=1,
        min_interval_seconds=1,
        session=session,
        sleep_func=sleeps.append,
    )

    client.get_json("https://example.test/a")
    client.get_json("https://example.test/b")

    assert sleeps
