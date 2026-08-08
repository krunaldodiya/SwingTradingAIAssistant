"""ARK-84 schedule-bound coverage proofs without forward fill."""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime, timedelta

from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceResult,
    ScheduleFailureCode,
    ScheduleOutcome,
    ScheduleSession,
    canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.validation import (
    EquityMonthValidationPolicy,
    ValidationReason,
)

_POLICY = EquityMonthValidationPolicy("nse-equity-month@v1")
_MONTH_START = date(2026, 1, 1)
_MONTH_END = date(2026, 1, 31)


def _plan() -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|ID",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2026,
        1,
        _MONTH_START,
        _MONTH_END,
    )


def _session(
    trade_date: date, *, minutes: int, kind: str = "regular"
) -> ScheduleSession:
    opening = datetime(
        trade_date.year, trade_date.month, trade_date.day, 3, 45, tzinfo=UTC
    )
    return ScheduleSession(
        trade_date, opening, opening + timedelta(minutes=minutes), kind
    )


def _complete_v2_schedule(*sessions: ScheduleSession) -> ExpectedSessionSchedule:
    session_dates = {session.trade_date for session in sessions}
    closures = tuple(
        ScheduleClosure(date(2026, 1, day), "nse-sourced-closure")
        for day in range(1, monthrange(2026, 1)[1] + 1)
        if date(2026, 1, day) not in session_dates
    )
    return ExpectedSessionSchedule(
        2,
        "nse",
        "ark84-schedule-v2",
        datetime(2026, 2, 1, tzinfo=UTC),
        "Asia/Kolkata",
        _MONTH_START,
        _MONTH_END,
        sessions,
        closures,
    )


def _retained(schedule: ExpectedSessionSchedule) -> ScheduleEvidenceResult:
    retained = canonical_schedule_bytes(schedule)
    return ScheduleEvidenceResult(
        ScheduleOutcome.RETAINED,
        ScheduleFailureCode.NONE,
        schedule,
        retained,
        schedule_digest(schedule),
        "calendar-schedules/sha256/ark84.json",
    )


def _candle(ts: datetime) -> CanonicalCandle:
    return CanonicalCandle(
        "upstox",
        "NSE_EQ|ID",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        None,
        None,
        None,
        None,
        "1m",
        ts,
        100.0,
        101.0,
        99.0,
        100.5,
        10,
        None,
        datetime(2026, 2, 1, tzinfo=UTC),
        "upstox-historical-v3",
        "raw",
    )


def _candles_for(session: ScheduleSession) -> tuple[CanonicalCandle, ...]:
    return tuple(
        _candle(session.open_at + timedelta(minutes=offset))
        for offset in range(
            int((session.close_at - session.open_at).total_seconds() // 60)
        )
    )


def _validate(schedule: ExpectedSessionSchedule, candles: tuple[CanonicalCandle, ...]):
    return _POLICY.validate(
        _plan(),
        candles,
        _retained(schedule),
        raw_row_count=len(candles),
        normalized_row_count=len(candles),
    )


def test_d08_internal_gap_stays_missing_without_forward_fill() -> None:
    """D08: an interior scheduled minute remains missing in the returned evidence."""
    session = _session(date(2026, 1, 2), minutes=3)
    schedule = _complete_v2_schedule(session)
    missing = session.open_at + timedelta(minutes=1)
    candles = (
        _candle(session.open_at),
        _candle(session.close_at - timedelta(minutes=1)),
    )

    evidence = _validate(schedule, candles)

    assert evidence.coverage_passed is False
    assert evidence.quality_passed is True
    assert evidence.reason is ValidationReason.COVERAGE_EXPECTED_BAR_MISSING
    assert evidence.row_count == 2
    assert evidence.actual_from_ts == session.open_at
    assert evidence.actual_to_ts == session.close_at - timedelta(minutes=1)
    assert tuple(candle.ts for candle in candles) == (
        session.open_at,
        session.close_at - timedelta(minutes=1),
    )
    assert missing not in {candle.ts for candle in candles}


def test_d16_holiday_closure_requires_no_bar_when_supplied_session_is_complete() -> (
    None
):
    """D16: a sourced closure is not treated as an inferred trading session."""
    session = _session(date(2026, 1, 2), minutes=2)
    schedule = _complete_v2_schedule(session)
    candles = _candles_for(session)

    evidence = _validate(schedule, candles)

    assert schedule.closures[0] == ScheduleClosure(
        date(2026, 1, 1), "nse-sourced-closure"
    )
    assert evidence.coverage_passed is True
    assert evidence.quality_passed is True
    assert evidence.reason is ValidationReason.NONE
    assert evidence.row_count == 2
    assert evidence.actual_from_ts == session.open_at
    assert evidence.actual_to_ts == session.close_at - timedelta(minutes=1)
    assert all(
        candle.ts.date() != datetime(2026, 1, 1, tzinfo=UTC).date()
        for candle in candles
    )


def test_d16_special_session_uses_only_authoritative_shorter_bounds() -> None:
    """D16: no default-session minutes are inferred beyond a special session."""
    session = _session(date(2026, 1, 3), minutes=2, kind="special-short")
    schedule = _complete_v2_schedule(session)
    candles = _candles_for(session)

    evidence = _validate(schedule, candles)

    assert schedule.sessions == (session,)
    assert evidence.coverage_passed is True
    assert evidence.quality_passed is True
    assert evidence.reason is ValidationReason.NONE
    assert evidence.row_count == 2
    assert evidence.actual_from_ts == session.open_at
    assert evidence.actual_to_ts == session.close_at - timedelta(minutes=1)
    assert session.close_at not in {candle.ts for candle in candles}


def test_d17_declared_late_listing_or_no_trade_minute_fails_closed_without_fill() -> (
    None
):
    """D17: an absent scheduled minute cannot become verified coverage."""
    session = _session(date(2026, 1, 4), minutes=2)
    schedule = _complete_v2_schedule(session)
    missing = session.close_at - timedelta(minutes=1)
    candles = (_candle(session.open_at),)

    evidence = _validate(schedule, candles)

    assert evidence.coverage_passed is False
    assert evidence.quality_passed is True
    assert evidence.reason is ValidationReason.COVERAGE_EXPECTED_BAR_MISSING
    assert evidence.row_count == 1
    assert evidence.actual_from_ts == session.open_at
    assert evidence.actual_to_ts == session.open_at
    assert missing not in {candle.ts for candle in candles}
