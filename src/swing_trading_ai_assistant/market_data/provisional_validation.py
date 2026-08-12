"""Append-only validation for an immutable current-month candle snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final, NoReturn, cast

from .open_month import (
    OpenMonthPlanV1,
    OpenMonthScheduleV1,
    open_month_schedule_digest,
)
from .schedule_evidence import ScheduleSession
from .schemas import CanonicalCandle

MAX_PROVISIONAL_CANDLES_V1: Final = 65_536
_HISTORICAL_SOURCE_V3: Final = "upstox-historical-v3"
_INTRADAY_SOURCE_V3: Final = "upstox-intraday-v3"


class ProvisionalValidationCodeV1(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    SCHEDULE_MISMATCH = "SCHEDULE_MISMATCH"
    PREFIX_CONFLICT = "PREFIX_CONFLICT"
    HISTORICAL_FINALIZATION_INCOMPLETE = "HISTORICAL_FINALIZATION_INCOMPLETE"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    OFF_SESSION_BAR = "OFF_SESSION_BAR"


class ProvisionalValidationFailureV1(ValueError):
    """Stable failure without provider values, paths, or credentials."""

    def __init__(self, code: ProvisionalValidationCodeV1) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class ProvisionalValidationV1:
    candles: tuple[CanonicalCandle, ...]
    target_cutoff: datetime | None
    actual_cutoff: datetime | None
    complete_to_target: bool
    session_complete: bool
    missing_count: int
    appended_count: int
    discarded_unfinished_count: int
    schedule_digest: str

    def __post_init__(self) -> None:
        counts = (
            self.missing_count,
            self.appended_count,
            self.discarded_unfinished_count,
        )
        if (
            type(self.candles) is not tuple
            or any(type(value) is not CanonicalCandle for value in self.candles)
            or len(self.candles) > MAX_PROVISIONAL_CANDLES_V1
            or type(self.complete_to_target) is not bool
            or type(self.session_complete) is not bool
            or any(type(value) is not int or value < 0 for value in counts)
            or type(self.schedule_digest) is not str
            or len(self.schedule_digest) != 64
            or (self.actual_cutoff is None) != (not self.candles)
            or self.session_complete
            and not self.complete_to_target
        ):
            raise ValueError("invalid provisional validation")
        if self.target_cutoff is not None and (
            type(self.target_cutoff) is not datetime
            or self.target_cutoff.tzinfo is None
            or self.target_cutoff.utcoffset() is None
        ):
            raise ValueError("invalid provisional validation")
        if self.actual_cutoff is not None and (
            type(self.actual_cutoff) is not datetime
            or self.actual_cutoff.tzinfo is None
            or self.actual_cutoff.utcoffset() is None
            or self.actual_cutoff != self.candles[-1].ts
            or self.target_cutoff is None
            or self.actual_cutoff > self.target_cutoff
        ):
            raise ValueError("invalid provisional validation")


def validate_provisional_advance(
    schedule: object,
    plan: object,
    existing: object,
    fetched_history: object,
    fetched_intraday: object,
) -> ProvisionalValidationV1:
    """Retain an unchanged prefix and add only newly completed one-minute bars."""
    schedule, plan, existing, fetched_history, fetched_intraday = _validated_inputs(
        schedule, plan, existing, fetched_history, fetched_intraday
    )
    digest = open_month_schedule_digest(schedule)
    if digest != plan.schedule_digest:
        _fail(ProvisionalValidationCodeV1.SCHEDULE_MISMATCH)

    expected = _expected_timestamps(schedule, plan)
    target = expected[-1] if expected else None
    if (
        plan.last_completed_bar_start is not None
        and target != plan.last_completed_bar_start
    ):
        _fail(ProvisionalValidationCodeV1.SCHEDULE_MISMATCH)
    expected_set = set(expected)
    finalized = _finalized_timestamps(schedule, plan, expected_set)
    combined, existing_keys, discarded = _merge_candles(
        schedule,
        plan,
        target,
        expected_set,
        finalized,
        existing,
        fetched_history,
        fetched_intraday,
    )
    if any(
        (candle := combined.get(timestamp)) is None
        or candle.source_version != _HISTORICAL_SOURCE_V3
        for timestamp in finalized
    ):
        _fail(ProvisionalValidationCodeV1.HISTORICAL_FINALIZATION_INCOMPLETE)
    retained: list[CanonicalCandle] = []
    for timestamp in expected:
        candle = combined.get(timestamp)
        if candle is None:
            break
        retained.append(candle)
    retained_tuple = tuple(retained)
    complete = len(retained_tuple) == len(expected)
    appended = sum(value.ts not in existing_keys for value in retained_tuple)
    return ProvisionalValidationV1(
        candles=retained_tuple,
        target_cutoff=target,
        actual_cutoff=retained_tuple[-1].ts if retained_tuple else None,
        complete_to_target=complete,
        session_complete=plan.active_session_complete and complete,
        missing_count=len(expected) - len(retained_tuple),
        appended_count=appended,
        discarded_unfinished_count=discarded,
        schedule_digest=digest,
    )


def _validated_inputs(
    schedule: object,
    plan: object,
    existing: object,
    fetched_history: object,
    fetched_intraday: object,
) -> tuple[
    OpenMonthScheduleV1,
    OpenMonthPlanV1,
    tuple[CanonicalCandle, ...],
    tuple[CanonicalCandle, ...],
    tuple[CanonicalCandle, ...],
]:
    if type(schedule) is not OpenMonthScheduleV1 or type(plan) is not OpenMonthPlanV1:
        _fail(ProvisionalValidationCodeV1.INVALID_INPUT)
    if (
        type(existing) is not tuple
        or type(fetched_history) is not tuple
        or type(fetched_intraday) is not tuple
    ):
        _fail(ProvisionalValidationCodeV1.INVALID_INPUT)
    values = cast(
        tuple[tuple[object, ...], tuple[object, ...], tuple[object, ...]],
        (existing, fetched_history, fetched_intraday),
    )
    if any(len(value) > MAX_PROVISIONAL_CANDLES_V1 for value in values) or any(
        type(candle) is not CanonicalCandle for value in values for candle in value
    ):
        _fail(ProvisionalValidationCodeV1.INVALID_INPUT)
    typed = cast(
        tuple[
            tuple[CanonicalCandle, ...],
            tuple[CanonicalCandle, ...],
            tuple[CanonicalCandle, ...],
        ],
        values,
    )
    return schedule, plan, typed[0], typed[1], typed[2]


def _merge_candles(
    schedule: OpenMonthScheduleV1,
    plan: OpenMonthPlanV1,
    target: datetime | None,
    expected: set[datetime],
    finalized: set[datetime],
    existing: tuple[CanonicalCandle, ...],
    fetched_history: tuple[CanonicalCandle, ...],
    fetched_intraday: tuple[CanonicalCandle, ...],
) -> tuple[dict[datetime, CanonicalCandle], set[datetime], int]:
    identity: tuple[object, ...] | None = None
    combined: dict[datetime, CanonicalCandle] = {}
    existing_keys: set[datetime] = set()
    discarded = 0
    active_session = next(
        (
            value
            for value in schedule.sessions
            if value.trade_date == plan.intraday_trade_date
        ),
        None,
    )
    for origin, values in (
        ("existing", existing),
        ("history", fetched_history),
        ("intraday", fetched_intraday),
    ):
        for candle in values:
            identity = _validated_identity(origin, candle, identity)
            if candle.ts not in expected:
                if origin == "intraday" and _unfinished_current_bar(
                    candle, target, active_session
                ):
                    discarded += 1
                    continue
                _fail(ProvisionalValidationCodeV1.OFF_SESSION_BAR)
            prior = combined.get(candle.ts)
            correction = _is_historical_finalization(
                origin, prior, candle.ts, finalized
            )
            if _has_prefix_conflict(prior, candle, correction):
                _fail(ProvisionalValidationCodeV1.PREFIX_CONFLICT)
            if prior is None or correction:
                combined[candle.ts] = candle
            if origin == "existing":
                existing_keys.add(candle.ts)
    return combined, existing_keys, discarded


def _validated_identity(
    origin: str,
    candle: CanonicalCandle,
    identity: tuple[object, ...] | None,
) -> tuple[object, ...]:
    if not _valid_source(origin, candle.source_version):
        _fail(ProvisionalValidationCodeV1.IDENTITY_MISMATCH)
    current = _identity(candle)
    if identity is not None and current != identity:
        _fail(ProvisionalValidationCodeV1.IDENTITY_MISMATCH)
    return current if identity is None else identity


def _has_prefix_conflict(
    prior: CanonicalCandle | None,
    candle: CanonicalCandle,
    correction: bool,
) -> bool:
    return (
        prior is not None
        and not correction
        and _raw_signature(prior) != _raw_signature(candle)
    )


def _is_historical_finalization(
    origin: str,
    prior: CanonicalCandle | None,
    timestamp: datetime,
    finalized: set[datetime],
) -> bool:
    return (
        origin == "history"
        and prior is not None
        and prior.source_version == _INTRADAY_SOURCE_V3
        and timestamp in finalized
    )


def _valid_source(origin: str, source_version: str) -> bool:
    if origin == "history":
        return source_version == _HISTORICAL_SOURCE_V3
    if origin == "intraday":
        return source_version == _INTRADAY_SOURCE_V3
    return source_version in {_HISTORICAL_SOURCE_V3, _INTRADAY_SOURCE_V3}


def _finalized_timestamps(
    schedule: OpenMonthScheduleV1,
    plan: OpenMonthPlanV1,
    expected: set[datetime],
) -> set[datetime]:
    if plan.historical_to is None:
        return set()
    finalized: set[datetime] = set()
    for session in schedule.sessions:
        if session.trade_date > plan.historical_to:
            continue
        current = session.open_at
        final = session.close_at - timedelta(minutes=1)
        while current <= final:
            if current in expected:
                finalized.add(current)
            current += timedelta(minutes=1)
    return finalized


def _expected_timestamps(
    schedule: OpenMonthScheduleV1, plan: OpenMonthPlanV1
) -> tuple[datetime, ...]:
    expected: list[datetime] = []
    for session in schedule.sessions:
        final = session.close_at - timedelta(minutes=1)
        if session.trade_date == plan.intraday_trade_date:
            if plan.last_completed_bar_start is None:
                continue
            final = min(final, plan.last_completed_bar_start)
        elif plan.historical_to is None or session.trade_date > plan.historical_to:
            continue
        current = session.open_at
        while current <= final:
            expected.append(current)
            if len(expected) > MAX_PROVISIONAL_CANDLES_V1:
                _fail(ProvisionalValidationCodeV1.INVALID_INPUT)
            current += timedelta(minutes=1)
    return tuple(sorted(expected))


def _identity(candle: CanonicalCandle) -> tuple[object, ...]:
    return (
        candle.provider,
        candle.instrument_key,
        candle.security_id,
        candle.symbol,
        candle.exchange,
        candle.segment,
        candle.instrument_type,
        candle.interval,
        candle.adjustment_state,
    )


def _raw_signature(candle: CanonicalCandle) -> tuple[object, ...]:
    return (
        _identity(candle),
        candle.ts,
        candle.open,
        candle.high,
        candle.low,
        candle.close,
        candle.volume,
        candle.oi,
    )


def _unfinished_current_bar(
    candle: CanonicalCandle,
    target: datetime | None,
    active_session: ScheduleSession | None,
) -> bool:
    if active_session is None or target is None:
        return False
    return target < candle.ts < active_session.close_at


def _fail(code: ProvisionalValidationCodeV1) -> NoReturn:
    raise ProvisionalValidationFailureV1(code) from None
