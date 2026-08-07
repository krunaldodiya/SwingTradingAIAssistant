from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
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
    ValidationEvidence,
    ValidationReason,
)


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
        date(2026, 1, 1),
        date(2026, 1, 31),
    )


def _session(
    trade_date: date = date(2026, 1, 2),
    open_minute: int = 0,
    minutes: int = 3,
) -> ScheduleSession:
    opening = datetime(2026, 1, trade_date.day, 3, 45, tzinfo=UTC)
    opening += timedelta(minutes=open_minute)
    return ScheduleSession(
        trade_date,
        opening,
        opening + timedelta(minutes=minutes),
        "regular",
    )


def _schedule(
    *sessions: ScheduleSession,
    source_release: str = "2026-01",
    covered_to: date = date(2026, 1, 31),
) -> ExpectedSessionSchedule:
    return ExpectedSessionSchedule(
        1,
        "nse",
        source_release,
        datetime(2026, 2, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 1, 1),
        covered_to,
        sessions or (_session(),),
    )


def _resolved(schedule: ExpectedSessionSchedule) -> ScheduleEvidenceResult:
    value = canonical_schedule_bytes(schedule)
    return ScheduleEvidenceResult(
        ScheduleOutcome.RESOLVED,
        ScheduleFailureCode.NONE,
        schedule,
        value,
        schedule_digest(schedule),
        "calendar-schedules/sha256/ignored.json",
    )


def _candle(ts: datetime, **overrides: object) -> CanonicalCandle:
    values: dict[str, object] = {
        "provider": "upstox",
        "instrument_key": "NSE_EQ|ID",
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
        "ts": ts,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 10,
        "oi": None,
        "ingested_at": datetime(2026, 2, 1, tzinfo=UTC),
        "source_version": "upstox-historical-v3",
        "adjustment_state": "raw",
    }
    values.update(overrides)
    return CanonicalCandle(**values)  # type: ignore[arg-type]


def _session_candles(session: ScheduleSession) -> list[CanonicalCandle]:
    return [
        _candle(session.open_at + timedelta(minutes=offset))
        for offset in range(
            int((session.close_at - session.open_at).total_seconds() // 60)
        )
    ]


def test_validates_one_canonical_month_against_immutable_schedule_evidence() -> None:
    schedule = _schedule()
    candles = _session_candles(schedule.sessions[0])

    evidence = EquityMonthValidationPolicy("nse-equity-month@v1").validate(
        _plan(),
        candles,
        _resolved(schedule),
        raw_row_count=4,
        normalized_row_count=3,
    )

    assert evidence.plan == _plan()
    assert evidence.policy_version == (
        "nse-equity-month@v1+sessions-sha256:" + schedule_digest(schedule)
    )
    assert evidence.schedule_digest == schedule_digest(schedule)
    assert evidence.raw_row_count == 4
    assert evidence.normalized_row_count == 3
    assert evidence.row_count == 3
    assert evidence.actual_from_ts == candles[0].ts
    assert evidence.actual_to_ts == candles[-1].ts
    assert evidence.coverage_passed is True
    assert evidence.quality_passed is True
    assert evidence.reason is ValidationReason.NONE
    assert evidence.failure_reason is ValidationReason.NONE
    with pytest.raises(FrozenInstanceError):
        evidence.row_count = 0  # type: ignore[misc]


def test_raw_schedule_is_rejected_as_unverified_child_d_evidence() -> None:
    schedule = _schedule()
    evidence = EquityMonthValidationPolicy("nse-equity-month@v1").validate(
        _plan(), _session_candles(schedule.sessions[0]), schedule, 3, 3
    )

    assert evidence.coverage_passed is False
    assert evidence.quality_passed is False
    assert evidence.reason is ValidationReason.SCHEDULE_RETAINED_BYTES_INVALID


def test_resolved_schedule_digest_mismatch_fails_closed() -> None:
    schedule = _schedule()
    resolved = _resolved(schedule)
    malformed = ScheduleEvidenceResult(
        resolved.outcome,
        resolved.failure_code,
        resolved.schedule,
        resolved.canonical_bytes,
        "0" * 64,
        resolved.relative_path,
    )

    evidence = EquityMonthValidationPolicy("nse-equity-month@v1").validate(
        _plan(), _session_candles(schedule.sessions[0]), malformed, 3, 3
    )

    assert evidence.reason is ValidationReason.SCHEDULE_DIGEST_MISMATCH
    assert evidence.schedule_digest == "0" * 64


def test_failed_schedule_resolution_without_digest_is_missing_evidence() -> None:
    failed = ScheduleEvidenceResult(
        ScheduleOutcome.FAILED,
        ScheduleFailureCode.SCHEDULE_UNSUPPORTED,
        None,
        None,
        None,
        message="schedule evidence unsupported",
    )

    evidence = EquityMonthValidationPolicy("nse-equity-month@v1").validate(
        _plan(), [], failed, 0, 0
    )

    assert evidence.reason is ValidationReason.SCHEDULE_DIGEST_MISSING


@pytest.mark.parametrize(
    "bad_policy",
    [
        "",
        " nse-equity-month@v1",
        "nse-equity-month",
        "@v1",
        "nse-equity-month@",
        "nse-equity-month@@v1",
        "nse-equity-month@v1+sessions-sha256:" + "a" * 63,
        "nse-equity-month@v1+sessions-sha256:" + "A" * 64,
        "nse-equity-month@v1++sessions-sha256:" + "a" * 64,
        "nse-equity-month@v1+sessions-sha256:" + "a" * 64 + "+extra",
        1,
    ],
)
def test_policy_version_is_validated_at_construction(bad_policy: object) -> None:
    with pytest.raises(ValueError, match="policy_version"):
        EquityMonthValidationPolicy(bad_policy)  # type: ignore[arg-type]


def test_missing_expected_session_bar_fails_coverage_without_inventing_a_bar() -> None:
    schedule = _schedule()
    candles = _session_candles(schedule.sessions[0])[:-1]

    evidence = EquityMonthValidationPolicy("nse-equity-month@v1").validate(
        _plan(), candles, _resolved(schedule), raw_row_count=2, normalized_row_count=2
    )

    assert evidence.coverage_passed is False
    assert evidence.quality_passed is True
    assert evidence.reason is ValidationReason.COVERAGE_EXPECTED_BAR_MISSING
    assert evidence.row_count == 2
    assert evidence.actual_to_ts == candles[-1].ts


def test_off_session_bar_fails_coverage_even_when_rows_cover_the_session() -> None:
    schedule = _schedule()
    candles = _session_candles(schedule.sessions[0])
    candles.append(_candle(schedule.sessions[0].close_at))

    evidence = EquityMonthValidationPolicy("nse-equity-month@v1").validate(
        _plan(), candles, _resolved(schedule), raw_row_count=4, normalized_row_count=4
    )

    assert evidence.coverage_passed is False
    assert evidence.reason is ValidationReason.COVERAGE_OFF_SESSION_BAR


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"high": 98.0}, ValidationReason.QUALITY_INVALID_OHLC),
        ({"high": float("nan")}, ValidationReason.QUALITY_INVALID_OHLC),
        ({"volume": -1}, ValidationReason.QUALITY_INVALID_VOLUME),
        ({"volume": True}, ValidationReason.QUALITY_INVALID_VOLUME),
    ],
)
def test_invalid_quality_is_reported_as_stable_evidence(
    overrides: dict[str, object], reason: ValidationReason
) -> None:
    schedule = _schedule()
    candles = _session_candles(schedule.sessions[0])
    object.__setattr__(
        candles[0], next(iter(overrides)), next(iter(overrides.values()))
    )

    evidence = EquityMonthValidationPolicy("nse-equity-month@v1").validate(
        _plan(), candles, _resolved(schedule), raw_row_count=3, normalized_row_count=3
    )

    assert evidence.coverage_passed is True
    assert evidence.quality_passed is False
    assert evidence.reason is reason


def test_schedule_byte_mismatch_fails_closed_without_current_calendar_substitution() -> (
    None
):
    schedule = _schedule()
    other = _schedule(source_release="different")
    resolved = _resolved(schedule)
    mismatched = ScheduleEvidenceResult(
        resolved.outcome,
        resolved.failure_code,
        other,
        resolved.canonical_bytes,
        resolved.digest,
        resolved.relative_path,
    )

    evidence = EquityMonthValidationPolicy("nse-equity-month@v1").validate(
        _plan(),
        _session_candles(schedule.sessions[0]),
        mismatched,
        raw_row_count=3,
        normalized_row_count=3,
    )

    assert evidence.coverage_passed is False
    assert evidence.quality_passed is False
    assert evidence.reason is ValidationReason.SCHEDULE_RETAINED_BYTES_INVALID


def test_missing_schedule_digest_fails_closed() -> None:
    evidence = EquityMonthValidationPolicy("nse-equity-month@v1").validate(
        _plan(), [], None, raw_row_count=0, normalized_row_count=0
    )

    assert evidence.coverage_passed is False
    assert evidence.quality_passed is False
    assert evidence.reason is ValidationReason.SCHEDULE_DIGEST_MISSING


def test_schedule_that_does_not_cover_the_full_month_fails_closed() -> None:
    schedule = _schedule(covered_to=date(2026, 1, 30))
    evidence = EquityMonthValidationPolicy("nse-equity-month@v1").validate(
        _plan(),
        _session_candles(schedule.sessions[0]),
        _resolved(schedule),
        raw_row_count=3,
        normalized_row_count=3,
    )

    assert evidence.coverage_passed is False
    assert evidence.reason is ValidationReason.SCHEDULE_COVERAGE_INCOMPLETE


def test_policy_version_bound_to_a_different_schedule_digest_fails_closed() -> None:
    schedule = _schedule()
    other_digest = schedule_digest(_schedule(source_release="different"))
    evidence = EquityMonthValidationPolicy(
        "nse-equity-month@v1+sessions-sha256:" + other_digest
    ).validate(
        _plan(),
        _session_candles(schedule.sessions[0]),
        _resolved(schedule),
        raw_row_count=3,
        normalized_row_count=3,
    )

    assert evidence.coverage_passed is False
    assert evidence.reason is ValidationReason.SCHEDULE_DIGEST_MISMATCH


def _direct_evidence(**overrides: object) -> ValidationEvidence:
    values: dict[str, object] = {
        "plan": _plan(),
        "policy_version": "nse-equity-month@v1+sessions-sha256:" + "a" * 64,
        "schedule_digest": "a" * 64,
        "raw_row_count": 3,
        "normalized_row_count": 3,
        "row_count": 3,
        "actual_from_ts": datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        "actual_to_ts": datetime(2026, 1, 2, 3, 47, tzinfo=UTC),
        "coverage_passed": True,
        "quality_passed": True,
        "reason": ValidationReason.NONE,
    }
    values.update(overrides)
    return ValidationEvidence(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"schedule_digest": None},
        {"policy_version": "nse-equity-month@v1"},
        {"policy_version": "nse-equity-month@v1+sessions-sha256:" + "b" * 64},
        {"reason": ValidationReason.SCHEDULE_DIGEST_MISSING},
        {
            "coverage_passed": False,
            "reason": ValidationReason.QUALITY_INVALID_OHLC,
        },
        {
            "quality_passed": True,
            "reason": ValidationReason.COVERAGE_EXPECTED_BAR_MISSING,
        },
    ],
)
def test_direct_validation_evidence_rejects_unsupported_success_or_reason(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="invalid validation evidence"):
        _direct_evidence(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"row_count": 0},
        {"normalized_row_count": 2},
        {"actual_from_ts": None},
        {"actual_to_ts": None},
        {
            "actual_from_ts": datetime(2026, 1, 2, 3, 48, tzinfo=UTC),
            "actual_to_ts": datetime(2026, 1, 2, 3, 47, tzinfo=UTC),
        },
    ],
)
def test_direct_validation_evidence_rejects_row_count_timestamp_inconsistency(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="invalid validation evidence"):
        _direct_evidence(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "raw_row_count": 0,
            "normalized_row_count": 0,
            "row_count": 0,
            "actual_from_ts": None,
            "actual_to_ts": None,
        },
        {
            "actual_from_ts": datetime(
                2026, 1, 2, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30))
            ),
            "actual_to_ts": datetime(
                2026, 1, 2, 9, 17, tzinfo=timezone(timedelta(hours=5, minutes=30))
            ),
        },
        {
            "actual_from_ts": datetime(2026, 1, 2, 3, 45, 1, tzinfo=UTC),
            "actual_to_ts": datetime(2026, 1, 2, 3, 47, 1, tzinfo=UTC),
        },
        {
            "actual_from_ts": datetime(2030, 1, 2, 3, 45, tzinfo=UTC),
            "actual_to_ts": datetime(2030, 1, 2, 3, 47, tzinfo=UTC),
        },
        {
            "raw_row_count": 65_537,
            "normalized_row_count": 65_537,
            "row_count": 65_537,
            "actual_from_ts": datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            "actual_to_ts": datetime(2026, 1, 31, 23, 59, tzinfo=UTC),
        },
        {
            "raw_row_count": 4,
            "normalized_row_count": 4,
            "row_count": 4,
            "actual_from_ts": datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
            "actual_to_ts": datetime(2026, 1, 2, 3, 47, tzinfo=UTC),
        },
    ],
)
def test_direct_validation_evidence_rejects_invalid_success_invariants(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="invalid validation evidence"):
        _direct_evidence(**overrides)


@pytest.mark.parametrize(("raw_count", "normalized_count"), [(2, 3), (3, 2), (True, 3)])
def test_inconsistent_row_counts_are_rejected_at_the_validation_boundary(
    raw_count: object, normalized_count: object
) -> None:
    schedule = _schedule()
    with pytest.raises(ValueError, match="row counts"):
        EquityMonthValidationPolicy("nse-equity-month@v1").validate(
            _plan(),
            _session_candles(schedule.sessions[0]),
            _resolved(schedule),
            raw_row_count=raw_count,  # type: ignore[arg-type]
            normalized_row_count=normalized_count,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("underlying_id", "NSE_INDEX:NIFTY 50"),
        ("expiry", date(2026, 1, 29)),
        ("strike", 100.0),
        ("option_type", "CE"),
        ("oi", 1.0),
    ],
)
def test_nse_equity_boundary_rejects_derivative_metadata(
    field: str, value: object
) -> None:
    schedule = _schedule()
    candles = _session_candles(schedule.sessions[0])
    candles[0] = _candle(candles[0].ts, **{field: value})

    with pytest.raises(ValueError, match="NSE equity"):
        EquityMonthValidationPolicy("nse-equity-month@v1").validate(
            _plan(), candles, _resolved(schedule), 3, 3
        )


def test_invalid_plan_and_candle_boundaries_are_rejected() -> None:
    schedule = _schedule()
    bad_plan = _plan()
    object.__setattr__(bad_plan, "to_date", date(2026, 1, 30))
    with pytest.raises(ValueError, match="canonical calendar month"):
        EquityMonthValidationPolicy("nse-equity-month@v1").validate(
            bad_plan, [], _resolved(schedule), 0, 0
        )
    with pytest.raises(ValueError, match="exact CanonicalCandle"):
        EquityMonthValidationPolicy("nse-equity-month@v1").validate(
            _plan(),
            [object()],
            _resolved(schedule),
            1,
            1,  # type: ignore[list-item]
        )
