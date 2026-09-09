"""Pure planning for one advancing, explicitly provisional equity month."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Final

from .schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleSession,
    canonical_schedule_bytes,
    schedule_digest,
)

_IST: Final = timezone(timedelta(hours=5, minutes=30))
_TIMEZONE_NAME: Final = "Asia/Kolkata"
_SAFE_LABEL: Final = re.compile(r"[\x20-\x7e]{1,128}\Z")
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")


class OpenMonthValidationError(ValueError):
    """An open-month request or schedule violates its supported input contract."""


@dataclass(frozen=True, slots=True)
class OpenMonthScheduleV1:
    """Authoritative classification through today, including a planned session."""

    schema_version: int
    source: str
    source_release: str
    as_of: datetime
    timezone: str
    covered_from: date
    covered_to: date
    sessions: tuple[ScheduleSession, ...]
    closures: tuple[ScheduleClosure, ...]

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != SCHEDULE_SCHEMA_VERSION_V3
            or type(self.source) is not str
            or _SAFE_LABEL.fullmatch(self.source) is None
            or type(self.source_release) is not str
            or _SAFE_LABEL.fullmatch(self.source_release) is None
            or type(self.as_of) is not datetime
            or self.as_of.tzinfo is None
            or self.as_of.utcoffset() is None
            or type(self.timezone) is not str
            or self.timezone != _TIMEZONE_NAME
            or type(self.covered_from) is not date
            or type(self.covered_to) is not date
            or self.covered_from > self.covered_to
            or type(self.sessions) is not tuple
            or any(type(item) is not ScheduleSession for item in self.sessions)
            or type(self.closures) is not tuple
            or any(type(item) is not ScheduleClosure for item in self.closures)
        ):
            raise OpenMonthValidationError("invalid open-month schedule")
        as_of = self.as_of.astimezone(UTC)
        if self.covered_to > as_of.astimezone(_IST).date():
            raise OpenMonthValidationError("invalid open-month schedule")
        session_dates = tuple(item.trade_date for item in self.sessions)
        closure_dates = tuple(item.trade_date for item in self.closures)
        if session_dates != tuple(sorted(session_dates)) or closure_dates != tuple(
            sorted(closure_dates)
        ):
            raise OpenMonthValidationError("invalid open-month schedule")
        classified = session_dates + closure_dates
        if len(classified) != len(set(classified)):
            raise OpenMonthValidationError("invalid open-month schedule")
        expected: list[date] = []
        current = self.covered_from
        while current <= self.covered_to:
            expected.append(current)
            current += timedelta(days=1)
        if set(classified) != set(expected):
            raise OpenMonthValidationError("invalid open-month schedule")
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "sessions", tuple(self.sessions))
        object.__setattr__(self, "closures", tuple(self.closures))


@dataclass(frozen=True, slots=True)
class OpenMonthPlanV1:
    """Provider-neutral split between prior-date and current-date retrieval."""

    requested_from: date
    requested_to: date
    month_start: date
    invocation: datetime
    historical_from: date | None
    historical_to: date | None
    intraday_trade_date: date | None
    last_completed_bar_start: datetime | None
    active_session_complete: bool
    schedule_digest: str

    def __post_init__(self) -> None:
        dates = (self.requested_from, self.requested_to, self.month_start)
        if (
            any(type(value) is not date for value in dates)
            or self.requested_from > self.requested_to
            or self.month_start.day != 1
            or type(self.invocation) is not datetime
            or self.invocation.tzinfo is None
            or self.invocation.utcoffset() is None
            or type(self.active_session_complete) is not bool
            or type(self.schedule_digest) is not str
            or _DIGEST.fullmatch(self.schedule_digest) is None
        ):
            raise OpenMonthValidationError("invalid open-month plan")
        if (self.historical_from is None) != (self.historical_to is None):
            raise OpenMonthValidationError("invalid open-month plan")
        if self.historical_from is not None and (
            type(self.historical_from) is not date
            or type(self.historical_to) is not date
            or self.historical_from > self.historical_to
        ):
            raise OpenMonthValidationError("invalid open-month plan")
        if (self.intraday_trade_date is None) != (
            self.last_completed_bar_start is None
        ):
            raise OpenMonthValidationError("invalid open-month plan")
        if self.intraday_trade_date is not None and (
            type(self.intraday_trade_date) is not date
            or type(self.last_completed_bar_start) is not datetime
            or self.last_completed_bar_start.tzinfo is None
            or self.last_completed_bar_start.utcoffset() is None
        ):
            raise OpenMonthValidationError("invalid open-month plan")
        object.__setattr__(self, "invocation", self.invocation.astimezone(UTC))
        if self.last_completed_bar_start is not None:
            object.__setattr__(
                self,
                "last_completed_bar_start",
                self.last_completed_bar_start.astimezone(UTC),
            )


def canonical_open_month_schedule_bytes(schedule: object) -> bytes:
    """Return the sole deterministic representation used for provenance."""
    if type(schedule) is not OpenMonthScheduleV1:
        raise OpenMonthValidationError("invalid open-month schedule")
    return canonical_schedule_bytes(_as_evidence(schedule))


def open_month_schedule_digest(schedule: object) -> str:
    if type(schedule) is not OpenMonthScheduleV1:
        raise OpenMonthValidationError("invalid open-month schedule")
    return schedule_digest(_as_evidence(schedule))


def open_month_schedule_from_evidence(schedule: object) -> OpenMonthScheduleV1:
    """Admit one retained v3 schedule into the open-month planner."""
    if (
        type(schedule) is not ExpectedSessionSchedule
        or schedule.schema_version != SCHEDULE_SCHEMA_VERSION_V3
    ):
        raise OpenMonthValidationError("invalid open-month schedule evidence")
    result = OpenMonthScheduleV1(
        schema_version=schedule.schema_version,
        source=schedule.source,
        source_release=schedule.source_release,
        as_of=schedule.as_of,
        timezone=schedule.timezone,
        covered_from=schedule.covered_from,
        covered_to=schedule.covered_to,
        sessions=schedule.sessions,
        closures=schedule.closures,
    )
    if canonical_open_month_schedule_bytes(result) != canonical_schedule_bytes(
        schedule
    ):
        raise OpenMonthValidationError("invalid open-month schedule evidence")
    return result


def _as_evidence(schedule: OpenMonthScheduleV1) -> ExpectedSessionSchedule:
    return ExpectedSessionSchedule(
        schema_version=schedule.schema_version,
        source=schedule.source,
        source_release=schedule.source_release,
        as_of=schedule.as_of,
        timezone=schedule.timezone,
        covered_from=schedule.covered_from,
        covered_to=schedule.covered_to,
        sessions=schedule.sessions,
        closures=schedule.closures,
    )


def plan_open_month(
    requested_from: object,
    requested_to: object,
    schedule: object,
    invocation: object,
) -> OpenMonthPlanV1:
    """Plan one current local month without guessing calendar or data state."""
    if (
        type(requested_from) is not date
        or type(requested_to) is not date
        or requested_from > requested_to
        or type(schedule) is not OpenMonthScheduleV1
        or type(invocation) is not datetime
        or invocation.tzinfo is None
        or invocation.utcoffset() is None
    ):
        raise OpenMonthValidationError("invalid open-month request")
    invoked = invocation.astimezone(UTC)
    local_today = invoked.astimezone(_IST).date()
    month_start = date(local_today.year, local_today.month, 1)
    if (
        requested_from < month_start
        or requested_to > local_today
        or (requested_from.year, requested_from.month)
        != (local_today.year, local_today.month)
        or (requested_to.year, requested_to.month)
        != (local_today.year, local_today.month)
        or schedule.covered_from > month_start
        or schedule.covered_to < requested_to
        or schedule.as_of > invoked
    ):
        raise OpenMonthValidationError("invalid open-month request")

    historical_end = min(requested_to, local_today - timedelta(days=1))
    has_historical_session = any(
        month_start <= item.trade_date <= historical_end for item in schedule.sessions
    )
    historical_from = month_start if has_historical_session else None
    historical_to = historical_end if has_historical_session else None

    intraday_date: date | None = None
    last_completed: datetime | None = None
    active_complete = False
    if requested_to == local_today:
        active = next(
            (item for item in schedule.sessions if item.trade_date == local_today),
            None,
        )
        if active is not None:
            minute_floor = invoked.replace(second=0, microsecond=0)
            candidate = min(
                minute_floor - timedelta(minutes=1),
                active.close_at - timedelta(minutes=1),
            )
            if candidate >= active.open_at:
                intraday_date = local_today
                last_completed = candidate
                active_complete = invoked >= active.close_at

    return OpenMonthPlanV1(
        requested_from=requested_from,
        requested_to=requested_to,
        month_start=month_start,
        invocation=invoked,
        historical_from=historical_from,
        historical_to=historical_to,
        intraday_trade_date=intraday_date,
        last_completed_bar_start=last_completed,
        active_session_complete=active_complete,
        schedule_digest=open_month_schedule_digest(schedule),
    )
