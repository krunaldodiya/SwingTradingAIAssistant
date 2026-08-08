"""ARK-75 characterization of coordinator admission before side effects."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.historical import RetryPolicy
from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionReport,
    IngestionRunOutcome,
    PartitionOutcome,
    PartitionResult,
    RunFailureCode,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleSession,
)


def _instrument() -> Instrument:
    return Instrument(
        "NSE_EQ|RELIANCE",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "INE002A01018",
    )


def _next_month_start(year: int, month: int) -> datetime:
    next_year = year + (month == 12)
    next_month = 1 if month == 12 else month + 1
    return datetime(next_year, next_month, 1, tzinfo=UTC)


def _complete_v2_schedule(year: int, month: int) -> ExpectedSessionSchedule:
    covered_from = date(year, month, 1)
    covered_to = date(year, month, monthrange(year, month)[1])
    session_date = date(year, month, min(2, covered_to.day))
    session = ScheduleSession(
        session_date,
        datetime(year, month, session_date.day, 3, 45, tzinfo=UTC),
        datetime(year, month, session_date.day, 3, 46, tzinfo=UTC),
        "regular",
    )
    closures = tuple(
        ScheduleClosure(day, "nse-source")
        for day in (
            covered_from.fromordinal(index)
            for index in range(covered_from.toordinal(), covered_to.toordinal() + 1)
        )
        if day != session_date
    )
    return ExpectedSessionSchedule(
        2,
        "nse",
        f"{year}-{month:02d}",
        _next_month_start(year, month),
        "Asia/Kolkata",
        covered_from,
        covered_to,
        (session,),
        closures,
    )


def _valid_v1_schedule() -> ExpectedSessionSchedule:
    session = ScheduleSession(
        date(2024, 1, 2),
        datetime(2024, 1, 2, 3, 45, tzinfo=UTC),
        datetime(2024, 1, 2, 3, 46, tzinfo=UTC),
        "regular",
    )
    return ExpectedSessionSchedule(
        1,
        "nse",
        "2024-01",
        datetime(2024, 2, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2024, 1, 1),
        date(2024, 1, 31),
        (session,),
    )


def _incomplete_v2_schedule() -> ExpectedSessionSchedule:
    complete = _complete_v2_schedule(2024, 1)
    return ExpectedSessionSchedule(
        complete.schema_version,
        complete.source,
        complete.source_release,
        complete.as_of,
        complete.timezone,
        complete.covered_from,
        complete.covered_to,
        complete.sessions,
        complete.closures[1:],
    )


@dataclass
class _AdmissionCallAudit:
    calls: list[str] = field(default_factory=list)

    def forbidden(self, name: str) -> Callable[..., object]:
        def call(*_args: object, **_kwargs: object) -> object:
            self.calls.append(name)
            raise AssertionError(f"{name} must remain inactive during admission")

        return call


class _NeverOpenProvider:
    def __init__(self, audit: _AdmissionCallAudit) -> None:
        self._audit = audit

    def open(self) -> object:
        self._audit.calls.append("provider_session_or_http")
        raise AssertionError("provider session must remain unopened during admission")


class _NeverUseLimiter:
    def __init__(self, audit: _AdmissionCallAudit) -> None:
        self._audit = audit

    def acquire(self, *_args: object, **_kwargs: object) -> object:
        self._audit.calls.append("limiter_acquire")
        raise AssertionError("limiter acquire must remain inactive during admission")

    def defer_for(self, *_args: object, **_kwargs: object) -> object:
        self._audit.calls.append("limiter_defer")
        raise AssertionError("limiter defer must remain inactive during admission")


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _root_listing(root: Path) -> tuple[str, ...]:
    return tuple(sorted(path.relative_to(root).as_posix() for path in root.rglob("*")))


@pytest.mark.parametrize(
    (
        "interval",
        "from_date",
        "to_date",
        "schedule_factory",
        "failure_code",
        "planned_count",
    ),
    [
        pytest.param(
            "5m",
            date(2024, 1, 1),
            date(2024, 1, 31),
            lambda: _complete_v2_schedule(2024, 1),
            RunFailureCode.UNSUPPORTED_INTERVAL,
            0,
            id="unsupported-interval",
        ),
        pytest.param(
            "1m",
            date(2024, 2, 1),
            date(2024, 2, 7),
            lambda: _complete_v2_schedule(2024, 2),
            RunFailureCode.PARTITION_NOT_CLOSED,
            1,
            id="open-current-month",
        ),
        pytest.param(
            "1m",
            date(2024, 1, 1),
            date(2024, 1, 31),
            _valid_v1_schedule,
            RunFailureCode.SCHEDULE_UNSUPPORTED,
            1,
            id="valid-object-v1-schedule",
        ),
        pytest.param(
            "1m",
            date(2024, 1, 1),
            date(2024, 1, 31),
            _incomplete_v2_schedule,
            RunFailureCode.SCHEDULE_UNSUPPORTED,
            1,
            id="incomplete-v2-schedule",
        ),
    ],
)
def test_coordinator_rejects_admission_cases_before_every_later_dependency(
    tmp_path: Path,
    interval: str,
    from_date: date,
    to_date: date,
    schedule_factory: Callable[[], ExpectedSessionSchedule],
    failure_code: RunFailureCode,
    planned_count: int,
) -> None:
    """D01/D02 retain the established preflight report shape without side effects."""
    audit = _AdmissionCallAudit()
    before = _root_listing(tmp_path)
    coordinator = IngestionCoordinator(
        session_factory=_NeverOpenProvider(audit),  # type: ignore[arg-type]
        limiter=_NeverUseLimiter(audit),  # type: ignore[arg-type]
        clock=_FixedClock(datetime(2024, 2, 15, tzinfo=UTC)),
        sleeper=audit.forbidden("sleeper"),  # type: ignore[arg-type]
        lease_acquirer=audit.forbidden("lease"),  # type: ignore[arg-type]
        catalog_factory=audit.forbidden("catalog"),  # type: ignore[arg-type]
        schedule_store_factory=audit.forbidden("schedule_store"),  # type: ignore[arg-type]
        recovery_observer_factory=audit.forbidden("recovery"),  # type: ignore[arg-type]
        lifecycle_executor_factory=audit.forbidden("lifecycle"),  # type: ignore[arg-type]
    )

    report = coordinator.run(
        IngestionCommand(
            _instrument(),
            from_date,
            to_date,
            interval,
            tmp_path,
            schedule_factory(),
            "nse-equity-month@v1",
            RetryPolicy(),
            1,
        )
    )

    assert type(report) is IngestionReport
    assert report.outcome is IngestionRunOutcome.REJECTED
    assert report.failure_code is failure_code
    assert report.planned_count == planned_count
    assert len(report.results) == planned_count
    assert report.provider_attempt_count == 0
    assert (
        report.skipped_count
        == report.locally_recovered_count
        == report.verified_count
        == report.failed_count
        == report.cancelled_count
        == 0
    )
    assert report.not_attempted_count == planned_count
    assert all(type(result) is PartitionResult for result in report.results)
    assert all(result.error_code is None for result in report.results)
    assert all(result.final_manifest is None for result in report.results)
    assert all(result.provider_attempts == 0 for result in report.results)
    assert all(
        result.outcome is PartitionOutcome.NOT_ATTEMPTED for result in report.results
    )
    assert audit.calls == []
    assert _root_listing(tmp_path) == before
