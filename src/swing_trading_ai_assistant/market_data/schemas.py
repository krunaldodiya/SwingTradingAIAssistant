"""Provider- and storage-independent canonical market-data schemas."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import ClassVar, TypeAlias, cast

CANDLE_SCHEMA_VERSION = 1

CandleUniquenessKey: TypeAlias = tuple[str, str, str, datetime]


class DuplicateCandleKeyError(ValueError):
    """Raised when canonical candles repeat a persistence uniqueness key."""

    def __init__(self, key: CandleUniquenessKey) -> None:
        self.key = key
        super().__init__(f"duplicate canonical candle key: {key!r}")


@dataclass(frozen=True, slots=True)
class CanonicalCandle:
    """Immutable canonical one-minute raw candle contract, schema version 1."""

    provider: str
    instrument_key: str
    security_id: str
    symbol: str
    exchange: str
    segment: str
    instrument_type: str
    underlying_id: str | None
    expiry: date | None
    strike: float | None
    option_type: str | None
    interval: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: float | None
    ingested_at: datetime
    source_version: str
    adjustment_state: str

    schema_version: ClassVar[int] = CANDLE_SCHEMA_VERSION

    def __init_subclass__(cls) -> None:
        raise TypeError("CanonicalCandle cannot be subclassed")

    def __post_init__(self) -> None:
        _validate_metadata(self)
        object.__setattr__(self, "ts", _utc_timestamp("ts", self.ts))
        _validate_bar_open_timestamp(self.ts)
        object.__setattr__(
            self,
            "ingested_at",
            _utc_timestamp("ingested_at", self.ingested_at),
        )
        for field_name in ("open", "high", "low", "close"):
            object.__setattr__(
                self,
                field_name,
                _nonnegative_float(field_name, getattr(self, field_name)),
            )
        _validate_ohlc_envelope(self)
        _validate_volume(self.volume)
        if self.oi is not None:
            object.__setattr__(self, "oi", _nonnegative_float("oi", self.oi))
        if self.strike is not None:
            object.__setattr__(self, "strike", _positive_float("strike", self.strike))

    @property
    def uniqueness_key(self) -> CandleUniquenessKey:
        """Return the canonical candle persistence uniqueness key."""
        return self.provider, self.instrument_key, self.interval, self.ts


def _validate_metadata(candle: CanonicalCandle) -> None:
    for field_name in (
        "provider",
        "instrument_key",
        "security_id",
        "symbol",
        "exchange",
        "segment",
        "instrument_type",
        "source_version",
    ):
        _require_nonblank(field_name, getattr(candle, field_name))
    for field_name in ("underlying_id", "option_type"):
        value = getattr(candle, field_name)
        if value is not None:
            _require_nonblank(field_name, value)
    _validate_expiry(candle.expiry)
    _require_exact_string("interval", candle.interval)
    _require_exact_string("adjustment_state", candle.adjustment_state)
    if candle.interval != "1m":
        raise ValueError("interval must be '1m' for candle schema v1")
    if candle.adjustment_state != "raw":
        raise ValueError("adjustment_state must be 'raw' for candle schema v1")


def _validate_ohlc_envelope(candle: CanonicalCandle) -> None:
    if candle.high < max(candle.open, candle.close, candle.low) or candle.low > min(
        candle.open, candle.close, candle.high
    ):
        raise ValueError("OHLC values violate the high/low envelope")


def _validate_volume(volume: object) -> None:
    if type(volume) is not int or volume < 0:
        raise ValueError("volume must be a non-negative integer")


def _validate_expiry(expiry: object) -> None:
    if expiry is not None and type(expiry) is not date:
        raise ValueError("expiry must be a date when present")


def _nonnegative_float(field_name: str, value: object) -> float:
    number = _finite_float(field_name, value)
    if number < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return number


def _positive_float(field_name: str, value: object) -> float:
    number = _finite_float(field_name, value)
    if number <= 0:
        raise ValueError(f"{field_name} must be positive when present")
    return number


def validate_unique_candle_keys(candles: Iterable[CanonicalCandle]) -> None:
    """Reject duplicate candle keys without mutating or retaining the input."""
    seen: set[CandleUniquenessKey] = set()
    for candle in candles:
        if type(candle) is not CanonicalCandle:
            raise ValueError("candles must be exact CanonicalCandle instances")
        key = candle.uniqueness_key
        if key in seen:
            raise DuplicateCandleKeyError(key)
        seen.add(key)


def _require_nonblank(field_name: str, value: object) -> None:
    _require_exact_string(field_name, value)
    string_value = cast(str, value)
    if not string_value or string_value != string_value.strip():
        raise ValueError(
            f"{field_name} must be nonblank without surrounding whitespace"
        )


def _require_exact_string(field_name: str, value: object) -> None:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a built-in string")


def _utc_timestamp(field_name: str, value: object) -> datetime:
    if type(value) is not datetime:
        raise ValueError(f"{field_name} must be a built-in datetime")
    try:
        is_timezone_aware = value.tzinfo is not None and value.utcoffset() is not None
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} cannot be converted to UTC") from exc
    if not is_timezone_aware:
        raise ValueError(f"{field_name} must be timezone-aware")
    try:
        return value.astimezone(UTC)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} cannot be converted to UTC") from exc


def _validate_bar_open_timestamp(ts: datetime) -> None:
    if ts.second != 0 or ts.microsecond != 0:
        raise ValueError("ts must be minute-aligned with zero seconds and microseconds")


def _finite_float(field_name: str, value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{field_name} must be a finite float")
    try:
        number = float(cast(int | float, value))
    except OverflowError as exc:
        raise ValueError(f"{field_name} must be a finite float") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite float")
    return number
