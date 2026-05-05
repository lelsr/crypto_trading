from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "domain"))

from app.feishu_notify import build_signal_message, notify_signal  # noqa: E402
from domain.models import LongSignal  # noqa: E402


def signal(level: str) -> LongSignal:
    return LongSignal(
        symbol="BTCUSDT",
        primary_exchange="okx",
        score=86.0,
        entry_zone_low=100.0,
        entry_zone_high=102.0,
        stop_loss=96.0,
        stop_reason="4h support minus 0.3% buffer",
        timeframe_alignment={"15m": "ok", "1h": "ok", "4h": "ok"},
        reasons=[f"signal_level:{level}", "rr:3.0"],
        invalidation="15m close below stop_loss",
        created_at=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),
    )


class Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_feishu_disabled_safely_skips() -> None:
    calls = []

    result = notify_signal(
        signal("A"),
        env={"ENABLE_FEISHU": "false", "FEISHU_WEBHOOK_URL": "https://example.invalid"},
        post_func=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert result.status == "skipped"
    assert result.reason == "disabled"
    assert calls == []


def test_feishu_empty_webhook_safely_skips() -> None:
    result = notify_signal(
        signal("A"),
        env={"ENABLE_FEISHU": "true", "FEISHU_WEBHOOK_URL": ""},
        post_func=lambda *args, **kwargs: Response(200),
    )

    assert result.status == "skipped"
    assert result.reason == "empty_webhook"


def test_feishu_pushes_a_and_b_but_skips_c() -> None:
    calls = []

    def post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return Response(200)

    result_a = notify_signal(signal("A"), env={"ENABLE_FEISHU": "true", "FEISHU_WEBHOOK_URL": "https://feishu"}, post_func=post)
    result_b = notify_signal(signal("B"), env={"ENABLE_FEISHU": "true", "FEISHU_WEBHOOK_URL": "https://feishu"}, post_func=post)
    result_c = notify_signal(signal("C"), env={"ENABLE_FEISHU": "true", "FEISHU_WEBHOOK_URL": "https://feishu"}, post_func=post)

    assert result_a.status == "sent"
    assert result_b.status == "sent"
    assert result_c.status == "skipped"
    assert result_c.reason == "signal_level_not_pushable"
    assert len(calls) == 2


def test_feishu_request_failure_returns_failed_without_raising() -> None:
    def broken_post(*args, **kwargs):
        raise RuntimeError("network down")

    result = notify_signal(
        signal("A"),
        env={"ENABLE_FEISHU": "true", "FEISHU_WEBHOOK_URL": "https://feishu"},
        post_func=broken_post,
    )

    assert result.status == "failed"
    assert "network down" in result.reason


def test_feishu_message_contains_signal_details() -> None:
    payload = build_signal_message(signal("B"), dashboard_url="http://localhost:8501")

    text = payload["content"]["text"]
    assert payload["msg_type"] == "text"
    assert "Signal Level: B" in text
    assert "BTCUSDT" in text
    assert "Entry Zone: 100.0 - 102.0" in text
