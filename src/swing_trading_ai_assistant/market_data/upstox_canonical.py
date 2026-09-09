"""Pure mapping from normalized Upstox equity candles to canonical candles."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime

from .instruments import Instrument
from .normalization import Candle, CandleSchemaError
from .schemas import (
    CanonicalCandle,
    DuplicateCandleKeyError,
    validate_unique_candle_keys,
)

_UPSTOX_PROVIDER = "upstox"
_ONE_MINUTE_INTERVAL = "1m"
_UPSTOX_HISTORICAL_V3 = "upstox-historical-v3"
_RAW_ADJUSTMENT_STATE = "raw"
MAX_UPSTOX_EQUITY_CANDLES = 65_536


def canonicalize_upstox_equity_candles(
    candles: Sequence[Candle], instrument: Instrument, ingested_at: datetime
) -> tuple[CanonicalCandle, ...]:
    """Map already-normalized NSE equity candles into the canonical v1 contract."""
    _validate_equity_instrument(instrument)
    _validate_ingested_at(ingested_at)
    if not isinstance(candles, Sequence):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise CandleSchemaError(
            "candles must be a sequence of normalized Candle values"
        )
    try:
        candle_count = len(candles)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CandleSchemaError(
            "candles must provide a valid finite sequence length"
        ) from exc
    if candle_count > MAX_UPSTOX_EQUITY_CANDLES:
        raise CandleSchemaError(
            "candles exceed the maximum one-month equity candle count"
        )
    canonical: list[CanonicalCandle] = []
    seen_keys: set[tuple[str, str, str, datetime]] = set()
    for index in range(candle_count):
        try:
            candle = candles[index]
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise CandleSchemaError("candles sequence is malformed") from exc
        if type(candle) is not Candle:
            raise CandleSchemaError(
                "candles must contain exact normalized Candle values"
            )
        _validate_source_open_interest(candle)
        canonical_candle = CanonicalCandle(
            provider=_UPSTOX_PROVIDER,
            instrument_key=instrument.instrument_key,
            security_id=instrument.security_id,
            symbol=instrument.symbol,
            exchange=instrument.exchange,
            segment=instrument.segment,
            instrument_type=instrument.instrument_type,
            underlying_id=None,
            expiry=None,
            strike=None,
            option_type=None,
            interval=_ONE_MINUTE_INTERVAL,
            ts=candle.timestamp,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            oi=None,
            ingested_at=ingested_at,
            source_version=_UPSTOX_HISTORICAL_V3,
            adjustment_state=_RAW_ADJUSTMENT_STATE,
        )
        if canonical_candle.uniqueness_key in seen_keys:
            raise DuplicateCandleKeyError(canonical_candle.uniqueness_key)
        seen_keys.add(canonical_candle.uniqueness_key)
        canonical.append(canonical_candle)
    validate_unique_candle_keys(canonical)
    return tuple(sorted(canonical, key=lambda candle: candle.ts))


def _validate_equity_instrument(instrument: Instrument) -> None:
    if type(instrument) is not Instrument:
        raise CandleSchemaError("a resolved Instrument is required")
    if (
        instrument.exchange != "NSE"
        or instrument.segment != "NSE_EQ"
        or instrument.instrument_type != "EQ"
        or any(
            value is not None
            for value in (
                instrument.underlying_key,
                instrument.expiry,
                instrument.strike_price,
                instrument.option_type,
            )
        )
    ):
        raise CandleSchemaError("Upstox canonicalization supports NSE/NSE_EQ/EQ only")


def _validate_source_open_interest(candle: Candle) -> None:
    if candle.oi is None:
        return
    if type(candle.oi) not in (int, float) or candle.oi != 0:
        raise CandleSchemaError(
            "equity candle source open interest must be absent or zero"
        )
    if not math.isfinite(candle.oi):
        raise CandleSchemaError(
            "equity candle source open interest must be absent or zero"
        )


def _validate_ingested_at(ingested_at: object) -> None:
    if type(ingested_at) is not datetime:
        raise CandleSchemaError("ingested_at must be a timezone-aware datetime")
    try:
        if ingested_at.tzinfo is None or ingested_at.utcoffset() is None:
            raise ValueError
        ingested_at.astimezone(UTC)
    except (OverflowError, TypeError, ValueError) as exc:
        raise CandleSchemaError(
            "ingested_at must be a valid UTC-convertible datetime"
        ) from exc
