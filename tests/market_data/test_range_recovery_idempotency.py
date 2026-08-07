from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.historical import HistoricalResponse
from swing_trading_ai_assistant.market_data.instruments import Instrument
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
    ScheduleClosure,
    ScheduleEvidenceResult,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    ScheduleSession,
)
from swing_trading_ai_assistant.market_data.schemas import (
    CANDLE_SCHEMA_VERSION,
    CanonicalCandle,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)


class _Clock:
    def __init__(self) -> None:
        self._value = datetime(2026, 3, 1, tzinfo=UTC)

    def now(self) -> datetime:
        value = self._value
        self._value += timedelta(microseconds=1)
        return value


class _Session:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def fetch(self, request: object) -> HistoricalResponse:
        self.requests.append(request)
        month = request.from_date.month  # type: ignore[union-attr]
        return HistoricalResponse(
            200,
            [
                [
                    f"2026-{month:02d}-02T03:45:00+00:00",
                    100.0,
                    101.0,
                    99.0,
                    100.5,
                    10,
                    None,
                ]
            ],
        )


class _SessionFactory:
    def __init__(self) -> None:
        self.open_calls = 0
        self.session = _Session()

    def open(self) -> _Session:
        self.open_calls += 1
        return self.session


class _NeverOpenSessionFactory:
    def __init__(self) -> None:
        self.open_calls = 0

    def open(self) -> object:
        self.open_calls += 1
        raise AssertionError("verified reruns must not resolve a provider session")


@dataclass(frozen=True, slots=True)
class _VerifiedNeighborSnapshot:
    manifest: PartitionManifest
    bytes: bytes
    schedule: ScheduleEvidenceResult


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


def _schedule() -> ExpectedSessionSchedule:
    sessions = (
        ScheduleSession(
            date(2026, 1, 2),
            datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
            datetime(2026, 1, 2, 3, 46, tzinfo=UTC),
            "regular",
        ),
        ScheduleSession(
            date(2026, 2, 2),
            datetime(2026, 2, 2, 3, 45, tzinfo=UTC),
            datetime(2026, 2, 2, 3, 46, tzinfo=UTC),
            "regular",
        ),
    )
    session_dates = {session.trade_date for session in sessions}
    closures: list[ScheduleClosure] = []
    current = date(2026, 1, 1)
    while current <= date(2026, 2, 28):
        if current not in session_dates:
            closures.append(ScheduleClosure(current, "nse-source"))
        current += timedelta(days=1)
    return ExpectedSessionSchedule(
        2,
        "nse",
        "2026-q1",
        datetime(2026, 3, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 1, 1),
        date(2026, 2, 28),
        sessions,
        tuple(closures),
    )


def _plans() -> tuple[PlannedInstrumentMonth, PlannedInstrumentMonth]:
    plans = plan_upstox_equity_months(
        _instrument(), date(2026, 1, 1), date(2026, 2, 28), "1m"
    )
    assert len(plans) == 2
    return plans[0], plans[1]


def _retain_schedule(
    root: Path, schedule: ExpectedSessionSchedule
) -> ScheduleEvidenceResult:
    result = StorageRootLease.try_acquire(root)
    assert result.outcome is LeaseOutcome.ACQUIRED
    assert result.lease is not None
    with result.lease:
        retained = ScheduleEvidenceStore(root, result.lease).retain(schedule)
    assert retained.outcome is ScheduleOutcome.RETAINED
    assert retained.digest is not None
    return retained


def _candle(plan: PlannedInstrumentMonth) -> CanonicalCandle:
    return CanonicalCandle(
        plan.provider,
        plan.instrument_key,
        plan.security_id,
        plan.symbol,
        plan.exchange,
        plan.segment,
        plan.instrument_type,
        None,
        None,
        None,
        None,
        plan.interval,
        datetime(plan.year, plan.month, 2, 3, 45, tzinfo=UTC),
        100.0,
        101.0,
        99.0,
        100.5,
        10,
        None,
        datetime(2026, 3, 1, tzinfo=UTC),
        "upstox-historical-v3",
        "raw",
    )


def _active_manifest(
    plan: PlannedInstrumentMonth, schedule: ScheduleEvidenceResult, run_id: str
) -> PartitionManifest:
    assert schedule.digest is not None
    started = datetime(2026, 2, 1, tzinfo=UTC)
    return PartitionManifest(
        1,
        plan,
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


def _seed_verified(
    root: Path,
    plan: PlannedInstrumentMonth,
    schedule: ScheduleEvidenceResult,
    run_id: str,
) -> None:
    published = publish_partition(root, plan, (_candle(plan),))
    active = _active_manifest(plan, schedule, run_id)
    verified = verify_manifest(
        active,
        datetime(2026, 2, 2, tzinfo=UTC),
        published.actual_from_ts,
        published.actual_to_ts,
        published.row_count,
        published.checksum_sha256,
        published.canonical_path,
    )
    with DuckDBCatalog(root) as catalog:
        catalog.create_manifest(active)
        catalog.transition_manifest(active, verified)


def _seed_in_progress(
    root: Path,
    plan: PlannedInstrumentMonth,
    schedule: ScheduleEvidenceResult,
    run_id: str,
) -> None:
    with DuckDBCatalog(root) as catalog:
        catalog.create_manifest(_active_manifest(plan, schedule, run_id))


def _command(root: Path) -> IngestionCommand:
    return IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, 2, 28),
        "1m",
        root,
        _schedule(),
        "nse-equity-month@v1",
        max_total_provider_attempts=2,
    )


def _coordinator(session_factory: object) -> IngestionCoordinator:
    run = 0

    def run_id() -> str:
        nonlocal run
        run += 1
        return f"ark37-run-{run}"

    return IngestionCoordinator(
        session_factory=session_factory,  # type: ignore[arg-type]
        clock=_Clock(),
        run_id_factory=run_id,
    )


def _requested_months(session_factory: _SessionFactory) -> list[int]:
    return [request.from_date.month for request in session_factory.session.requests]  # type: ignore[union-attr]


def _canonical_path(plan: PlannedInstrumentMonth) -> str:
    return (
        "candles/"
        f"provider={plan.provider}/exchange={plan.exchange}/segment={plan.segment}/"
        f"instrument_type={plan.instrument_type}/security_id={plan.security_id}/"
        f"interval={plan.interval}/year={plan.year:04d}/month={plan.month:02d}/"
        "bars.parquet"
    )


def _verified_manifest(
    root: Path,
    plan: PlannedInstrumentMonth,
    schedule: ScheduleEvidenceResult,
    expected_run_id: str,
) -> PartitionManifest:
    assert schedule.digest is not None
    with DuckDBCatalog(root) as catalog:
        manifest = catalog.get_manifest(plan)
    assert manifest is not None
    artifact_path = root / _canonical_path(plan)
    artifact_bytes = artifact_path.read_bytes()
    assert manifest.plan == plan
    assert manifest.state is ManifestState.VERIFIED
    assert manifest.validation_outcome is ValidationOutcome.PASSED
    assert manifest.failure_category is None
    assert manifest.ingestion_run_id == expected_run_id
    assert manifest.canonical_path == _canonical_path(plan)
    assert manifest.checksum_sha256 == hashlib.sha256(artifact_bytes).hexdigest()
    assert manifest.candle_schema_version == CANDLE_SCHEMA_VERSION
    assert manifest.validation_policy_version == (
        "nse-equity-month@v1+sessions-sha256:" + schedule.digest
    )
    assert manifest.source_version == "upstox-historical-v3"
    assert manifest.row_count == 1
    assert manifest.actual_from_ts == _candle(plan).ts
    assert manifest.actual_to_ts == _candle(plan).ts
    return manifest


def _snapshot_verified_neighbor(
    root: Path,
    plan: PlannedInstrumentMonth,
    schedule: ScheduleEvidenceResult,
    expected_run_id: str,
) -> _VerifiedNeighborSnapshot:
    manifest = _verified_manifest(root, plan, schedule, expected_run_id)
    return _VerifiedNeighborSnapshot(
        manifest, (root / _canonical_path(plan)).read_bytes(), schedule
    )


def _assert_neighbor_unchanged(
    root: Path,
    snapshot: _VerifiedNeighborSnapshot,
) -> None:
    current = _verified_manifest(
        root,
        snapshot.manifest.plan,
        snapshot.schedule,
        snapshot.manifest.ingestion_run_id,
    )
    assert current == snapshot.manifest
    assert (
        root / _canonical_path(snapshot.manifest.plan)
    ).read_bytes() == snapshot.bytes


def _assert_zero_session_rerun(root: Path) -> None:
    sessions = _NeverOpenSessionFactory()
    report = _coordinator(sessions).run(_command(root))
    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.SKIPPED_VERIFIED,
    ]
    assert report.provider_attempt_count == 0
    assert report.skipped_count == 2
    assert sessions.open_calls == 0


def test_restart_skips_verified_month_and_requests_only_interrupted_month(
    tmp_path: Path,
) -> None:
    schedule = _retain_schedule(tmp_path, _schedule())
    january, february = _plans()
    _seed_verified(tmp_path, january, schedule, "seed-jan")
    _seed_in_progress(tmp_path, february, schedule, "interrupted-feb")
    january_before = _snapshot_verified_neighbor(
        tmp_path, january, schedule, "seed-jan"
    )
    sessions = _SessionFactory()

    report = _coordinator(sessions).run(_command(tmp_path))

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.VERIFIED,
    ]
    assert report.skipped_count == 1
    assert report.verified_count == 1
    assert report.provider_attempt_count == 1
    assert sessions.open_calls == 1
    assert _requested_months(sessions) == [2]
    assert report.results[0].provider_attempts == 0
    assert report.results[1].provider_attempts == 1
    assert report.results[1].final_manifest is not None
    assert report.results[1].final_manifest.state is ManifestState.VERIFIED
    _verified_manifest(tmp_path, january, schedule, "seed-jan")
    _verified_manifest(tmp_path, february, schedule, "ark37-run-2")
    _assert_neighbor_unchanged(tmp_path, january_before)
    _assert_zero_session_rerun(tmp_path)


def test_fully_verified_restart_is_zero_session_and_zero_candle_request(
    tmp_path: Path,
) -> None:
    schedule = _retain_schedule(tmp_path, _schedule())
    january, february = _plans()
    _seed_verified(tmp_path, january, schedule, "seed-jan")
    _seed_verified(tmp_path, february, schedule, "seed-feb")
    sessions = _NeverOpenSessionFactory()

    report = _coordinator(sessions).run(_command(tmp_path))

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.SKIPPED_VERIFIED,
    ]
    assert report.provider_attempt_count == 0
    assert report.skipped_count == 2
    assert sessions.open_calls == 0
    _verified_manifest(tmp_path, january, schedule, "seed-jan")
    _verified_manifest(tmp_path, february, schedule, "seed-feb")


def test_checksum_mismatch_repairs_only_the_exact_partition(tmp_path: Path) -> None:
    schedule = _retain_schedule(tmp_path, _schedule())
    january, february = _plans()
    _seed_verified(tmp_path, january, schedule, "seed-jan")
    _seed_verified(tmp_path, february, schedule, "seed-feb")
    february_before = _snapshot_verified_neighbor(
        tmp_path, february, schedule, "seed-feb"
    )
    january_path = tmp_path / _canonical_path(january)
    january_path.write_bytes(january_path.read_bytes() + b"checksum-mismatch")
    sessions = _SessionFactory()

    report = _coordinator(sessions).run(_command(tmp_path))

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.VERIFIED,
        PartitionOutcome.SKIPPED_VERIFIED,
    ]
    assert report.provider_attempt_count == 1
    assert _requested_months(sessions) == [1]
    _verified_manifest(tmp_path, january, schedule, "ark37-run-2")
    _verified_manifest(tmp_path, february, schedule, "seed-feb")
    _assert_neighbor_unchanged(tmp_path, february_before)
    _assert_zero_session_rerun(tmp_path)


def test_missing_canonical_parquet_repairs_only_the_exact_partition(
    tmp_path: Path,
) -> None:
    schedule = _retain_schedule(tmp_path, _schedule())
    january, february = _plans()
    _seed_verified(tmp_path, january, schedule, "seed-jan")
    _seed_verified(tmp_path, february, schedule, "seed-feb")
    january_before = _snapshot_verified_neighbor(
        tmp_path, january, schedule, "seed-jan"
    )
    february_path = tmp_path / _canonical_path(february)
    february_path.unlink()
    sessions = _SessionFactory()

    report = _coordinator(sessions).run(_command(tmp_path))

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.VERIFIED,
    ]
    assert report.provider_attempt_count == 1
    assert _requested_months(sessions) == [2]
    _verified_manifest(tmp_path, january, schedule, "seed-jan")
    _verified_manifest(tmp_path, february, schedule, "ark37-run-2")
    _assert_neighbor_unchanged(tmp_path, january_before)
    _assert_zero_session_rerun(tmp_path)


def test_abandoned_temp_is_not_complete_and_does_not_affect_verified_month(
    tmp_path: Path,
) -> None:
    schedule = _retain_schedule(tmp_path, _schedule())
    january, february = _plans()
    _seed_verified(tmp_path, january, schedule, "seed-jan")
    january_before = _snapshot_verified_neighbor(
        tmp_path, january, schedule, "seed-jan"
    )
    temp = (tmp_path / _canonical_path(february)).parent / (
        ".publish-0123456789abcdef0123456789abcdef.tmp"
    )
    temp.parent.mkdir(parents=True)
    temp.write_bytes(b"abandoned")
    sessions = _SessionFactory()

    report = _coordinator(sessions).run(_command(tmp_path))

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.VERIFIED,
    ]
    assert report.provider_attempt_count == 1
    assert _requested_months(sessions) == [2]
    assert not temp.exists()
    _verified_manifest(tmp_path, january, schedule, "seed-jan")
    _verified_manifest(tmp_path, february, schedule, "ark37-run-2")
    _assert_neighbor_unchanged(tmp_path, january_before)
    _assert_zero_session_rerun(tmp_path)
