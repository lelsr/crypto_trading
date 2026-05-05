"""Support and resistance helpers for primary-exchange klines."""

from __future__ import annotations

from dataclasses import dataclass

from models import KlineBar


@dataclass(frozen=True)
class SwingLow:
    price: float
    index: int


@dataclass(frozen=True)
class SupportLevel:
    price: float | None
    support_score: float
    support_status: str
    touch_count: int


def find_recent_swing_low(
    bars: list[KlineBar],
    *,
    left: int = 2,
    right: int = 2,
) -> SwingLow | None:
    swings = find_swing_lows(bars, left=left, right=right)
    return swings[-1] if swings else None


def find_swing_lows(
    bars: list[KlineBar],
    *,
    left: int = 2,
    right: int = 2,
) -> list[SwingLow]:
    sorted_bars = sorted(bars, key=lambda bar: bar.open_time)
    if len(sorted_bars) < left + right + 1:
        return []
    swings: list[SwingLow] = []
    for index in range(left, len(sorted_bars) - right):
        low = sorted_bars[index].low
        left_lows = [bar.low for bar in sorted_bars[index - left:index]]
        right_lows = [bar.low for bar in sorted_bars[index + 1:index + right + 1]]
        if all(low <= value for value in left_lows) and all(low <= value for value in right_lows):
            swings.append(SwingLow(price=low, index=index))
    return swings


def identify_support_level(
    bars: list[KlineBar],
    *,
    lookback: int = 120,
    tolerance_pct: float = 0.005,
) -> SupportLevel:
    if not bars:
        return SupportLevel(price=None, support_score=0.0, support_status="missing", touch_count=0)
    recent_bars = sorted(bars, key=lambda bar: bar.open_time)[-lookback:]
    current_price = recent_bars[-1].close
    swings = [swing for swing in find_swing_lows(recent_bars) if swing.price < current_price]
    if not swings:
        recent = find_recent_swing_low(recent_bars)
        if recent is None:
            return SupportLevel(price=None, support_score=0.0, support_status="missing", touch_count=0)
        return SupportLevel(price=recent.price, support_score=10.0, support_status="weak", touch_count=1)

    clusters = _cluster_swings(swings, tolerance_pct=tolerance_pct)
    scored = [_score_cluster(cluster, recent_bars) for cluster in clusters]
    below_price = [level for level in scored if level.price is not None and level.price < current_price]
    if not below_price:
        return SupportLevel(price=swings[-1].price, support_score=10.0, support_status="weak", touch_count=1)
    return sorted(below_price, key=lambda level: (abs(current_price - (level.price or 0)), -level.support_score))[0]


def _cluster_swings(swings: list[SwingLow], *, tolerance_pct: float) -> list[list[SwingLow]]:
    clusters: list[list[SwingLow]] = []
    for swing in swings:
        placed = False
        for cluster in clusters:
            center = sum(item.price for item in cluster) / len(cluster)
            if abs(swing.price - center) / center <= tolerance_pct:
                cluster.append(swing)
                placed = True
                break
        if not placed:
            clusters.append([swing])
    return clusters


def _score_cluster(cluster: list[SwingLow], bars: list[KlineBar]) -> SupportLevel:
    touch_count = len(cluster)
    price = sum(item.price for item in cluster) / touch_count
    touch_count_score = min(touch_count / 5, 1.0) * 100
    latest_index = max(item.index for item in cluster)
    recency_score = (latest_index + 1) / len(bars) * 100
    max_volume = max((bar.volume for bar in bars), default=0.0)
    avg_touch_volume = sum(bars[item.index].volume for item in cluster) / touch_count
    volume_score = (avg_touch_volume / max_volume * 100) if max_volume > 0 else 0.0
    support_score = touch_count_score * 0.50 + recency_score * 0.30 + volume_score * 0.20
    return SupportLevel(
        price=price,
        support_score=round(support_score, 6),
        support_status="strong" if touch_count >= 2 else "weak",
        touch_count=touch_count,
    )
