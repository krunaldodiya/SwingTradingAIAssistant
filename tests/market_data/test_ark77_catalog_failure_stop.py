"""ARK-77 characterization of catalog-construction failure containment."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from ark74_benchmark_fixture import benchmark_nse_eq_v1

from swing_trading_ai_assistant.market_data.historical import RetryPolicy
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
    ScheduleEvidenceResult,
    ScheduleFailureCode,
    ScheduleOutcome,
    canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)


class _FixedMarch2024Clock:
    def now(self) -> datetime:
        return datetime(2024, 3, 1, tzinfo=UTC)


@dataclass
class _DependencyAudit:
    calls: dict[str, int] = field(default_factory=dict)

    def record(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def forbidden(self, name: str) -> Callable[..., object]:
        def call(*_args: object, **_kwargs: object) -> object:
            self.record(name)
            raise AssertionError(f"{name} must remain inactive after catalog failure")

        return call


class _NeverUseProvider:
    def __init__(self, audit: _DependencyAudit) -> None:
        self._audit = audit

    def open(self) -> object:
        self._audit.record("provider_session_or_http")
        raise AssertionError("provider session and HTTP must remain inactive")


class _NeverUseLimiter:
    def __init__(self, audit: _DependencyAudit) -> None:
        self._audit = audit

    def acquire(self, *_args: object, **_kwargs: object) -> object:
        self._audit.record("limiter_acquire")
        raise AssertionError("limiter acquire must remain inactive")

    def defer_for(self, *_args: object, **_kwargs: object) -> object:
        self._audit.record("limiter_defer")
        raise AssertionError("limiter defer must remain inactive")


class _ExactRetainedScheduleStore:
    def __init__(
        self, schedule: ExpectedSessionSchedule, audit: _DependencyAudit
    ) -> None:
        self._schedule = schedule
        self._audit = audit

    def retain(
        self, command_schedule: ExpectedSessionSchedule
    ) -> ScheduleEvidenceResult:
        self._audit.record("schedule_retain")
        assert command_schedule == self._schedule
        canonical = canonical_schedule_bytes(self._schedule)
        digest = schedule_digest(self._schedule)
        return ScheduleEvidenceResult(
            ScheduleOutcome.RETAINED,
            ScheduleFailureCode.NONE,
            self._schedule,
            canonical,
            digest,
            f"calendar-schedules/sha256/{digest}.json",
        )


def _command(storage_root: Path) -> IngestionCommand:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    return IngestionCommand(
        fixture.instrument,
        date(2024, 2, 1),
        date(2024, 2, 29),
        "1m",
        storage_root,
        fixture.schedule,
        fixture.validation_policy,
        RetryPolicy(),
        1,
    )


def _root_snapshot(root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_catalog_construction_failure_stops_after_allowed_lease_and_schedule_boundary(
    tmp_path: Path,
) -> None:
    """D19 maps one catalog-construction failure without creating provider activity."""
    command = _command(tmp_path)
    initial_lease = StorageRootLease.try_acquire(tmp_path)
    assert initial_lease.outcome is LeaseOutcome.ACQUIRED
    assert initial_lease.lease is not None
    initial_lease.lease.close()
    before = _root_snapshot(tmp_path)
    assert before == (
        (
            ".ingestion.lock",
            (tmp_path / ".ingestion.lock").read_bytes(),
        ),
    )
    assert (
        hashlib.sha256(before[0][1]).hexdigest()
        == hashlib.sha256((tmp_path / ".ingestion.lock").read_bytes()).hexdigest()
    )

    audit = _DependencyAudit()

    def unavailable_catalog(_root: object) -> object:
        audit.record("catalog_construction")
        raise RuntimeError("private catalog connection detail")

    coordinator = IngestionCoordinator(
        session_factory=_NeverUseProvider(audit),  # type: ignore[arg-type]
        limiter=_NeverUseLimiter(audit),  # type: ignore[arg-type]
        clock=_FixedMarch2024Clock(),
        sleeper=audit.forbidden("sleeper"),  # type: ignore[arg-type]
        catalog_factory=unavailable_catalog,  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ExactRetainedScheduleStore(
            command.expected_sessions, audit
        ),  # type: ignore[arg-type]
        recovery_observer_factory=audit.forbidden("recovery_observer"),  # type: ignore[arg-type]
        lifecycle_executor_factory=audit.forbidden("lifecycle_executor"),  # type: ignore[arg-type]
    )

    report = coordinator.run(command)

    assert type(report) is IngestionReport
    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is RunFailureCode.CATALOG_UNAVAILABLE
    assert (
        report.planned_count == report.not_attempted_count == len(report.results) == 1
    )
    assert report.provider_attempt_count == 0
    assert (
        report.skipped_count
        == report.locally_recovered_count
        == report.verified_count
        == report.failed_count
        == report.cancelled_count
        == 0
    )
    assert len(report.results) == 1
    result = report.results[0]
    assert type(result) is PartitionResult
    assert result.outcome is PartitionOutcome.NOT_ATTEMPTED
    assert (
        result.plan
        == benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1)).partitions[0].plan
    )
    assert result.provider_attempts == 0
    assert result.ingestion_run_id is None
    assert result.final_manifest is None
    assert result.failure_category is None
    assert result.error_code is None
    assert audit.calls == {"schedule_retain": 1, "catalog_construction": 1}
    assert _root_snapshot(tmp_path) == before
