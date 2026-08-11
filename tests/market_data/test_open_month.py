from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from swing_trading_ai_assistant.market_data.open_month import (
    OpenMonthPlanV1,
    OpenMonthScheduleV1,
    canonical_open_month_schedule_bytes,
    open_month_schedule_digest,
    open_month_schedule_from_evidence,
    plan_open_month,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleSession,
    canonical_schedule_bytes,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _instant(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=IST)


def _session(day: int) -> ScheduleSession:
    return ScheduleSession(
        date(2026, 8, day),
        _instant(day, 9, 15),
        _instant(day, 15, 30),
        "REGULAR",
    )


def _schedule(*, as_of: datetime, through: int = 11) -> OpenMonthScheduleV1:
    session_days = {3, 4, 5, 6, 7, 10, 11}
    sessions = tuple(
        _session(day) for day in range(1, through + 1) if day in session_days
    )
    closures = tuple(
        ScheduleClosure(date(2026, 8, day), "EXCHANGE_CLOSED")
        for day in range(1, through + 1)
        if day not in session_days
    )
    return OpenMonthScheduleV1(
        schema_version=SCHEDULE_SCHEMA_VERSION_V3,
        source="authoritative-nse-calendar",
        source_release="2026-08-11T09:00:00+05:30",
        as_of=as_of,
        timezone="Asia/Kolkata",
        covered_from=date(2026, 8, 1),
        covered_to=date(2026, 8, through),
        sessions=sessions,
        closures=closures,
    )


def test_active_session_plans_history_plus_last_completed_minute() -> None:
    invocation = _instant(
        11,
        10,
        0,
    ).replace(second=37)
    schedule = _schedule(as_of=_instant(11, 9, 0))

    result = plan_open_month(date(2026, 8, 1), date(2026, 8, 11), schedule, invocation)

    assert result == OpenMonthPlanV1(
        requested_from=date(2026, 8, 1),
        requested_to=date(2026, 8, 11),
        month_start=date(2026, 8, 1),
        invocation=invocation.astimezone(UTC),
        historical_from=date(2026, 8, 1),
        historical_to=date(2026, 8, 10),
        intraday_trade_date=date(2026, 8, 11),
        last_completed_bar_start=_instant(11, 9, 59).astimezone(UTC),
        active_session_complete=False,
        schedule_digest=open_month_schedule_digest(schedule),
    )


def test_after_close_caps_intraday_at_final_scheduled_minute() -> None:
    schedule = _schedule(as_of=_instant(11, 9, 0))
    result = plan_open_month(
        date(2026, 8, 5), date(2026, 8, 11), schedule, _instant(11, 18, 0)
    )

    assert result.historical_from == date(2026, 8, 1)
    assert result.historical_to == date(2026, 8, 10)
    assert result.intraday_trade_date == date(2026, 8, 11)
    assert result.last_completed_bar_start == _instant(11, 15, 29).astimezone(UTC)
    assert result.active_session_complete is True


def test_before_first_completed_minute_avoids_intraday_request() -> None:
    schedule = _schedule(as_of=_instant(11, 9, 0))
    result = plan_open_month(
        date(2026, 8, 1),
        date(2026, 8, 11),
        schedule,
        _instant(
            11,
            9,
            15,
        ).replace(second=59),
    )

    assert result.historical_to == date(2026, 8, 10)
    assert result.intraday_trade_date is None
    assert result.last_completed_bar_start is None
    assert result.active_session_complete is False


def test_current_date_closure_never_uses_intraday() -> None:
    prior_sessions = tuple(_session(day) for day in (3, 4, 5, 6, 7, 10))
    closures = tuple(
        ScheduleClosure(
            date(2026, 8, day),
            "SPECIAL_CLOSURE" if day == 11 else "EXCHANGE_CLOSED",
        )
        for day in (1, 2, 8, 9, 11)
    )
    schedule = OpenMonthScheduleV1(
        schema_version=SCHEDULE_SCHEMA_VERSION_V3,
        source="authoritative-nse-calendar",
        source_release="closure-release",
        as_of=_instant(11, 8, 0),
        timezone="Asia/Kolkata",
        covered_from=date(2026, 8, 1),
        covered_to=date(2026, 8, 11),
        sessions=prior_sessions,
        closures=closures,
    )
    result = plan_open_month(
        date(2026, 8, 11), date(2026, 8, 11), schedule, _instant(11, 12, 0)
    )

    assert result.historical_from == date(2026, 8, 1)
    assert result.historical_to == date(2026, 8, 10)
    assert result.intraday_trade_date is None
    assert result.last_completed_bar_start is None


def test_request_ending_before_today_uses_only_historical_range() -> None:
    schedule = _schedule(as_of=_instant(11, 9, 0), through=10)
    result = plan_open_month(
        date(2026, 8, 5), date(2026, 8, 10), schedule, _instant(11, 12, 0)
    )

    assert result.historical_from == date(2026, 8, 1)
    assert result.historical_to == date(2026, 8, 10)
    assert result.intraday_trade_date is None


@pytest.mark.parametrize(
    ("requested_from", "requested_to", "schedule", "invocation"),
    [
        (date(2026, 7, 31), date(2026, 8, 11), None, _instant(11, 12, 0)),
        (date(2026, 8, 1), date(2026, 8, 12), None, _instant(11, 12, 0)),
        (date(2026, 8, 12), date(2026, 8, 11), None, _instant(11, 12, 0)),
        (date(2026, 8, 1), date(2026, 8, 11), None, datetime(2026, 8, 11)),
    ],
)
def test_planner_rejects_cross_month_future_reversed_or_naive_requests(
    requested_from: date,
    requested_to: date,
    schedule: None,
    invocation: datetime,
) -> None:
    del schedule
    with pytest.raises(ValueError):
        plan_open_month(
            requested_from,
            requested_to,
            _schedule(as_of=_instant(11, 9, 0)),
            invocation,
        )


def test_planner_rejects_schedule_not_known_at_invocation() -> None:
    with pytest.raises(ValueError):
        plan_open_month(
            date(2026, 8, 1),
            date(2026, 8, 11),
            _schedule(as_of=_instant(11, 12, 1)),
            _instant(11, 12, 0),
        )


def test_schedule_requires_exact_calendar_classification_and_order() -> None:
    base = {
        "schema_version": SCHEDULE_SCHEMA_VERSION_V3,
        "source": "authoritative-nse-calendar",
        "source_release": "release",
        "as_of": _instant(11, 9, 0),
        "timezone": "Asia/Kolkata",
        "covered_from": date(2026, 8, 10),
        "covered_to": date(2026, 8, 11),
    }
    with pytest.raises(ValueError):
        OpenMonthScheduleV1(sessions=(_session(11),), closures=(), **base)
    with pytest.raises(ValueError):
        OpenMonthScheduleV1(sessions=(_session(11), _session(10)), closures=(), **base)
    with pytest.raises(ValueError):
        OpenMonthScheduleV1(
            sessions=(_session(10), _session(11)),
            closures=(ScheduleClosure(date(2026, 8, 11), "DUPLICATE"),),
            **base,
        )


def test_schedule_canonical_bytes_and_digest_are_stable() -> None:
    schedule = _schedule(as_of=_instant(11, 9, 0))
    encoded = canonical_open_month_schedule_bytes(schedule)

    assert encoded == canonical_open_month_schedule_bytes(schedule)
    assert open_month_schedule_digest(schedule) == hashlib.sha256(encoded).hexdigest()
    assert b"authoritative-nse-calendar" in encoded


def test_open_month_schedule_is_the_exact_retained_v3_schedule_evidence() -> None:
    schedule = _schedule(as_of=_instant(11, 9, 0))
    retained = ExpectedSessionSchedule(
        schema_version=SCHEDULE_SCHEMA_VERSION_V3,
        source=schedule.source,
        source_release=schedule.source_release,
        as_of=schedule.as_of,
        timezone=schedule.timezone,
        covered_from=schedule.covered_from,
        covered_to=schedule.covered_to,
        sessions=schedule.sessions,
        closures=schedule.closures,
    )

    converted = open_month_schedule_from_evidence(retained)

    assert converted == schedule
    assert canonical_open_month_schedule_bytes(converted) == canonical_schedule_bytes(
        retained
    )


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"source": ""},
        {"source_release": "token\nvalue"},
        {"timezone": "UTC"},
        {"covered_from": date(2026, 9, 1)},
        {"covered_to": date(2026, 8, 31)},
    ],
)
def test_schedule_rejects_malformed_contract_fields(change: dict[str, object]) -> None:
    values = {
        "schema_version": SCHEDULE_SCHEMA_VERSION_V3,
        "source": "authoritative-nse-calendar",
        "source_release": "release",
        "as_of": _instant(11, 9, 0),
        "timezone": "Asia/Kolkata",
        "covered_from": date(2026, 8, 11),
        "covered_to": date(2026, 8, 11),
        "sessions": (_session(11),),
        "closures": (),
    }
    values.update(change)
    with pytest.raises(ValueError):
        OpenMonthScheduleV1(**values)  # type: ignore[arg-type]


def test_plan_rejects_unpaired_ranges_bad_digest_and_invalid_intraday_values() -> None:
    values = {
        "requested_from": date(2026, 8, 1),
        "requested_to": date(2026, 8, 11),
        "month_start": date(2026, 8, 1),
        "invocation": _instant(11, 10),
        "historical_from": None,
        "historical_to": None,
        "intraday_trade_date": None,
        "last_completed_bar_start": None,
        "active_session_complete": False,
        "schedule_digest": "a" * 64,
    }
    for change in (
        {"schedule_digest": "not-a-digest"},
        {"historical_from": date(2026, 8, 1)},
        {"historical_from": date(2026, 8, 2), "historical_to": date(2026, 8, 1)},
        {"intraday_trade_date": date(2026, 8, 11)},
        {"intraday_trade_date": date(2026, 8, 11), "last_completed_bar_start": "bad"},
    ):
        with pytest.raises(ValueError, match="invalid open-month plan"):
            OpenMonthPlanV1(**(values | change))  # type: ignore[arg-type]


def test_schedule_helpers_reject_wrong_types_and_non_v3_evidence() -> None:
    for helper in (canonical_open_month_schedule_bytes, open_month_schedule_digest):
        with pytest.raises(ValueError, match="invalid open-month schedule"):
            helper(object())

    retained = ExpectedSessionSchedule(
        schema_version=2,
        source="authoritative-nse-calendar",
        source_release="release",
        as_of=_instant(11, 17),
        timezone="Asia/Kolkata",
        covered_from=date(2026, 8, 11),
        covered_to=date(2026, 8, 11),
        sessions=(_session(11),),
        closures=(),
    )
    with pytest.raises(ValueError, match="invalid open-month schedule evidence"):
        open_month_schedule_from_evidence(retained)
