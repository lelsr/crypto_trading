"""Technical indicator calculations for primary-exchange klines."""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import pstdev

from models import IndicatorSnapshot, KlineBar

MIN_EMA20_BARS = 50
MIN_MACD_BARS = 100


def calculate_indicator_snapshot(
    bars: list[KlineBar],
    *,
    primary_exchange: str,
    timeframe: str,
    calculated_at: datetime | None = None,
) -> IndicatorSnapshot | None:
    if not bars:
        return None
    sorted_bars = sorted(bars, key=lambda bar: bar.open_time)
    symbol = sorted_bars[-1].symbol
    if any(bar.exchange != primary_exchange for bar in sorted_bars):
        raise ValueError("indicator input contains non-primary exchange kline")
    if any(bar.symbol != symbol for bar in sorted_bars):
        raise ValueError("indicator input contains mixed symbols")

    closes = [bar.close for bar in sorted_bars]
    volumes = [bar.volume for bar in sorted_bars]
    macd_value, macd_signal, macd_histogram = macd(closes)
    bb_upper, bb_middle, bb_lower = bollinger_bands(closes)
    return IndicatorSnapshot(
        exchange=primary_exchange,
        symbol=symbol,
        timeframe=timeframe,
        calculated_at=calculated_at or datetime.now(UTC),
        close=closes[-1],
        ema20=ema_last(closes, 20),
        ema60=ema_last(closes, 60),
        macd=macd_value,
        macd_signal=macd_signal,
        macd_histogram=macd_histogram,
        bollinger_upper=bb_upper,
        bollinger_middle=bb_middle,
        bollinger_lower=bb_lower,
        volume_ma=sma_last(volumes, 20),
        recent_swing_low=None,
        support_level=None,
    )


def sma_last(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values: list[float], period: int) -> list[float | None]:
    min_bars = MIN_EMA20_BARS if period == 20 else period
    if len(values) < min_bars:
        return [None] * len(values)
    alpha = 2 / (period + 1)
    result: list[float | None] = [None] * (period - 1)
    current = sum(values[:period]) / period
    result.append(current)
    for value in values[period:]:
        current = value * alpha + current * (1 - alpha)
        result.append(current)
    return result


def ema_last(values: list[float], period: int) -> float | None:
    series = ema_series(values, period)
    return series[-1] if series else None


def macd(
    values: list[float],
    *,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[float | None, float | None, float | None]:
    if len(values) < MIN_MACD_BARS:
        return None, None, None
    fast = ema_series(values, fast_period)
    slow = ema_series(values, slow_period)
    macd_values: list[float] = []
    for fast_value, slow_value in zip(fast, slow):
        if fast_value is not None and slow_value is not None:
            macd_values.append(fast_value - slow_value)
    signal = ema_series(macd_values, signal_period)
    signal_value = signal[-1] if signal else None
    macd_value = macd_values[-1] if macd_values else None
    if macd_value is None or signal_value is None:
        return macd_value, signal_value, None
    return macd_value, signal_value, macd_value - signal_value


def bollinger_bands(
    values: list[float],
    *,
    period: int = 20,
    stddev_multiplier: float = 2.0,
) -> tuple[float | None, float | None, float | None]:
    if len(values) < period:
        return None, None, None
    window = values[-period:]
    middle = sum(window) / period
    deviation = pstdev(window)
    return middle + stddev_multiplier * deviation, middle, middle - stddev_multiplier * deviation
