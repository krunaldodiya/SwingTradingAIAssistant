"""ARK-89: characterize ordered mixed-range reconciliation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ark74_benchmark_fixture import BenchmarkFixturePartition, benchmark_nse_eq_v1

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.historical import (
    HistoricalRequest,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    publish_partition,
)
from swing_trading_ai_assistant.market_data.partition_reconciliation import (
    RequestReason,
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

_FIXED_NOW = datetime(2024, 4, 1, tzinfo=UTC)


class _FixedClock:
    def now(self) -> datetime:
        return _FIXED_NOW


class _OneResponseSession:
    def __init__(self, response: HistoricalResponse) -> None:
        self._response = response
        self.requests: list[HistoricalRequest] = []

    def fetch(self, request: HistoricalRequest) -> HistoricalResponse:
        self.requests.append(request)
        return self._response


class _OneResponseSessionFactory:
    def __init__(self, response: HistoricalResponse) -> None:
        self.open_calls = 0
        self.session = _OneResponseSession(response)

    def open(self) -> _OneResponseSession:
        self.open_calls += 1
        return self.session


class _RecordingLimiter:
    def __init__(self) -> None:
        self.acquire_calls = 0
        self.defer_calls = 0

    def acquire(self, *_args: object) -> timedelta:
        self.acquire_calls += 1
        return timedelta(0)

    def defer_for(self, *_args: object) -> timedelta:
        self.defer_calls += 1
        return timedelta(0)


class _NeverSleeper:
    def __init__(self) -> None:
        self.calls = 0

    def sleep(self, *_args: object) -> None:
        self.calls += 1
        raise AssertionError("ARK-89 does not retry its one successful request")


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
    assert retained.digest is not None
    return retained


def _seed_verified(
    root: Path,
    partition: BenchmarkFixturePartition,
    schedule: ScheduleEvidenceResult,
) -> PartitionManifest:
    assert schedule.digest is not None
    published = publish_partition(root, partition.plan, partition.canonical_candles)
    started = datetime(2024, 4, 1, tzinfo=UTC)
    active = PartitionManifest(
        1,
        partition.plan,
        "ark89-seed-verified",
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


def _seed_final_without_catalog(
    root: Path, partition: BenchmarkFixturePartition
) -> None:
    published = publish_partition(root, partition.plan, partition.canonical_candles)
    assert published.canonical_path == _canonical_path(partition)
    assert published.row_count == partition.published_count


def _expected_verified_manifest(
    partition: BenchmarkFixturePartition,
    run_id: str,
    schedule_digest: str,
    checksum: str,
) -> PartitionManifest:
    active = PartitionManifest(
        1,
        partition.plan,
        run_id,
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        f"nse-equity-month@v1+sessions-sha256:{schedule_digest}",
        None,
        None,
        None,
        None,
        None,
        partition.canonical_candles[0].source_version,
        _FIXED_NOW,
        _FIXED_NOW,
        _FIXED_NOW,
        None,
    )
    return verify_manifest(
        active,
        _FIXED_NOW,
        partition.canonical_candles[0].ts,
        partition.canonical_candles[-1].ts,
        partition.published_count,
        checksum,
        _canonical_path(partition),
    )


def _snapshot(root: Path, partition: BenchmarkFixturePartition) -> _PartitionSnapshot:
    path = root / _canonical_path(partition)
    data = path.read_bytes()
    with DuckDBCatalog(root) as catalog:
        manifest = catalog.get_manifest(partition.plan)
    return _PartitionSnapshot(manifest, data, hashlib.sha256(data).hexdigest())


def test_d21_orders_verified_skip_local_recovery_and_only_missing_month_request(
    tmp_path: Path,
) -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 1, 1), date(2024, 3, 1))
    january, february, march = fixture.partitions
    schedule = _retain_schedule(tmp_path, fixture.schedule)
    january_manifest = _seed_verified(tmp_path, january, schedule)
    _seed_final_without_catalog(tmp_path, february)
    january_before = _snapshot(tmp_path, january)
    february_before = _snapshot(tmp_path, february)
    schedule_path = (
        tmp_path / "calendar-schedules" / "sha256" / f"{fixture.schedule_digest}.json"
    )
    schedule_before = schedule_path.read_bytes()
    sessions = _OneResponseSessionFactory(march.response)
    limiter = _RecordingLimiter()
    sleeper = _NeverSleeper()
    run_ids = iter(("ark89-recovery", "ark89-fetch", "ark89-request"))
    coordinator = IngestionCoordinator(
        session_factory=sessions,
        limiter=limiter,
        sleeper=sleeper,
        clock=_FixedClock(),
        run_id_factory=lambda: next(run_ids),
    )
    command = IngestionCommand(
        fixture.instrument,
        date(2024, 1, 1),
        date(2024, 3, 31),
        "1m",
        tmp_path,
        fixture.schedule,
        fixture.validation_policy,
        max_total_provider_attempts=1,
    )

    report = coordinator.run(command)

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert [result.plan for result in report.results] == [
        january.plan,
        february.plan,
        march.plan,
    ]
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.RECOVERED_LOCALLY,
        PartitionOutcome.VERIFIED,
    ]
    assert [result.reconciliation_reasons for result in report.results] == [
        (),
        (),
        (RequestReason.MISSING_EVIDENCE,),
    ]
    assert [result.ingestion_run_id for result in report.results] == [
        "ark89-seed-verified",
        "ark89-recovery",
        "ark89-request",
    ]
    assert [result.provider_attempts for result in report.results] == [0, 0, 1]
    assert report.planned_count == 3
    assert (
        report.skipped_count
        == report.locally_recovered_count
        == report.verified_count
        == 1
    )
    assert report.provider_attempt_count == 1
    assert (
        report.failed_count == report.not_attempted_count == report.cancelled_count == 0
    )
    assert (
        sessions.open_calls
        == len(sessions.session.requests)
        == limiter.acquire_calls
        == 1
    )
    assert limiter.defer_calls == sleeper.calls == 0
    assert sessions.session.requests == [
        HistoricalRequest(
            fixture.instrument.instrument_key,
            "minutes",
            1,
            date(2024, 3, 1),
            date(2024, 3, 31),
        )
    ]
    assert schedule_path.read_bytes() == schedule_before == fixture.schedule_bytes

    january_after = _snapshot(tmp_path, january)
    february_after = _snapshot(tmp_path, february)
    march_after = _snapshot(tmp_path, march)
    expected_manifests = (
        _expected_verified_manifest(
            january,
            "ark89-seed-verified",
            fixture.schedule_digest,
            january_before.checksum,
        ),
        _expected_verified_manifest(
            february,
            "ark89-recovery",
            fixture.schedule_digest,
            february_before.checksum,
        ),
        _expected_verified_manifest(
            march,
            "ark89-request",
            fixture.schedule_digest,
            march_after.checksum,
        ),
    )
    expected_results = (
        PartitionResult(
            january.plan,
            PartitionOutcome.SKIPPED_VERIFIED,
            (),
            "ark89-seed-verified",
            0,
            expected_manifests[0],
            None,
            None,
        ),
        PartitionResult(
            february.plan,
            PartitionOutcome.RECOVERED_LOCALLY,
            (),
            "ark89-recovery",
            0,
            expected_manifests[1],
            None,
            None,
        ),
        PartitionResult(
            march.plan,
            PartitionOutcome.VERIFIED,
            (RequestReason.MISSING_EVIDENCE,),
            "ark89-request",
            1,
            expected_manifests[2],
            None,
            None,
        ),
    )
    expected_report = IngestionReport(
        IngestionRunOutcome.SUCCEEDED,
        RunFailureCode.NONE,
        expected_results,
        3,
        1,
        1,
        1,
        1,
        0,
        0,
        0,
        _FIXED_NOW,
        _FIXED_NOW,
    )

    assert type(report) is IngestionReport
    assert all(type(result) is PartitionResult for result in report.results)
    assert report.results == expected_results
    assert report == expected_report
    assert (
        tuple(result.final_manifest for result in report.results) == expected_manifests
    )
    assert january_after == january_before
    assert january_after.manifest == january_manifest == expected_manifests[0]
    assert february_after.bytes == february_before.bytes
    assert february_after.checksum == february_before.checksum
    assert february_after.manifest == expected_manifests[1]
    assert march_after.manifest == expected_manifests[2]
