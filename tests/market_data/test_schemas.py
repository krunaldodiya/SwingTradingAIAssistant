from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo

import pytest

from swing_trading_ai_assistant.market_data.schemas import (
    CANDLE_SCHEMA_VERSION,
    CanonicalCandle,
    DuplicateCandleKeyError,
    validate_unique_candle_keys,
)


def _candle(**overrides: object) -> CanonicalCandle:
    values: dict[str, object] = {
        "provider": "upstox",
        "instrument_key": "NSE_EQ|INE002A01018",
        "security_id": "INE002A01018",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "segment": "NSE_EQ",
        "instrument_type": "EQ",
        "underlying_id": None,
        "expiry": None,
        "strike": None,
        "option_type": None,
        "interval": "1m",
        "ts": datetime(
            2026, 8, 3, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30))
        ),
        "open": 1400.0,
        "high": 1403.0,
        "low": 1399.0,
        "close": 1402.0,
        "volume": 1000,
        "oi": None,
        "ingested_at": datetime(2026, 8, 5, 4, 30, tzinfo=UTC),
        "source_version": "upstox-historical-v3",
        "adjustment_state": "raw",
    }
    values.update(overrides)
    return CanonicalCandle(**values)  # type: ignore[arg-type]


def test_canonical_candle_is_immutable_versioned_and_canonicalizes_timestamps() -> None:
    candle = _candle()

    assert CANDLE_SCHEMA_VERSION == 1
    assert candle.schema_version == CANDLE_SCHEMA_VERSION
    assert candle.ts == datetime(2026, 8, 3, 3, 45, tzinfo=UTC)
    assert candle.ts.tzinfo is UTC
    assert candle.ingested_at.tzinfo is UTC
    assert candle.uniqueness_key == (
        "upstox",
        "NSE_EQ|INE002A01018",
        "1m",
        datetime(2026, 8, 3, 3, 45, tzinfo=UTC),
    )
    with pytest.raises(FrozenInstanceError):
        candle.volume = 1  # type: ignore[misc]


def test_canonical_candle_allows_typed_nullable_derivative_metadata() -> None:
    expiry = date(2026, 8, 27)

    candle = _candle(
        instrument_type="OPT",
        underlying_id="NSE_INDEX:NIFTY 50",
        expiry=expiry,
        strike=25000,
        option_type="CE",
        oi=42,
    )

    assert candle.expiry == expiry
    assert candle.strike == 25000.0
    assert candle.option_type == "CE"
    assert candle.oi == 42.0


def test_canonical_candle_rejects_off_minute_bar_open_but_allows_precise_ingestion() -> (
    None
):
    with pytest.raises(ValueError, match="ts.*minute-aligned"):
        _candle(ts=datetime(2026, 8, 3, 9, 15, 1, tzinfo=UTC))

    with pytest.raises(ValueError, match="ts.*minute-aligned"):
        _candle(ts=datetime(2026, 8, 3, 9, 15, 0, 1, tzinfo=UTC))

    candle = _candle(ingested_at=datetime(2026, 8, 5, 4, 30, 45, 12, tzinfo=UTC))

    assert candle.ingested_at == datetime(2026, 8, 5, 4, 30, 45, 12, tzinfo=UTC)


def test_canonical_candle_rejects_non_date_expiry() -> None:
    with pytest.raises(ValueError, match="expiry"):
        _candle(expiry="2026-08-27")


@pytest.mark.parametrize(
    "field",
    [
        "provider",
        "instrument_key",
        "security_id",
        "symbol",
        "exchange",
        "segment",
        "instrument_type",
        "source_version",
    ],
)
@pytest.mark.parametrize("value", ["  ", " leading", "trailing "])
def test_canonical_candle_rejects_noncanonical_required_identifiers(
    field: str, value: str
) -> None:
    with pytest.raises(ValueError, match=field):
        _candle(**{field: value})


@pytest.mark.parametrize("field", ["underlying_id", "option_type"])
@pytest.mark.parametrize("value", ["  ", " leading", "trailing "])
def test_canonical_candle_rejects_noncanonical_optional_identifiers(
    field: str, value: str
) -> None:
    with pytest.raises(ValueError, match=field):
        _candle(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "up stox"),
        ("instrument_key", "NSE EQ|INE002A01018"),
        ("security_id", "INE 002A01018"),
        ("symbol", "RELI ANCE"),
        ("exchange", "N SE"),
        ("segment", "NSE EQ"),
        ("instrument_type", "E Q"),
        ("source_version", "upstox historical v3"),
        ("underlying_id", "NSE INDEX:NIFTY 50"),
        ("option_type", "C E"),
    ],
)
def test_canonical_candle_allows_internal_identifier_whitespace(
    field: str, value: str
) -> None:
    assert getattr(_candle(**{field: value}), field) == value


class _StringSubclass(str):
    pass


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "upstox"),
        ("instrument_key", "NSE_EQ|INE002A01018"),
        ("security_id", "INE002A01018"),
        ("symbol", "RELIANCE"),
        ("exchange", "NSE"),
        ("segment", "NSE_EQ"),
        ("instrument_type", "EQ"),
        ("source_version", "upstox-historical-v3"),
        ("underlying_id", "NSE_INDEX:NIFTY 50"),
        ("option_type", "CE"),
        ("interval", "1m"),
        ("adjustment_state", "raw"),
    ],
)
def test_canonical_candle_rejects_string_subclasses(field: str, value: str) -> None:
    with pytest.raises(ValueError, match=field):
        _candle(**{field: _StringSubclass(value)})


@pytest.mark.parametrize("field", ["ts", "ingested_at"])
def test_canonical_candle_rejects_naive_timestamps(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        _candle(**{field: datetime(2026, 8, 3, 9, 15)})


def test_canonical_candle_rejects_non_datetime_timestamp() -> None:
    with pytest.raises(ValueError, match="ts"):
        _candle(ts="2026-08-03T09:15:00+05:30")


def test_canonical_candle_wraps_utc_conversion_overflow() -> None:
    with pytest.raises(ValueError, match="ts cannot be converted to UTC"):
        _candle(ts=datetime.min.replace(tzinfo=timezone(timedelta(hours=1))))


class _MalformedOffsetTimezone(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return "not-a-timedelta"  # type: ignore[return-value]

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return "malformed"


def test_canonical_candle_wraps_malformed_timezone_offset_type_error() -> None:
    malformed = datetime(2026, 8, 3, 9, 15, tzinfo=_MalformedOffsetTimezone())

    with pytest.raises(ValueError, match="ts cannot be converted to UTC"):
        _candle(ts=malformed)


class _DatetimeSubclass(datetime):
    pass


@pytest.mark.parametrize("field", ["ts", "ingested_at"])
def test_canonical_candle_rejects_datetime_subclasses(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        _candle(**{field: _DatetimeSubclass(2026, 8, 3, 9, 15, tzinfo=UTC)})


class _DateSubclass(date):
    pass


def test_canonical_candle_rejects_date_subclasses() -> None:
    with pytest.raises(ValueError, match="expiry"):
        _candle(expiry=_DateSubclass(2026, 8, 27))


@pytest.mark.parametrize(
    ("field", "value"),
    [("interval", "5m"), ("adjustment_state", "adjusted")],
)
def test_canonical_candle_rejects_unsupported_v1_metadata(
    field: str, value: str
) -> None:
    with pytest.raises(ValueError, match=field):
        _candle(**{field: value})


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "oi", "strike"])
@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf"), True, "1.0"]
)
def test_canonical_candle_rejects_non_finite_or_boolean_float_fields(
    field: str, value: object
) -> None:
    with pytest.raises(ValueError, match=field):
        _candle(**{field: value})


@pytest.mark.parametrize("field", ["open", "strike", "oi"])
def test_canonical_candle_wraps_huge_integer_float_overflow(field: str) -> None:
    with pytest.raises(ValueError, match=rf"{field}.*finite float"):
        _candle(**{field: 10**10_000})


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "oi"])
def test_canonical_candle_rejects_negative_prices_and_open_interest(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        _candle(**{field: -0.01})


def test_canonical_candle_requires_positive_strike() -> None:
    with pytest.raises(ValueError, match="strike"):
        _candle(strike=0.0)


@pytest.mark.parametrize("volume", [-1, 1.5, True])
def test_canonical_candle_rejects_invalid_volume(volume: object) -> None:
    with pytest.raises(ValueError, match="volume"):
        _candle(volume=volume)


class _IntSubclass(int):
    pass


class _FloatSubclass(float):
    pass


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "strike", "oi"])
@pytest.mark.parametrize("value", [_IntSubclass(1), _FloatSubclass(1.0)])
def test_canonical_candle_rejects_numeric_subclasses(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        _candle(**{field: value})


def test_canonical_candle_rejects_integer_subclasses_for_volume() -> None:
    with pytest.raises(ValueError, match="volume"):
        _candle(volume=_IntSubclass(1))


@pytest.mark.parametrize(
    "prices",
    [
        {"high": 1401.0, "close": 1402.0},
        {"low": 1401.0, "open": 1400.0},
    ],
)
def test_canonical_candle_rejects_invalid_ohlc_envelope(
    prices: dict[str, float],
) -> None:
    with pytest.raises(ValueError, match="OHLC"):
        _candle(**prices)


def test_duplicate_key_detection_is_pure_and_rejects_a_repeated_key() -> None:
    first = _candle()
    duplicate = _candle(close=1401.0)
    candles = [first, duplicate]

    with pytest.raises(DuplicateCandleKeyError) as exc_info:
        validate_unique_candle_keys(candles)

    assert exc_info.value.key == first.uniqueness_key
    assert candles == [first, duplicate]


def test_duplicate_key_detection_accepts_distinct_keys() -> None:
    first = _candle()
    second = _candle(ts=datetime(2026, 8, 3, 9, 16, tzinfo=UTC))

    validate_unique_candle_keys((first, second))


def test_canonical_candle_equality_and_hash_use_normalized_persisted_fields() -> None:
    utc_candle = _candle(ts=datetime(2026, 8, 3, 3, 45, tzinfo=UTC))
    offset_candle = _candle(
        ts=datetime(2026, 8, 3, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    )
    changed_candle = _candle(source_version="upstox-historical-v3-revised")

    assert utc_candle == offset_candle
    assert hash(utc_candle) == hash(offset_candle)
    assert {utc_candle, offset_candle} == {utc_candle}
    assert {utc_candle: "canonical"}[offset_candle] == "canonical"
    assert changed_candle != utc_candle
    assert changed_candle not in {utc_candle}


def test_canonical_candle_subclasses_are_prohibited() -> None:
    with pytest.raises(TypeError, match="cannot be subclassed"):

        class _CandleSubclass(CanonicalCandle):
            pass


def test_duplicate_key_detection_requires_exact_canonical_candles() -> None:
    with pytest.raises(ValueError, match="CanonicalCandle"):
        validate_unique_candle_keys([object()])  # type: ignore[arg-type]
