"""Test-only deterministic Plan 03 synthetic benchmark corpus support."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from swing_trading_ai_assistant.market_data.historical import HistoricalResponse
from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleSession,
    canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle

_FIXTURE_ID = "benchmark-nse-eq-v1"
_FIRST_MONTH = date(2023, 1, 1)
_LAST_MONTH = date(2024, 3, 1)
_VALIDATION_POLICY = "nse-equity-month@v1"
_SOURCE_VERSION = "upstox-historical-v3"
_SCHEDULE_SOURCE = "synthetic-benchmark"
_SESSION_KIND = "synthetic-regular"
_CLOSURE_REASON = "synthetic-benchmark-closure-v1"
_SESSION_MINUTES = 375
_SESSION_COUNT = 20


@dataclass(frozen=True, slots=True)
class BenchmarkFixturePartition:
    """One fixed synthetic month and its fake provider response."""

    instrument: Instrument
    plan: PlannedInstrumentMonth
    response: HistoricalResponse
    canonical_candles: tuple[CanonicalCandle, ...]
    raw_count: int
    normalized_count: int
    published_count: int


@dataclass(frozen=True, slots=True)
class BenchmarkFixture:
    """One range-wide schedule with its ordered synthetic monthly partitions."""

    fixture_id: str
    instrument: Instrument
    schedule: ExpectedSessionSchedule
    schedule_bytes: bytes
    schedule_digest: str
    validation_policy: str
    partitions: tuple[BenchmarkFixturePartition, ...]


def benchmark_nse_eq_v1(from_month: date, to_month: date) -> BenchmarkFixture:
    """Return one credential-free Plan 03 fixture range within its frozen domain."""
    _validate_month_range(from_month, to_month)
    instrument = _instrument()
    months = tuple(_months_inclusive(from_month, to_month))
    schedule = _schedule(months)
    partitions = tuple(_partition(instrument, month) for month in months)
    canonical_bytes = canonical_schedule_bytes(schedule)
    return BenchmarkFixture(
        _FIXTURE_ID,
        instrument,
        schedule,
        canonical_bytes,
        schedule_digest(schedule),
        _VALIDATION_POLICY,
        partitions,
    )


def _validate_month_range(from_month: object, to_month: object) -> None:
    if (
        type(from_month) is not date
        or type(to_month) is not date
        or from_month.day != 1
        or to_month.day != 1
        or from_month > to_month
        or from_month < _FIRST_MONTH
        or to_month > _LAST_MONTH
    ):
        raise ValueError("benchmark fixture month range is unsupported")


def _instrument() -> Instrument:
    return Instrument(
        instrument_key="NSE_EQ|TESTEQ",
        security_id="INE000A01000",
        symbol="TESTEQ",
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        isin="INE000A01000",
    )


def _months_inclusive(from_month: date, to_month: date) -> tuple[date, ...]:
    months: list[date] = []
    current = from_month
    while current <= to_month:
        months.append(current)
        current = _next_month(current)
    return tuple(months)


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _schedule(months: tuple[date, ...]) -> ExpectedSessionSchedule:
    sessions: list[ScheduleSession] = []
    closures: list[ScheduleClosure] = []
    for month in months:
        for day in range(1, monthrange(month.year, month.month)[1] + 1):
            trade_date = date(month.year, month.month, day)
            if day <= _SESSION_COUNT:
                open_at = datetime(month.year, month.month, day, 3, 45, tzinfo=UTC)
                sessions.append(
                    ScheduleSession(
                        trade_date,
                        open_at,
                        open_at + timedelta(minutes=_SESSION_MINUTES),
                        _SESSION_KIND,
                    )
                )
            else:
                closures.append(ScheduleClosure(trade_date, _CLOSURE_REASON))
    return ExpectedSessionSchedule(
        2,
        _SCHEDULE_SOURCE,
        _FIXTURE_ID,
        datetime.combine(_next_month(months[-1]), datetime.min.time(), tzinfo=UTC),
        "Asia/Kolkata",
        months[0],
        _last_day(months[-1]),
        tuple(sessions),
        tuple(closures),
    )


def _partition(instrument: Instrument, month: date) -> BenchmarkFixturePartition:
    plan = PlannedInstrumentMonth(
        "upstox",
        instrument.instrument_key,
        instrument.security_id,
        instrument.symbol,
        instrument.exchange,
        instrument.segment,
        instrument.instrument_type,
        "1m",
        month.year,
        month.month,
        month,
        _last_day(month),
    )
    ingested_at = datetime.combine(_next_month(month), datetime.min.time(), tzinfo=UTC)
    canonical: list[CanonicalCandle] = []
    raw_rows: list[list[object]] = []
    month_index = 12 * (month.year - 2023) + month.month - 1
    for session_index in range(_SESSION_COUNT):
        opening = datetime(
            month.year, month.month, session_index + 1, 3, 45, tzinfo=UTC
        )
        for minute_index in range(_SESSION_MINUTES):
            row_index = _SESSION_MINUTES * session_index + minute_index
            timestamp = opening + timedelta(minutes=minute_index)
            candle = _candle(
                instrument,
                timestamp,
                ingested_at,
                month_index,
                row_index,
            )
            canonical.append(candle)
            raw_rows.append(
                [
                    timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                    None,
                ]
            )
    rows = tuple(canonical)
    return BenchmarkFixturePartition(
        instrument,
        plan,
        HistoricalResponse(200, raw_rows),
        rows,
        len(raw_rows),
        len(rows),
        len(rows),
    )


def _last_day(month: date) -> date:
    return date(month.year, month.month, monthrange(month.year, month.month)[1])


def _candle(
    instrument: Instrument,
    timestamp: datetime,
    ingested_at: datetime,
    month_index: int,
    row_index: int,
) -> CanonicalCandle:
    cents = 100_000 + 10_000 * month_index + row_index
    return CanonicalCandle(
        provider="upstox",
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
        interval="1m",
        ts=timestamp,
        open=_price(cents),
        high=_price(cents + 4),
        low=_price(cents - 3),
        close=_price(cents + 1),
        volume=1_000_000 + 7_500 * month_index + row_index,
        oi=None,
        ingested_at=ingested_at,
        source_version=_SOURCE_VERSION,
        adjustment_state="raw",
    )


def _price(cents: int) -> float:
    return float(Decimal(cents).scaleb(-2))
