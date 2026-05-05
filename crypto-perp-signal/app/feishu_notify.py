"""Feishu webhook notification helpers for generated signals."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass(frozen=True)
class FeishuNotifyResult:
    status: str
    reason: str
    signal_level: str | None = None
    http_status: int | None = None


def notify_signal(
    signal: Any,
    *,
    dashboard_url: str = "http://localhost:8501",
    env: dict[str, str] | None = None,
    post_func: Any | None = None,
    timeout_seconds: float = 10.0,
) -> FeishuNotifyResult:
    env = env or os.environ
    enabled = _env_enabled(env.get("ENABLE_FEISHU", "true"))
    webhook_url = env.get("FEISHU_WEBHOOK_URL", "").strip()
    signal_level = extract_signal_level(signal)

    if not enabled:
        return FeishuNotifyResult(status="skipped", reason="disabled", signal_level=signal_level)
    if not webhook_url:
        return FeishuNotifyResult(status="skipped", reason="empty_webhook", signal_level=signal_level)
    if signal_level not in {"A", "B"}:
        return FeishuNotifyResult(status="skipped", reason="signal_level_not_pushable", signal_level=signal_level)

    payload = build_signal_message(signal, dashboard_url=dashboard_url, signal_level=signal_level)
    if post_func is None:
        import requests

        post = requests.post
    else:
        post = post_func
    try:
        response = post(webhook_url, json=payload, timeout=timeout_seconds)
    except Exception as exc:  # requests failures must not break scan flow.
        return FeishuNotifyResult(status="failed", reason=str(exc), signal_level=signal_level)

    status_code = getattr(response, "status_code", None)
    if status_code is not None and 200 <= status_code < 300:
        return FeishuNotifyResult(status="sent", reason="ok", signal_level=signal_level, http_status=status_code)
    return FeishuNotifyResult(
        status="failed",
        reason=f"http_status:{status_code}",
        signal_level=signal_level,
        http_status=status_code,
    )


def build_signal_message(signal: Any, *, dashboard_url: str, signal_level: str | None = None) -> dict[str, Any]:
    signal_level = signal_level or extract_signal_level(signal) or "unknown"
    lines = [
        f"Signal Level: {signal_level}",
        f"Symbol: {signal.symbol}",
        f"Primary Exchange: {signal.primary_exchange}",
        f"Score: {signal.score}",
        f"Entry Zone: {signal.entry_zone_low} - {signal.entry_zone_high}",
        f"Stop Loss: {signal.stop_loss}",
        f"Stop Reason: {signal.stop_reason}",
        f"Invalidation: {signal.invalidation}",
        f"Dashboard: {dashboard_url}",
        "Reasons:",
        *[f"- {reason}" for reason in signal.reasons],
    ]
    return {
        "msg_type": "text",
        "content": {
            "text": "\n".join(lines),
        },
    }


def extract_signal_level(signal: Any) -> str | None:
    for reason in getattr(signal, "reasons", []):
        if isinstance(reason, str) and reason.startswith("signal_level:"):
            return reason.split(":", 1)[1]
    return None


def _env_enabled(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}
