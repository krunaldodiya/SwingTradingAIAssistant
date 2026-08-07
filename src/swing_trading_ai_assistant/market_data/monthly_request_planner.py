"""Pure bounded one-minute calendar-month request planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .instruments import Instrument

_FIRST_AVAILABLE_DATE = date(2022, 1, 1)
MAX_PLANNED_MONTHS = (date.max.year - 2022 + 1) * 12


@dataclass(frozen=True, slots=True)
class PlannedInstrumentMonth:
    provider: str
    instrument_key: str
    security_id: str
    symbol: str
    exchange: str
    segment: str
    instrument_type: str
    interval: str
    year: int
    month: int
    from_date: date
    to_date: date

    def __init_subclass__(cls) -> None:
        raise TypeError("PlannedInstrumentMonth cannot be subclassed")

    def __post_init__(self) -> None:
        if (
            not _is_exact_string_fields(
                self.provider,
                self.instrument_key,
                self.security_id,
                self.symbol,
                self.exchange,
                self.segment,
                self.instrument_type,
                self.interval,
            )
            or not _is_planned_identity(
                self.provider,
                self.instrument_key,
                self.security_id,
                self.symbol,
                self.exchange,
                self.segment,
                self.instrument_type,
                self.interval,
            )
            or type(self.year) is not int
            or type(self.month) is not int
            or not 2022 <= self.year <= date.max.year
            or not 1 <= self.month <= 12
            or type(self.from_date) is not date
            or type(self.to_date) is not date
            or self.from_date > self.to_date
            or self.from_date.month != self.month
            or self.to_date.month != self.month
            or self.from_date.year != self.year
            or self.to_date.year != self.year
        ):
            raise ValueError("invalid planned instrument month")


def plan_upstox_equity_months(
    instrument: Instrument, from_date: date, to_date: date, interval: str
) -> tuple[PlannedInstrumentMonth, ...]:
    _validate(instrument, from_date, to_date, interval)
    count = _month_count(from_date, to_date)
    if count > MAX_PLANNED_MONTHS:
        raise ValueError("planned month count exceeds natural bound")
    plans: list[PlannedInstrumentMonth] = []
    for offset in range(count):
        month_index = from_date.month - 1 + offset
        year, month = from_date.year + month_index // 12, month_index % 12 + 1
        start = from_date if offset == 0 else date(year, month, 1)
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        end = (
            to_date
            if offset == count - 1
            else date(next_year, next_month, 1).fromordinal(
                date(next_year, next_month, 1).toordinal() - 1
            )
        )
        plans.append(
            PlannedInstrumentMonth(
                "upstox",
                instrument.instrument_key,
                instrument.security_id,
                instrument.symbol,
                instrument.exchange,
                instrument.segment,
                instrument.instrument_type,
                interval,
                year,
                month,
                start,
                end,
            )
        )
    return tuple(plans)


def _validate(
    instrument: object, from_date: object, to_date: object, interval: object
) -> None:
    if type(instrument) is not Instrument:
        raise ValueError("a resolved NSE/NSE_EQ/EQ equity Instrument is required")
    if not _is_exact_string_fields(
        instrument.instrument_key,
        instrument.security_id,
        instrument.symbol,
        instrument.exchange,
        instrument.segment,
        instrument.instrument_type,
        instrument.isin,
    ):
        raise ValueError("a resolved NSE/NSE_EQ/EQ equity Instrument is required")
    if (
        not _is_planned_identity(
            "upstox",
            instrument.instrument_key,
            instrument.security_id,
            instrument.symbol,
            instrument.exchange,
            instrument.segment,
            instrument.instrument_type,
            "1m",
        )
        or instrument.isin != instrument.security_id
        or instrument.underlying_key is not None
        or instrument.expiry is not None
        or instrument.strike_price is not None
        or instrument.option_type is not None
    ):
        raise ValueError("a resolved NSE/NSE_EQ/EQ equity Instrument is required")
    if type(from_date) is not date or type(to_date) is not date:
        raise ValueError("from_date and to_date must be built-in dates")
    if from_date < _FIRST_AVAILABLE_DATE or to_date < _FIRST_AVAILABLE_DATE:
        raise ValueError("dates before 2022-01-01 are not supported")
    if from_date > to_date:
        raise ValueError("from_date must be on or before to_date")
    if type(interval) is not str or interval != "1m":
        raise ValueError("interval must be built-in '1m'")


def _is_exact_string_fields(*values: object) -> bool:
    return all(type(value) is str for value in values)


def _is_planned_identity(
    provider: str,
    instrument_key: str,
    security_id: str,
    symbol: str,
    exchange: str,
    segment: str,
    instrument_type: str,
    interval: str,
) -> bool:
    return (
        provider == "upstox"
        and exchange == "NSE"
        and segment == "NSE_EQ"
        and instrument_type == "EQ"
        and interval == "1m"
        and all(
            value and value == value.strip()
            for value in (instrument_key, security_id, symbol)
        )
    )


def _month_count(from_date: date, to_date: date) -> int:
    return (to_date.year - from_date.year) * 12 + to_date.month - from_date.month + 1
