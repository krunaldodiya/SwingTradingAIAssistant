"""ARK-87 D15 immutable raw-partition regression evidence."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ark74_benchmark_fixture import (
    BenchmarkFixture,
    BenchmarkFixturePartition,
    benchmark_nse_eq_v1,
)

import swing_trading_ai_assistant.market_data.partition_publication as publication_module
import swing_trading_ai_assistant.market_data.partition_recovery as recovery_module
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
    plan_upstox_equity_months,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    PublicationOutcome,
    publish_partition,
)
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
    ScheduleEvidenceStore,
    ScheduleOutcome,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2024, 4, 1, tzinfo=UTC)


_FIXED_NOW = datetime(2024, 4, 1, tzinfo=UTC)


def _empty_strings() -> list[str]:
    return []


@dataclass(slots=True)
class _DirectoryIdentity:
    device: int
    inode: int


class _TargetPathOSProxy:
    """A module-local OS proxy that refuses writes to one exact raw artifact."""

    def __init__(self, barrier: _FinalPathWriteBarrier) -> None:
        self._barrier = barrier

    def __getattr__(self, name: str) -> object:
        return getattr(os, name)

    def open(
        self,
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        self._barrier.record_open(path, flags, dir_fd)
        if dir_fd is None:
            return os.open(path, flags, mode)  # type: ignore[arg-type]
        return os.open(path, flags, mode, dir_fd=dir_fd)  # type: ignore[arg-type]

    def link(
        self,
        source: object,
        destination: object,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        self._barrier.record_link(source, destination, src_dir_fd, dst_dir_fd)
        os.link(
            source,  # type: ignore[arg-type]
            destination,  # type: ignore[arg-type]
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    def replace(
        self,
        source: object,
        destination: object,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        self._barrier.deny_target_mutation("replace", destination, dst_dir_fd)
        os.replace(
            source,  # type: ignore[arg-type]
            destination,  # type: ignore[arg-type]
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    def rename(
        self,
        source: object,
        destination: object,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        self._barrier.deny_target_mutation("rename", destination, dst_dir_fd)
        os.rename(
            source,  # type: ignore[arg-type]
            destination,  # type: ignore[arg-type]
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    def unlink(self, path: object, *, dir_fd: int | None = None) -> None:
        self._barrier.deny_target_mutation("unlink", path, dir_fd)
        if dir_fd is None:
            os.unlink(path)  # type: ignore[arg-type]
            return
        os.unlink(path, dir_fd=dir_fd)  # type: ignore[arg-type]


@dataclass(slots=True)
class _FinalPathWriteBarrier:
    """Binds final-path observations to the exact canonical parent directory."""

    target: Path
    target_parent: _DirectoryIdentity = field(init=False)
    target_read_opens: int = 0
    target_link_destinations: int = 0
    blocked_target_mutations: list[str] = field(default_factory=_empty_strings)
    temporary_operations: list[str] = field(default_factory=_empty_strings)
    wrong_directory_bars: int = 0

    def __post_init__(self) -> None:
        target_parent = self.target.parent.stat()
        self.target_parent = _DirectoryIdentity(
            target_parent.st_dev, target_parent.st_ino
        )

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        proxy = _TargetPathOSProxy(self)
        monkeypatch.setattr(publication_module, "os", proxy)
        monkeypatch.setattr(recovery_module, "os", proxy)

    def record_open(self, path: object, flags: int, dir_fd: int | None) -> None:
        if self._is_target(path, dir_fd):
            if flags & (
                os.O_WRONLY | os.O_RDWR | os.O_TRUNC | os.O_CREAT | os.O_APPEND
            ):
                self.blocked_target_mutations.append("open")
                raise AssertionError("ARK-87 final path must never be opened writable")
            self.target_read_opens += 1
        else:
            self._record_temp("open", path)

    def record_link(
        self,
        source: object,
        destination: object,
        source_dir_fd: int | None,
        destination_dir_fd: int | None,
    ) -> None:
        if self._is_target(destination, destination_dir_fd):
            self.target_link_destinations += 1
        else:
            self._record_temp("link", source)

    def deny_target_mutation(
        self, operation: str, path: object, dir_fd: int | None
    ) -> None:
        if self._is_target(path, dir_fd):
            self.blocked_target_mutations.append(operation)
            raise AssertionError(f"ARK-87 final path must never be {operation}d")
        self._record_temp(operation, path)

    def _is_target(self, path: object, dir_fd: int | None) -> bool:
        if not self._is_bars_name(path):
            return False
        identity = self._parent_identity(path, dir_fd)
        if identity == self.target_parent:
            return True
        self.wrong_directory_bars += 1
        return False

    def _parent_identity(
        self, path: object, dir_fd: int | None
    ) -> _DirectoryIdentity | None:
        try:
            if dir_fd is not None:
                parent = os.fstat(dir_fd)
            elif isinstance(path, (str, Path)) and Path(path).is_absolute():
                parent = Path(path).parent.stat()
            else:
                return None
        except OSError:
            return None
        return _DirectoryIdentity(parent.st_dev, parent.st_ino)

    def _record_temp(self, operation: str, path: object) -> None:
        if isinstance(path, str) and path.startswith(".publish-"):
            self.temporary_operations.append(operation)

    @staticmethod
    def _is_bars_name(path: object) -> bool:
        return isinstance(path, (str, Path)) and Path(path).name == "bars.parquet"


class _NeverProviderSessionFactory:
    def __init__(self) -> None:
        self.open_calls = 0

    def open(self) -> object:
        self.open_calls += 1
        raise AssertionError("ARK-87 local observation must not open a provider")


class _NeverLimiter:
    def __init__(self) -> None:
        self.acquire_calls = 0
        self.defer_calls = 0

    def acquire(self, *_args: object) -> object:
        self.acquire_calls += 1
        raise AssertionError("ARK-87 local observation must not acquire a limiter")

    def defer_for(self, *_args: object) -> object:
        self.defer_calls += 1
        raise AssertionError("ARK-87 local observation must not defer a limiter")


class _NeverSleeper:
    def __init__(self) -> None:
        self.calls = 0

    def sleep(self, *_args: object) -> None:
        self.calls += 1
        raise AssertionError("ARK-87 local observation must not sleep")


@dataclass(frozen=True, slots=True)
class _PartitionSnapshot:
    manifest: PartitionManifest | None
    bytes: bytes
    checksum: str
    device: int
    inode: int


def _fixture() -> tuple[BenchmarkFixture, BenchmarkFixturePartition]:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    return fixture, fixture.partitions[0]


def _expected_plan(fixture: BenchmarkFixture) -> PlannedInstrumentMonth:
    plans = plan_upstox_equity_months(
        fixture.instrument,
        date(2024, 2, 1),
        date(2024, 2, 29),
        "1m",
    )
    assert len(plans) == 1
    return plans[0]


def _canonical_path(partition: BenchmarkFixturePartition) -> str:
    plan = partition.plan
    return (
        "candles/"
        f"provider={plan.provider}/exchange={plan.exchange}/segment={plan.segment}/"
        f"instrument_type={plan.instrument_type}/security_id={plan.security_id}/"
        f"interval={plan.interval}/year={plan.year:04d}/month={plan.month:02d}/"
        "bars.parquet"
    )


def _retain_schedule(
    root: Path, schedule: ExpectedSessionSchedule
) -> ScheduleEvidenceResult:
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED
    assert acquired.lease is not None
    with acquired.lease:
        retained = ScheduleEvidenceStore(root, acquired.lease).retain(schedule)
    assert retained.outcome is ScheduleOutcome.RETAINED
    return retained


def _seed_verified(
    root: Path,
    partition: BenchmarkFixturePartition,
    schedule: ScheduleEvidenceResult,
    run_id: str,
) -> PartitionManifest:
    assert schedule.digest is not None
    published = publish_partition(root, partition.plan, partition.canonical_candles)
    started = datetime(2024, 4, 1, tzinfo=UTC)
    active = PartitionManifest(
        1,
        partition.plan,
        run_id,
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        "nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        None,
        None,
        None,
        None,
        None,
        "upstox-historical-v3",
        started,
        started,
        started,
        None,
    )
    verified = verify_manifest(
        active,
        started,
        published.actual_from_ts,
        published.actual_to_ts,
        published.row_count,
        published.checksum_sha256,
        published.canonical_path,
    )
    with DuckDBCatalog(root) as catalog:
        catalog.create_manifest(active)
        catalog.transition_manifest(active, verified)
    return verified


def _expected_verified_manifest(
    fixture: BenchmarkFixture,
    partition: BenchmarkFixturePartition,
    expected_plan: PlannedInstrumentMonth,
    checksum: str,
    run_id: str,
) -> PartitionManifest:
    return PartitionManifest(
        1,
        expected_plan,
        run_id,
        1,
        ManifestState.VERIFIED,
        ValidationOutcome.PASSED,
        f"nse-equity-month@v1+sessions-sha256:{fixture.schedule_digest}",
        partition.canonical_candles[0].ts,
        partition.canonical_candles[-1].ts,
        7_500,
        checksum,
        _canonical_path(partition),
        "upstox-historical-v3",
        _FIXED_NOW,
        _FIXED_NOW,
        _FIXED_NOW,
        None,
    )


def _snapshot(root: Path, partition: BenchmarkFixturePartition) -> _PartitionSnapshot:
    artifact = root / _canonical_path(partition)
    data = artifact.read_bytes()
    metadata = artifact.stat()
    with DuckDBCatalog(root) as catalog:
        manifest = catalog.get_manifest(partition.plan)
    return _PartitionSnapshot(
        manifest,
        data,
        hashlib.sha256(data).hexdigest(),
        metadata.st_dev,
        metadata.st_ino,
    )


def _command(root: Path, fixture: BenchmarkFixture) -> IngestionCommand:
    return IngestionCommand(
        fixture.instrument,
        date(2024, 2, 1),
        date(2024, 2, 29),
        "1m",
        root,
        fixture.schedule,
        fixture.validation_policy,
    )


def _coordinator(
    sessions: _NeverProviderSessionFactory,
    limiter: _NeverLimiter,
    sleeper: _NeverSleeper,
    run_id: str,
) -> IngestionCoordinator:
    return IngestionCoordinator(
        session_factory=sessions,  # type: ignore[arg-type]
        limiter=limiter,  # type: ignore[arg-type]
        sleeper=sleeper,  # type: ignore[arg-type]
        clock=_FixedClock(),
        run_id_factory=lambda: run_id,
    )


def _assert_zero_request_success(
    report: IngestionReport,
    expected_plan: PlannedInstrumentMonth,
    outcome: PartitionOutcome,
    expected_run_id: str,
    expected_manifest: PartitionManifest,
) -> PartitionResult:
    assert type(report) is IngestionReport
    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert report.planned_count == 1
    assert report.provider_attempt_count == 0
    assert type(report.results) is tuple
    assert len(report.results) == 1
    assert report.skipped_count == int(outcome is PartitionOutcome.SKIPPED_VERIFIED)
    assert report.locally_recovered_count == int(
        outcome is PartitionOutcome.RECOVERED_LOCALLY
    )
    assert (
        report.verified_count == report.failed_count == report.not_attempted_count == 0
    )
    assert report.cancelled_count == 0
    assert report.started_at == _FIXED_NOW
    assert report.completed_at == _FIXED_NOW
    assert report.started_at.tzinfo is UTC
    assert report.completed_at.tzinfo is UTC
    result = report.results[0]
    assert type(result) is PartitionResult
    assert result.plan == expected_plan
    assert result.outcome is outcome
    assert result.reconciliation_reasons == ()
    assert result.ingestion_run_id == expected_run_id
    assert result.provider_attempts == 0
    assert result.final_manifest == expected_manifest
    assert result.failure_category is None
    assert result.error_code is None
    assert report.results == (
        PartitionResult(
            expected_plan,
            outcome,
            (),
            expected_run_id,
            0,
            expected_manifest,
            None,
            None,
        ),
    )
    return result


def _assert_verified_provenance(
    manifest: PartitionManifest,
    expected_plan: PlannedInstrumentMonth,
    partition: BenchmarkFixturePartition,
    checksum: str,
    schedule_digest: str,
    run_id: str,
) -> None:
    assert type(manifest) is PartitionManifest
    assert manifest.manifest_schema_version == 1
    assert manifest.plan == expected_plan
    assert manifest.ingestion_run_id == run_id
    assert manifest.candle_schema_version == 1
    assert manifest.state is ManifestState.VERIFIED
    assert manifest.validation_outcome is ValidationOutcome.PASSED
    assert manifest.failure_category is None
    assert manifest.row_count == partition.published_count == 7_500
    assert manifest.actual_from_ts == partition.canonical_candles[0].ts
    assert manifest.actual_to_ts == partition.canonical_candles[-1].ts
    assert manifest.actual_from_ts is not None
    assert manifest.actual_to_ts is not None
    assert manifest.actual_from_ts.tzinfo is UTC
    assert manifest.actual_to_ts.tzinfo is UTC
    assert manifest.validation_policy_version == (
        f"nse-equity-month@v1+sessions-sha256:{schedule_digest}"
    )
    assert manifest.source_version == "upstox-historical-v3"
    assert manifest.canonical_path == _canonical_path(partition)
    assert manifest.checksum_sha256 == checksum
    assert manifest.created_at == _FIXED_NOW
    assert manifest.attempt_started_at == _FIXED_NOW
    assert manifest.updated_at == _FIXED_NOW
    assert manifest.created_at.tzinfo is UTC
    assert manifest.attempt_started_at.tzinfo is UTC
    assert manifest.updated_at.tzinfo is UTC


def test_verified_b01_rerun_skips_without_mutating_raw_partition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, partition = _fixture()
    expected_plan = _expected_plan(fixture)
    schedule = _retain_schedule(tmp_path, fixture.schedule)
    seeded = _seed_verified(tmp_path, partition, schedule, "ark87-seed")
    before = _snapshot(tmp_path, partition)
    expected_seeded = _expected_verified_manifest(
        fixture,
        partition,
        expected_plan,
        before.checksum,
        "ark87-seed",
    )
    _assert_verified_provenance(
        seeded,
        expected_plan,
        partition,
        before.checksum,
        fixture.schedule_digest,
        "ark87-seed",
    )
    assert seeded == expected_seeded
    barrier = _FinalPathWriteBarrier(tmp_path / _canonical_path(partition))
    barrier.install(monkeypatch)
    sessions = _NeverProviderSessionFactory()
    limiter = _NeverLimiter()
    sleeper = _NeverSleeper()

    report = _coordinator(sessions, limiter, sleeper, "ark87-rerun").run(
        _command(tmp_path, fixture)
    )
    assert barrier.target_read_opens >= 1
    assert barrier.target_link_destinations == 0
    assert barrier.blocked_target_mutations == []
    assert barrier.temporary_operations == []

    result = _assert_zero_request_success(
        report,
        expected_plan,
        PartitionOutcome.SKIPPED_VERIFIED,
        "ark87-seed",
        expected_seeded,
    )
    assert result.final_manifest == seeded == before.manifest
    assert (
        sessions.open_calls
        == limiter.acquire_calls
        == limiter.defer_calls
        == sleeper.calls
        == 0
    )
    after = _snapshot(tmp_path, partition)
    assert after == before


def test_valid_final_without_catalog_recovers_locally_without_mutating_raw_partition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, partition = _fixture()
    expected_plan = _expected_plan(fixture)
    published = publish_partition(tmp_path, partition.plan, partition.canonical_candles)
    before = _snapshot(tmp_path, partition)
    before_checksum = before.checksum
    assert before_checksum == published.checksum_sha256
    expected_recovered = _expected_verified_manifest(
        fixture,
        partition,
        expected_plan,
        before_checksum,
        "ark87-recovery",
    )
    barrier = _FinalPathWriteBarrier(tmp_path / published.canonical_path)
    barrier.install(monkeypatch)
    sessions = _NeverProviderSessionFactory()
    limiter = _NeverLimiter()
    sleeper = _NeverSleeper()

    report = _coordinator(sessions, limiter, sleeper, "ark87-recovery").run(
        _command(tmp_path, fixture)
    )
    assert barrier.target_read_opens >= 1
    assert barrier.target_link_destinations == 0
    assert barrier.blocked_target_mutations == []
    assert barrier.temporary_operations == []

    _assert_zero_request_success(
        report,
        expected_plan,
        PartitionOutcome.RECOVERED_LOCALLY,
        "ark87-recovery",
        expected_recovered,
    )
    _assert_verified_provenance(
        expected_recovered,
        expected_plan,
        partition,
        before_checksum,
        fixture.schedule_digest,
        "ark87-recovery",
    )
    assert (
        sessions.open_calls
        == limiter.acquire_calls
        == limiter.defer_calls
        == sleeper.calls
        == 0
    )
    after = _snapshot(tmp_path, partition)
    assert after.bytes == before.bytes
    assert after.checksum == before_checksum
    assert after.device == before.device
    assert after.inode == before.inode
    assert after.manifest == expected_recovered


def test_repeat_exact_publication_is_already_present_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture_value, partition = _fixture()
    first = publish_partition(tmp_path, partition.plan, partition.canonical_candles)
    artifact = tmp_path / first.canonical_path
    before_bytes = artifact.read_bytes()
    before_metadata = artifact.stat()
    barrier = _FinalPathWriteBarrier(artifact)
    barrier.install(monkeypatch)
    wrong_parent = tmp_path / "wrong-parent"
    wrong_parent.mkdir()
    (wrong_parent / "bars.parquet").write_bytes(b"control")
    wrong_parent_fd = os.open(wrong_parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        wrong_descriptor = publication_module.os.open(
            "bars.parquet", os.O_RDONLY, dir_fd=wrong_parent_fd
        )
        os.close(wrong_descriptor)
    finally:
        os.close(wrong_parent_fd)

    repeated = publish_partition(tmp_path, partition.plan, partition.canonical_candles)

    assert first.outcome is PublicationOutcome.PUBLISHED
    assert repeated.outcome is PublicationOutcome.ALREADY_PRESENT
    assert repeated.plan == first.plan == partition.plan
    assert repeated.canonical_path == first.canonical_path == _canonical_path(partition)
    assert repeated.checksum_sha256 == first.checksum_sha256
    assert repeated.byte_size == first.byte_size == len(before_bytes)
    assert repeated.row_count == first.row_count == partition.published_count == 7_500
    assert (
        repeated.actual_from_ts
        == first.actual_from_ts
        == partition.canonical_candles[0].ts
    )
    assert (
        repeated.actual_to_ts
        == first.actual_to_ts
        == partition.canonical_candles[-1].ts
    )
    assert repeated.source_version == first.source_version == "upstox-historical-v3"
    assert barrier.target_read_opens == 1
    assert barrier.target_link_destinations == 1
    assert barrier.blocked_target_mutations == []
    assert barrier.temporary_operations == ["open", "unlink"]
    assert barrier.wrong_directory_bars == 1
    assert artifact.read_bytes() == before_bytes
    assert artifact.stat().st_dev == before_metadata.st_dev
    assert artifact.stat().st_ino == before_metadata.st_ino
