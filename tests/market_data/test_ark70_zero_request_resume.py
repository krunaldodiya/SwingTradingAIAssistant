from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from ark74_benchmark_fixture import BenchmarkFixturePartition, benchmark_nse_eq_v1

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    publish_partition,
)
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionRunOutcome,
    PartitionOutcome,
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
        raise AssertionError("B02 resume must not open a provider session")


class _NeverLimiter:
    def __init__(self) -> None:
        self.acquire_calls = 0
        self.defer_calls = 0

    def acquire(self, *_args: object) -> object:
        self.acquire_calls += 1
        raise AssertionError("B02 resume must not acquire a limiter permit")

    def defer_for(self, *_args: object) -> object:
        self.defer_calls += 1
        raise AssertionError("B02 resume must not defer a limiter")


@dataclass(frozen=True, slots=True)
class _PartitionSnapshot:
    manifest: PartitionManifest | None
    bytes: bytes
    checksum: str


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
) -> None:
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


def _seed_final_without_catalog(
    root: Path, partition: BenchmarkFixturePartition
) -> None:
    published = publish_partition(root, partition.plan, partition.canonical_candles)
    assert published.canonical_path == _canonical_path(partition)
    assert published.row_count == partition.published_count


def _snapshot(root: Path, partition: BenchmarkFixturePartition) -> _PartitionSnapshot:
    path = root / _canonical_path(partition)
    data = path.read_bytes()
    with DuckDBCatalog(root) as catalog:
        manifest = catalog.get_manifest(partition.plan)
    return _PartitionSnapshot(manifest, data, hashlib.sha256(data).hexdigest())


def test_b02_resume_recovers_only_the_valid_uncatalogued_march_partition(
    tmp_path: Path,
) -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 1, 1), date(2024, 3, 1))
    january, february, march = fixture.partitions
    schedule = _retain_schedule(tmp_path, fixture.schedule)
    _seed_verified(tmp_path, january, schedule, "ark70-seed-january")
    _seed_verified(tmp_path, february, schedule, "ark70-seed-february")
    _seed_final_without_catalog(tmp_path, march)
    before = tuple(_snapshot(tmp_path, partition) for partition in fixture.partitions)
    assert before[0].manifest is not None
    assert before[1].manifest is not None
    assert before[2].manifest is None
    schedule_path = (
        tmp_path / "calendar-schedules" / "sha256" / f"{fixture.schedule_digest}.json"
    )
    schedule_before = schedule_path.read_bytes()
    sessions = _NeverProviderSessionFactory()
    limiter = _NeverLimiter()
    coordinator = IngestionCoordinator(
        session_factory=sessions,  # type: ignore[arg-type]
        limiter=limiter,  # type: ignore[arg-type]
        clock=_FixedClock(),
        run_id_factory=lambda: "ark70-recovery",
    )
    command = IngestionCommand(
        fixture.instrument,
        date(2024, 1, 1),
        date(2024, 3, 31),
        "1m",
        tmp_path,
        fixture.schedule,
        fixture.validation_policy,
    )

    report = coordinator.run(command)

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert report.planned_count == 3
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.RECOVERED_LOCALLY,
    ]
    assert report.skipped_count == 2
    assert report.locally_recovered_count == 1
    assert report.provider_attempt_count == 0
    assert sessions.open_calls == limiter.acquire_calls == limiter.defer_calls == 0
    assert schedule_path.read_bytes() == schedule_before == fixture.schedule_bytes

    after = tuple(_snapshot(tmp_path, partition) for partition in fixture.partitions)
    assert after[0] == before[0]
    assert after[1] == before[1]
    assert after[2].bytes == before[2].bytes
    assert after[2].checksum == before[2].checksum
    assert after[2].manifest is not None
    assert after[2].manifest.state is ManifestState.VERIFIED
    assert after[2].manifest.validation_outcome is ValidationOutcome.PASSED
    assert after[2].manifest.row_count == march.published_count == 7_500
    assert after[2].manifest.canonical_path == _canonical_path(march)
    assert after[2].manifest.checksum_sha256 == before[2].checksum
    assert after[2].manifest.validation_policy_version == (
        f"{fixture.validation_policy}+sessions-sha256:{fixture.schedule_digest}"
    )
