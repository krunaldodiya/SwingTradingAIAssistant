from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from swing_trading_ai_assistant.market_data.open_month import (
    OpenMonthScheduleV1,
    plan_open_month,
)
from swing_trading_ai_assistant.market_data.provisional_validation import (
    ProvisionalValidationCodeV1,
    ProvisionalValidationFailureV1,
    ProvisionalValidationV1,
    validate_provisional_advance,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V3,
    ScheduleClosure,
    ScheduleSession,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle

IST = timezone(timedelta(hours=5, minutes=30))


def _local(hour: int, minute: int, *, day: int = 11) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=IST)


def _schedule(*, close_minute: int = 20) -> OpenMonthScheduleV1:
    sessions = (
        ScheduleSession(
            date(2026, 8, 10),
            _local(9, 15, day=10),
            _local(9, 18, day=10),
            "TEST_SESSION",
        ),
        ScheduleSession(
            date(2026, 8, 11),
            _local(9, 15),
            _local(9, close_minute),
            "TEST_SESSION",
        ),
    )
    closures = tuple(
        ScheduleClosure(date(2026, 8, day), "EXCHANGE_CLOSED") for day in range(1, 10)
    )
    return OpenMonthScheduleV1(
        SCHEDULE_SCHEMA_VERSION_V3,
        "authoritative-test-calendar",
        "release-v1",
        _local(9, 0),
        "Asia/Kolkata",
        date(2026, 8, 1),
        date(2026, 8, 11),
        sessions,
        closures,
    )


def _plan(invocation: datetime):
    return plan_open_month(date(2026, 8, 1), date(2026, 8, 11), _schedule(), invocation)


def _candle(ts: datetime, close: float = 100.5, *, source: str = "source-v3"):
    return CanonicalCandle(
        provider="upstox",
        instrument_key="NSE_EQ|INE002A01018",
        security_id="INE002A01018",
        symbol="RELIANCE",
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        underlying_id=None,
        expiry=None,
        strike=None,
        option_type=None,
        interval="1m",
        ts=ts,
        open=100.0,
        high=max(101.0, close),
        low=99.0,
        close=close,
        volume=10,
        oi=None,
        ingested_at=datetime(2026, 8, 11, 10, tzinfo=UTC),
        source_version=source,
        adjustment_state="raw",
    )


def _history() -> tuple[CanonicalCandle, ...]:
    return tuple(_candle(_local(9, minute, day=10)) for minute in range(15, 18))


def _today(through: int) -> tuple[CanonicalCandle, ...]:
    return tuple(
        _candle(_local(9, minute), source="upstox-intraday-v3")
        for minute in range(15, through + 1)
    )


def test_first_refresh_combines_prior_history_and_current_completed_minutes() -> None:
    plan = _plan(_local(9, 18))
    result = validate_provisional_advance(_schedule(), plan, (), _history(), _today(17))

    assert result.complete_to_target is True
    assert result.missing_count == 0
    assert result.actual_cutoff == _local(9, 17).astimezone(UTC)
    assert result.target_cutoff == _local(9, 17).astimezone(UTC)
    assert result.session_complete is False
    assert result.appended_count == 6
    assert len(result.candles) == 6


def test_second_refresh_reuses_prefix_and_appends_only_new_completed_minutes() -> None:
    first = validate_provisional_advance(
        _schedule(), _plan(_local(9, 18)), (), _history(), _today(17)
    )
    second = validate_provisional_advance(
        _schedule(), _plan(_local(9, 20)), first.candles, (), _today(19)
    )

    assert second.complete_to_target is True
    assert second.appended_count == 2
    assert second.candles[:6] == first.candles
    assert second.actual_cutoff == _local(9, 19).astimezone(UTC)
    assert second.session_complete is True


def test_identical_cutoff_rerun_is_zero_append_idempotent() -> None:
    first = validate_provisional_advance(
        _schedule(), _plan(_local(9, 18)), (), _history(), _today(17)
    )
    rerun = validate_provisional_advance(
        _schedule(), _plan(_local(9, 18)), first.candles, (), _today(17)
    )

    assert rerun.complete_to_target is True
    assert rerun.appended_count == 0
    assert rerun.candles == first.candles


def test_in_progress_provider_candle_after_target_is_discarded() -> None:
    result = validate_provisional_advance(
        _schedule(),
        _plan(
            _local(
                9,
                18,
            ).replace(second=30)
        ),
        (),
        _history(),
        _today(18),
    )

    assert result.target_cutoff == _local(9, 17).astimezone(UTC)
    assert result.actual_cutoff == result.target_cutoff
    assert result.discarded_unfinished_count == 1
    assert all(candle.ts <= result.target_cutoff for candle in result.candles)


def test_changed_previously_persisted_bar_fails_without_replacement() -> None:
    first = validate_provisional_advance(
        _schedule(), _plan(_local(9, 18)), (), _history(), _today(17)
    )
    changed = tuple(
        replace(value, close=100.75)
        if value.ts == _local(9, 16).astimezone(UTC)
        else value
        for value in _today(19)
    )

    with pytest.raises(ProvisionalValidationFailureV1) as raised:
        validate_provisional_advance(
            _schedule(), _plan(_local(9, 20)), first.candles, (), changed
        )

    assert raised.value.code is ProvisionalValidationCodeV1.PREFIX_CONFLICT


def test_missing_middle_bar_is_partial_even_when_latest_bar_exists() -> None:
    today = tuple(
        value for value in _today(19) if value.ts != _local(9, 17).astimezone(UTC)
    )
    result = validate_provisional_advance(
        _schedule(), _plan(_local(9, 20)), (), _history(), today
    )

    assert result.complete_to_target is False
    assert result.missing_count == 3
    assert result.actual_cutoff == _local(9, 16).astimezone(UTC)
    assert result.candles[-1].ts == result.actual_cutoff
    assert result.session_complete is False


def test_off_session_and_wrong_identity_fail_closed() -> None:
    off_session = _candle(_local(9, 14), source="upstox-intraday-v3")
    with pytest.raises(ProvisionalValidationFailureV1) as raised:
        validate_provisional_advance(
            _schedule(),
            _plan(_local(9, 18)),
            (),
            _history(),
            (off_session, *_today(17)),
        )
    assert raised.value.code is ProvisionalValidationCodeV1.OFF_SESSION_BAR

    wrong = replace(_today(17)[0], security_id="OTHER")
    with pytest.raises(ProvisionalValidationFailureV1) as raised:
        validate_provisional_advance(
            _schedule(), _plan(_local(9, 18)), (), _history(), (wrong, *_today(17)[1:])
        )
    assert raised.value.code is ProvisionalValidationCodeV1.IDENTITY_MISMATCH


def test_schedule_digest_and_plan_must_match() -> None:
    changed_schedule = replace(_schedule(), source_release="release-v2")
    with pytest.raises(ProvisionalValidationFailureV1) as raised:
        validate_provisional_advance(
            changed_schedule, _plan(_local(9, 18)), (), _history(), _today(17)
        )
    assert raised.value.code is ProvisionalValidationCodeV1.SCHEDULE_MISMATCH


def test_inputs_are_bounded_and_exact_typed() -> None:
    with pytest.raises(ProvisionalValidationFailureV1) as raised:
        validate_provisional_advance(
            _schedule(),
            _plan(_local(9, 18)),
            (),
            (),
            (object(),),  # type: ignore[arg-type]
        )
    assert raised.value.code is ProvisionalValidationCodeV1.INVALID_INPUT


def test_validation_rejects_plan_target_mismatch_and_non_tuple_inputs() -> None:
    plan = replace(_plan(_local(9, 18)), last_completed_bar_start=_local(9, 14))
    with pytest.raises(ProvisionalValidationFailureV1) as raised:
        validate_provisional_advance(_schedule(), plan, (), _history(), _today(17))
    assert raised.value.code is ProvisionalValidationCodeV1.SCHEDULE_MISMATCH

    with pytest.raises(ProvisionalValidationFailureV1) as raised:
        validate_provisional_advance(_schedule(), _plan(_local(9, 18)), [], (), ())
    assert raised.value.code is ProvisionalValidationCodeV1.INVALID_INPUT


def test_validation_value_object_rejects_inconsistent_cutoffs_and_completion() -> None:
    base = {
        "candles": (),
        "target_cutoff": None,
        "actual_cutoff": None,
        "complete_to_target": False,
        "session_complete": False,
        "missing_count": 0,
        "appended_count": 0,
        "discarded_unfinished_count": 0,
        "schedule_digest": "a" * 64,
    }
    for change in (
        {"session_complete": True},
        {"target_cutoff": "bad"},
        {"actual_cutoff": _local(9, 15)},
    ):
        with pytest.raises(ValueError, match="invalid provisional validation"):
            ProvisionalValidationV1(**(base | change))  # type: ignore[arg-type]

    candle = _today(15)[0]
    with pytest.raises(ValueError, match="invalid provisional validation"):
        ProvisionalValidationV1(
            **(
                base
                | {
                    "candles": (candle,),
                    "target_cutoff": candle.ts,
                    "actual_cutoff": _local(9, 14).astimezone(UTC),
                }
            )
        )


def test_validation_rejects_wrong_schedule_type_and_requires_month_history() -> None:
    with pytest.raises(ProvisionalValidationFailureV1) as raised:
        validate_provisional_advance(object(), _plan(_local(9, 18)), (), (), ())
    assert raised.value.code is ProvisionalValidationCodeV1.INVALID_INPUT

    today_only = plan_open_month(
        date(2026, 8, 11), date(2026, 8, 11), _schedule(), _local(9, 18)
    )
    result = validate_provisional_advance(_schedule(), today_only, (), (), _today(17))
    assert result.complete_to_target is False
    assert result.missing_count == 6
