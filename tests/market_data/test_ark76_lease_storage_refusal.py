"""ARK-76 characterization of lease and unsafe-storage coordinator refusals."""

from __future__ import annotations

import hashlib
import os
import stat
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
    LeaseFailureCode,
    LeaseOutcome,
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


@dataclass(frozen=True, slots=True)
class _FilesystemEntry:
    relative_path: str
    device: int
    inode: int
    file_type: int
    mode: int
    size: int
    content_sha256: str | None
    symlink_target: str | None


def _snapshot(root: Path) -> tuple[_FilesystemEntry, ...]:
    entries: list[_FilesystemEntry] = []

    def visit(path: Path, relative_path: str) -> None:
        metadata = os.lstat(path)
        file_type = stat.S_IFMT(metadata.st_mode)
        entries.append(
            _FilesystemEntry(
                relative_path,
                metadata.st_dev,
                metadata.st_ino,
                file_type,
                stat.S_IMODE(metadata.st_mode),
                metadata.st_size,
                (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if stat.S_ISREG(metadata.st_mode)
                    else None
                ),
                os.readlink(path) if stat.S_ISLNK(metadata.st_mode) else None,
            )
        )
        if stat.S_ISDIR(metadata.st_mode):
            with os.scandir(path) as children:
                for child in sorted(children, key=lambda item: item.name):
                    child_relative_path = (
                        child.name
                        if relative_path == "."
                        else f"{relative_path}/{child.name}"
                    )
                    visit(path / child.name, child_relative_path)

    visit(root, ".")
    return tuple(sorted(entries, key=lambda item: item.relative_path))


def _entry(
    snapshot: tuple[_FilesystemEntry, ...], relative_path: str
) -> _FilesystemEntry:
    return next(item for item in snapshot if item.relative_path == relative_path)


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
    before = _snapshot(tmp_path)
    assert _entry(before, ".").inode == os.lstat(tmp_path).st_ino
    assert (
        _entry(before, ".ingestion.lock").content_sha256
        == hashlib.sha256((tmp_path / ".ingestion.lock").read_bytes()).hexdigest()
    )
    audit = _DependencyAudit()
    try:
        report = _coordinator(audit).run(_command(tmp_path))
        _assert_refusal_report(
            report, IngestionRunOutcome.ALREADY_RUNNING, RunFailureCode.ALREADY_RUNNING
        )
        assert audit.calls == {}
        assert _snapshot(tmp_path) == before

        with acquired.lease.root_operation(tmp_path) as operation:
            assert type(operation.descriptor) is int
        contention = StorageRootLease.try_acquire(tmp_path)
        assert contention.outcome is LeaseOutcome.ALREADY_RUNNING
        assert contention.failure_code is LeaseFailureCode.ALREADY_RUNNING
        assert contention.lease is None
        assert _snapshot(tmp_path) == before
    finally:
        acquired.lease.close()

    # Closing only releases the advisory lock; it does not alter durable evidence.
    assert _snapshot(tmp_path) == before
    reacquired = StorageRootLease.try_acquire(tmp_path)
    assert reacquired.outcome is LeaseOutcome.ACQUIRED
    assert reacquired.lease is not None
    reacquired.lease.close()
    assert _snapshot(tmp_path) == before


def test_symlink_storage_root_is_rejected_without_creating_through_the_link(
    tmp_path: Path,
) -> None:
    """D19 refuses a physical symlink root before any storage or provider work."""
    target = tmp_path / "target"
    target.mkdir()
    sentinel = target / "preserved.bin"
    sentinel.write_bytes(b"ARK-76 unsafe-root sentinel")
    unsafe_root = tmp_path / "unsafe-root"
    if not hasattr(os, "symlink"):
        pytest.skip("the operating system does not support symlinks")
    unsafe_root.symlink_to(target, target_is_directory=True)
    before_root = _snapshot(tmp_path)
    before_target = _snapshot(target)
    unsafe_entry = _entry(before_root, "unsafe-root")
    assert unsafe_entry.file_type == stat.S_IFLNK
    assert unsafe_entry.symlink_target == os.readlink(unsafe_root)
    assert (
        _entry(before_target, "preserved.bin").content_sha256
        == hashlib.sha256(sentinel.read_bytes()).hexdigest()
    )
    audit = _DependencyAudit()

    report = _coordinator(audit).run(_command(unsafe_root))

    _assert_refusal_report(
        report, IngestionRunOutcome.REJECTED, RunFailureCode.STORAGE_UNSAFE
    )
    assert audit.calls == {}
    assert _snapshot(tmp_path) == before_root
    assert _snapshot(target) == before_target
    assert not (target / ".ingestion.lock").exists()
