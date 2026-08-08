"""ARK-76 characterization of lease and unsafe-storage coordinator refusals."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
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
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    StorageRootLease,
)


class _FixedMarch2024Clock:
    def now(self) -> datetime:
        return datetime(2024, 3, 1, tzinfo=UTC)


@dataclass
class _DependencyAudit:
    calls: dict[str, int] = field(default_factory=dict[str, int])

    def record(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def forbidden(self, name: str) -> Callable[..., object]:
        def call(*_args: object, **_kwargs: object) -> object:
            self.record(name)
            raise AssertionError(f"{name} must remain inactive during refusal")

        return call


class _NeverUseProvider:
    def __init__(self, audit: _DependencyAudit) -> None:
        self._audit = audit

    def open(self) -> object:
        self._audit.record("provider_session")
        raise AssertionError("provider session must remain unopened during refusal")


class _NeverUseLimiter:
    def __init__(self, audit: _DependencyAudit) -> None:
        self._audit = audit

    def acquire(self, *_args: object, **_kwargs: object) -> object:
        self._audit.record("limiter_acquire")
        raise AssertionError("limiter acquire must remain inactive during refusal")

    def defer_for(self, *_args: object, **_kwargs: object) -> object:
        self._audit.record("limiter_defer")
        raise AssertionError("limiter defer must remain inactive during refusal")


def _listing(root: Path) -> tuple[str, ...]:
    return tuple(sorted(path.relative_to(root).as_posix() for path in root.rglob("*")))


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


def _coordinator(audit: _DependencyAudit) -> IngestionCoordinator:
    return IngestionCoordinator(
        session_factory=_NeverUseProvider(audit),  # type: ignore[arg-type]
        limiter=_NeverUseLimiter(audit),  # type: ignore[arg-type]
        clock=_FixedMarch2024Clock(),
        sleeper=audit.forbidden("sleeper"),  # type: ignore[arg-type]
        schedule_store_factory=audit.forbidden("schedule_store"),  # type: ignore[arg-type]
        catalog_factory=audit.forbidden("catalog"),  # type: ignore[arg-type]
        recovery_observer_factory=audit.forbidden("recovery"),  # type: ignore[arg-type]
        lifecycle_executor_factory=audit.forbidden("lifecycle"),  # type: ignore[arg-type]
    )


def _assert_refusal_report(
    report: IngestionReport,
    outcome: IngestionRunOutcome,
    failure_code: RunFailureCode,
) -> None:
    assert type(report) is IngestionReport
    assert report.outcome is outcome
    assert report.failure_code is failure_code
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
    assert all(type(result) is PartitionResult for result in report.results)
    assert all(
        result.outcome is PartitionOutcome.NOT_ATTEMPTED for result in report.results
    )
    assert all(result.provider_attempts == 0 for result in report.results)
    assert all(result.ingestion_run_id is None for result in report.results)
    assert all(result.final_manifest is None for result in report.results)
    assert all(result.failure_category is None for result in report.results)
    assert all(result.error_code is None for result in report.results)


def test_held_real_storage_root_lease_returns_already_running_without_side_effects(
    tmp_path: Path,
) -> None:
    """D19 preserves a held protected root and stops before all later ports."""
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    before = _listing(tmp_path)
    audit = _DependencyAudit()
    try:
        report = _coordinator(audit).run(_command(tmp_path))
    finally:
        acquired.lease.close()

    _assert_refusal_report(
        report, IngestionRunOutcome.ALREADY_RUNNING, RunFailureCode.ALREADY_RUNNING
    )
    assert audit.calls == {}
    assert _listing(tmp_path) == before


def test_symlink_storage_root_is_rejected_without_creating_through_the_link(
    tmp_path: Path,
) -> None:
    """D19 refuses a physical symlink root before any storage or provider work."""
    target = tmp_path / "target"
    target.mkdir()
    unsafe_root = tmp_path / "unsafe-root"
    try:
        unsafe_root.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink unavailable in this environment: {error}")
    before_root = _listing(tmp_path)
    before_target = _listing(target)
    audit = _DependencyAudit()

    report = _coordinator(audit).run(_command(unsafe_root))

    _assert_refusal_report(
        report, IngestionRunOutcome.REJECTED, RunFailureCode.STORAGE_UNSAFE
    )
    assert audit.calls == {}
    assert _listing(tmp_path) == before_root
    assert _listing(target) == before_target
    assert not (target / ".ingestion.lock").exists()
