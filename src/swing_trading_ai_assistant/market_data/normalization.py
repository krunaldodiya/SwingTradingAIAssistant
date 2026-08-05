"""Provider payload normalization and deterministic candle validation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from numbers import Real


class CandleSchemaError(ValueError):
    """A provider candle cannot satisfy the internal raw-candle schema."""


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: float | None


def normalize_candles(rows: list[list[object]]) -> list[Candle]:
    """Validate, sort, and exactly deduplicate Upstox candle arrays."""
    by_timestamp: dict[datetime, Candle] = {}
    for row in rows:
        candle = _normalize_candle(row)
        existing = by_timestamp.get(candle.timestamp)
        if existing is not None and existing != candle:
            raise CandleSchemaError("conflicting candles share one timestamp")
        by_timestamp[candle.timestamp] = candle
    return [by_timestamp[timestamp] for timestamp in sorted(by_timestamp)]


def _normalize_candle(row: list[object]) -> Candle:
    if len(row) != 7:
        raise CandleSchemaError("candle must contain exactly seven fields")
    try:
        timestamp = datetime.fromisoformat(_required_text(row[0]))
    except ValueError as exc:
        raise CandleSchemaError("candle timestamp is not ISO-8601") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise CandleSchemaError("candle timestamp must include a timezone offset")

    open_price, high, low, close = (_finite_number(value) for value in row[1:5])
    if min(open_price, high, low, close) < 0:
        raise CandleSchemaError("OHLC prices must be non-negative")
    if high < max(open_price, low, close) or low > min(open_price, high, close):
        raise CandleSchemaError("OHLC values violate the high/low envelope")

    volume_value = _finite_number(row[5])
    if volume_value < 0 or not volume_value.is_integer():
        raise CandleSchemaError("volume must be a non-negative integer")
    oi = None if row[6] is None else _finite_number(row[6])
    if oi is not None and oi < 0:
        raise CandleSchemaError("open interest must be non-negative when present")

    return Candle(
        timestamp=timestamp,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=int(volume_value),
        oi=oi,
    )


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CandleSchemaError("candle timestamp must be text")
    return value


def _finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise CandleSchemaError("numeric candle field has an invalid type")
    number = float(value)
    if not math.isfinite(number):
        raise CandleSchemaError("numeric candle field must be finite")
    return number
