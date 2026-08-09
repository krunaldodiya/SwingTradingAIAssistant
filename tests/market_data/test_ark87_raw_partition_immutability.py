"""ARK-87 D15 immutable raw-partition regression evidence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from ark74_benchmark_fixture import (
    BenchmarkFixture,
    BenchmarkFixturePartition,
    benchmark_nse_eq_v1,
)

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    verify_manifest,
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
    inode: int


def _fixture() -> tuple[BenchmarkFixture, BenchmarkFixturePartition]:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    return fixture, fixture.partitions[0]


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


def _snapshot(root: Path, partition: BenchmarkFixturePartition) -> _PartitionSnapshot:
    artifact = root / _canonical_path(partition)
    data = artifact.read_bytes()
    with DuckDBCatalog(root) as catalog:
        manifest = catalog.get_manifest(partition.plan)
    return _PartitionSnapshot(
        manifest,
        data,
        hashlib.sha256(data).hexdigest(),
        artifact.stat().st_ino,
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
    partition: BenchmarkFixturePartition,
    outcome: PartitionOutcome,
) -> PartitionResult:
    assert type(report) is IngestionReport
    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert report.planned_count == 1
    assert report.provider_attempt_count == 0
    assert report.results == (report.results[0],)
    assert report.skipped_count == int(outcome is PartitionOutcome.SKIPPED_VERIFIED)
    assert report.locally_recovered_count == int(
        outcome is PartitionOutcome.RECOVERED_LOCALLY
    )
    assert (
        report.verified_count == report.failed_count == report.not_attempted_count == 0
    )
    assert report.cancelled_count == 0
    result = report.results[0]
    assert type(result) is PartitionResult
    assert result.plan == partition.plan
    assert result.outcome is outcome
    assert result.reconciliation_reasons == ()
    assert result.provider_attempts == 0
    assert result.failure_category is result.error_code is None
    return result


def _assert_verified_provenance(
    manifest: PartitionManifest,
    partition: BenchmarkFixturePartition,
    checksum: str,
    schedule_digest: str,
    run_id: str,
) -> None:
    assert manifest.plan == partition.plan
    assert manifest.ingestion_run_id == run_id
    assert manifest.state is ManifestState.VERIFIED
    assert manifest.validation_outcome is ValidationOutcome.PASSED
    assert manifest.failure_category is None
    assert manifest.row_count == partition.published_count == 7_500
    assert manifest.actual_from_ts == partition.canonical_candles[0].ts
    assert manifest.actual_to_ts == partition.canonical_candles[-1].ts
    assert manifest.actual_from_ts.tzinfo is UTC
    assert manifest.actual_to_ts.tzinfo is UTC
    assert manifest.validation_policy_version == (
        f"nse-equity-month@v1+sessions-sha256:{schedule_digest}"
    )
    assert manifest.source_version == "upstox-historical-v3"
    assert manifest.canonical_path == _canonical_path(partition)
    assert manifest.checksum_sha256 == checksum


def test_verified_b01_rerun_skips_without_mutating_raw_partition(
    tmp_path: Path,
) -> None:
    fixture, partition = _fixture()
    schedule = _retain_schedule(tmp_path, fixture.schedule)
    seeded = _seed_verified(tmp_path, partition, schedule, "ark87-seed")
    before = _snapshot(tmp_path, partition)
    _assert_verified_provenance(
        seeded,
        partition,
        before.checksum,
        fixture.schedule_digest,
        "ark87-seed",
    )
    sessions = _NeverProviderSessionFactory()
    limiter = _NeverLimiter()
    sleeper = _NeverSleeper()

    report = _coordinator(sessions, limiter, sleeper, "ark87-rerun").run(
        _command(tmp_path, fixture)
    )

    result = _assert_zero_request_success(
        report, partition, PartitionOutcome.SKIPPED_VERIFIED
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
) -> None:
    fixture, partition = _fixture()
    published = publish_partition(tmp_path, partition.plan, partition.canonical_candles)
    before_bytes = (tmp_path / published.canonical_path).read_bytes()
    before_checksum = hashlib.sha256(before_bytes).hexdigest()
    assert before_checksum == published.checksum_sha256
    sessions = _NeverProviderSessionFactory()
    limiter = _NeverLimiter()
    sleeper = _NeverSleeper()

    report = _coordinator(sessions, limiter, sleeper, "ark87-recovery").run(
        _command(tmp_path, fixture)
    )

    result = _assert_zero_request_success(
        report, partition, PartitionOutcome.RECOVERED_LOCALLY
    )
    assert result.ingestion_run_id == "ark87-recovery"
    assert result.final_manifest is not None
    _assert_verified_provenance(
        result.final_manifest,
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
    assert after.bytes == before_bytes
    assert after.checksum == before_checksum
    assert after.manifest == result.final_manifest


def test_repeat_exact_publication_is_already_present_without_overwrite(
    tmp_path: Path,
) -> None:
    _fixture_value, partition = _fixture()
    first = publish_partition(tmp_path, partition.plan, partition.canonical_candles)
    artifact = tmp_path / first.canonical_path
    before_bytes = artifact.read_bytes()
    before_inode = artifact.stat().st_ino

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
    assert artifact.read_bytes() == before_bytes
    assert artifact.stat().st_ino == before_inode
