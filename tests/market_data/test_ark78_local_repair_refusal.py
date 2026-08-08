"""ARK-78 characterization of unsafe local-repair refusal containment."""

from __future__ import annotations

import hashlib
import os
import stat
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
    calls: dict[str, int] = field(default_factory=dict[str, int])

    def record(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def forbidden(self, name: str) -> Callable[..., object]:
        def call(*_args: object, **_kwargs: object) -> object:
            self.record(name)
            raise AssertionError(f"{name} must remain inactive after local refusal")

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


class _InMemoryCatalog:
    def __init__(self, audit: _DependencyAudit) -> None:
        self._audit = audit

    def __enter__(self) -> _InMemoryCatalog:
        return self

    def __exit__(
        self,
        _exception_type: object,
        _exception: object,
        _traceback: object,
    ) -> None:
        return None

    def get_manifest(self, _plan: object) -> None:
        self._audit.record("catalog_get")
        return None

    def create_manifest(self, _manifest: object) -> None:
        self._audit.record("catalog_create")
        raise AssertionError(
            "catalog creation must remain inactive after local refusal"
        )

    def transition_manifest(self, _current: object, _target: object) -> None:
        self._audit.record("catalog_transition")
        raise AssertionError(
            "catalog transition must remain inactive after local refusal"
        )


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

    def resolve(self, _digest: object) -> object:
        self._audit.record("schedule_resolve")
        raise AssertionError("manifest schedule resolution must remain inactive")


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


def _canonical_target(storage_root: Path) -> Path:
    return storage_root / (
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
        "instrument_type=EQ/security_id=INE000A01000/interval=1m/"
        "year=2024/month=02/bars.parquet"
    )


def test_symlinked_canonical_partition_refuses_local_repair_without_request(
    tmp_path: Path,
) -> None:
    """D19 leaves an unsafe partition and external target untouched before requests."""
    storage_root = tmp_path / "storage-root"
    storage_root.mkdir()
    initial_lease = StorageRootLease.try_acquire(storage_root)
    assert initial_lease.outcome is LeaseOutcome.ACQUIRED
    assert initial_lease.lease is not None
    initial_lease.lease.close()

    outside_target = tmp_path / "outside-sentinel.parquet"
    outside_target.write_bytes(b"ARK-78 external sentinel bytes")
    os.chmod(outside_target, 0o640)
    target = _canonical_target(storage_root)
    target.parent.mkdir(parents=True)
    target.symlink_to(outside_target)

    before_root = _snapshot(storage_root)
    before_outside = _snapshot(outside_target)
    assert target.is_symlink()
    assert os.readlink(target) == str(outside_target)

    audit = _DependencyAudit()
    catalog = _InMemoryCatalog(audit)
    command = _command(storage_root)
    coordinator = IngestionCoordinator(
        session_factory=_NeverUseProvider(audit),  # type: ignore[arg-type]
        limiter=_NeverUseLimiter(audit),  # type: ignore[arg-type]
        clock=_FixedMarch2024Clock(),
        sleeper=audit.forbidden("sleeper"),  # type: ignore[arg-type]
        run_id_factory=audit.forbidden("run_id"),  # type: ignore[arg-type]
        catalog_factory=lambda _root: catalog,  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ExactRetainedScheduleStore(
            command.expected_sessions, audit
        ),  # type: ignore[arg-type]
        lifecycle_executor_factory=audit.forbidden("lifecycle_executor"),  # type: ignore[arg-type]
    )

    report = coordinator.run(command)

    assert type(report) is IngestionReport
    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is RunFailureCode.LOCAL_REPAIR_BLOCKED
    assert report.planned_count == report.failed_count == len(report.results) == 1
    assert (
        report.skipped_count
        == report.locally_recovered_count
        == report.provider_attempt_count
        == report.verified_count
        == report.not_attempted_count
        == report.cancelled_count
        == 0
    )
    result = report.results[0]
    assert type(result) is PartitionResult
    assert result.outcome is PartitionOutcome.FAILED
    assert result.provider_attempts == 0
    assert result.ingestion_run_id is None
    assert result.final_manifest is None
    assert result.failure_category is None
    assert result.error_code == RunFailureCode.LOCAL_REPAIR_BLOCKED
    assert audit.calls == {"schedule_retain": 1, "catalog_get": 1}

    assert _snapshot(storage_root) == before_root
    assert _snapshot(outside_target) == before_outside
    assert target.is_symlink()
    assert os.readlink(target) == str(outside_target)
    assert outside_target.read_bytes() == b"ARK-78 external sentinel bytes"
    assert not tuple(target.parent.glob(".quarantine-*.parquet"))
