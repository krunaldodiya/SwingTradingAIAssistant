"""ARK-83 cancellation/crash mapping regression evidence."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.historical import (
    CancellationRequested,
    CancellationToken,
    HistoricalFetchResult,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    fail_manifest,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.partition_ingestion import (
    PartitionIngestionExecutor,
    PartitionLifecycleOutcome,
    PartitionLifecycleResult,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    PublicationOutcome,
    PublishedPartitionEvidence,
    publish_partition,
)
from swing_trading_ai_assistant.market_data.partition_recovery import (
    PartitionRecoveryOutcome,
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
    ScheduleFailureCode,
    ScheduleOutcome,
    ScheduleSession,
    canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)
from swing_trading_ai_assistant.market_data.validation import (
    EquityMonthValidationPolicy,
)


class _CancellingBeforeTerminalTransitionClock:
    def __init__(self, cancellation: CancellationToken) -> None:
        self._cancellation = cancellation
        self._calls = 0

    def now(self) -> datetime:
        self._calls += 1
        if self._calls == 2:
            self._cancellation.cancel()
        return datetime(2026, 2, 1, tzinfo=UTC) + timedelta(microseconds=self._calls)


class _OneResponseFetcher:
    def __init__(self) -> None:
        self.calls: list[PlannedInstrumentMonth] = []

    def fetch(self, plan: PlannedInstrumentMonth) -> HistoricalFetchResult:
        self.calls.append(plan)
        return HistoricalFetchResult(
            HistoricalResponse(
                200,
                [["2026-01-02T03:45:00+00:00", 100.0, 101.0, 99.0, 100.5, 10, None]],
            ),
            attempts=1,
            retrieved_at=datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        )


class _Catalog:
    def __init__(self) -> None:
        self.current: PartitionManifest | None = None
        self.transitions: list[PartitionManifest] = []

    def get_manifest(self, _plan: PlannedInstrumentMonth) -> PartitionManifest | None:
        return self.current

    def create_manifest(self, manifest: PartitionManifest) -> None:
        self.current = manifest

    def transition_manifest(
        self, current: PartitionManifest, target: PartitionManifest
    ) -> None:
        assert self.current == current
        self.transitions.append(target)
        self.current = target


def _plan() -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|INE002A01018",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2026,
        1,
        date(2026, 1, 1),
        date(2026, 1, 31),
    )


def _instrument() -> Instrument:
    return Instrument(
        "NSE_EQ|INE002A01018",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "INE002A01018",
    )


def _schedule_evidence() -> ScheduleEvidenceResult:
    schedule = ExpectedSessionSchedule(
        1,
        "nse",
        "2026-01",
        datetime(2026, 2, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 1, 1),
        date(2026, 1, 31),
        (
            ScheduleSession(
                date(2026, 1, 2),
                datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
                datetime(2026, 1, 2, 3, 46, tzinfo=UTC),
                "regular",
            ),
        ),
    )
    canonical = canonical_schedule_bytes(schedule)
    digest = schedule_digest(schedule)
    return ScheduleEvidenceResult(
        ScheduleOutcome.RESOLVED,
        ScheduleFailureCode.NONE,
        schedule,
        canonical,
        digest,
        f"calendar-schedules/sha256/{digest}.json",
    )


def _published(plan: PlannedInstrumentMonth) -> PublishedPartitionEvidence:
    return PublishedPartitionEvidence(
        plan,
        PublicationOutcome.PUBLISHED,
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/instrument_type=EQ/"
        "security_id=INE002A01018/interval=1m/year=2026/month=01/bars.parquet",
        "a" * 64,
        1,
        1,
        datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        "upstox-historical-v3",
        128,
    )


def test_cancellation_immediately_before_terminal_catalog_transition_is_interrupted(
    tmp_path: Path,
) -> None:
    plan = _plan()
    cancellation = CancellationToken()
    catalog = _Catalog()
    fetcher = _OneResponseFetcher()
    executor = PartitionIngestionExecutor(
        instrument=_instrument(),
        expected_sessions=_schedule_evidence(),
        validation_policy=EquityMonthValidationPolicy("nse-equity-month@v1"),
        fetcher=fetcher,
        catalog=catalog,
        storage_root=tmp_path,
        clock=_CancellingBeforeTerminalTransitionClock(cancellation),
        run_id="ark83-run",
        cancellation=cancellation,
        publisher=lambda _root, actual_plan, _candles: _published(actual_plan),
    )

    result = executor.execute(plan)

    assert result.outcome is PartitionLifecycleOutcome.CANCELLED
    assert result.provider_attempts == 1
    assert result.failure_category is FailureCategory.INTERRUPTED
    assert result.error_code == "CANCELLED"
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.FAILED
    assert result.final_manifest.failure_category is FailureCategory.INTERRUPTED
    published = _published(plan)
    assert result.final_manifest.canonical_path == published.canonical_path
    assert result.final_manifest.checksum_sha256 == published.checksum_sha256
    assert (
        result.final_manifest.candle_schema_version == published.candle_schema_version
    )
    assert result.final_manifest.row_count == published.row_count
    assert result.final_manifest.actual_from_ts == published.actual_from_ts
    assert result.final_manifest.actual_to_ts == published.actual_to_ts
    assert fetcher.calls == [plan]
    assert [manifest.state for manifest in catalog.transitions] == [
        ManifestState.FAILED
    ]


class _FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        value = self._value
        self._value += timedelta(microseconds=1)
        return value


class _RecordingSession:
    def __init__(self, responses: list[HistoricalResponse]) -> None:
        self._responses = responses
        self.open_calls = 0
        self.requests: list[object] = []

    def open(self) -> _RecordingSession:
        self.open_calls += 1
        return self

    def fetch(self, request: object) -> HistoricalResponse:
        self.requests.append(request)
        return self._responses.pop(0)


class _RecordingLimiter:
    def __init__(self) -> None:
        self.acquires: list[timedelta] = []
        self.deferrals: list[tuple[timedelta, timedelta]] = []

    def acquire(
        self, _cancellation: CancellationToken, remaining_wait: timedelta
    ) -> timedelta:
        self.acquires.append(remaining_wait)
        return timedelta(0)

    def defer_for(self, delay: timedelta, remaining_wait: timedelta) -> timedelta:
        self.deferrals.append((delay, remaining_wait))
        return timedelta(0)


class _CancellingLimiter(_RecordingLimiter):
    def acquire(
        self, cancellation: CancellationToken, remaining_wait: timedelta
    ) -> timedelta:
        self.acquires.append(remaining_wait)
        cancellation.cancel()
        raise CancellationRequested


class _RecordingSleeper:
    def __init__(self) -> None:
        self.delays: list[timedelta] = []

    def sleep(self, delay: timedelta, _cancellation: CancellationToken) -> None:
        self.delays.append(delay)


class _NoManifestCatalog:
    def __enter__(self) -> _NoManifestCatalog:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _FixedScheduleStore:
    def __init__(self, schedule: ExpectedSessionSchedule) -> None:
        self._schedule = schedule

    def retain(self, _schedule: ExpectedSessionSchedule) -> ScheduleEvidenceResult:
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


def _range_schedule(last_month: int) -> ExpectedSessionSchedule:
    last_day = 28 if last_month == 2 else 31
    sessions = tuple(
        ScheduleSession(
            date(2026, month, 2),
            datetime(2026, month, 2, 3, 45, tzinfo=UTC),
            datetime(2026, month, 2, 3, 46, tzinfo=UTC),
            "regular",
        )
        for month in range(1, last_month + 1)
    )
    covered_from = date(2026, 1, 1)
    covered_to = date(2026, last_month, last_day)
    session_dates = {session.trade_date for session in sessions}
    closures: list[ScheduleClosure] = []
    current = covered_from
    while current <= covered_to:
        if current not in session_dates:
            closures.append(ScheduleClosure(current, "nse-source"))
        current += timedelta(days=1)
    return ExpectedSessionSchedule(
        2,
        "nse",
        "2026-q1",
        datetime(2026, 4, 1, tzinfo=UTC),
        "Asia/Kolkata",
        covered_from,
        covered_to,
        sessions,
        tuple(closures),
    )


def _range_command(
    root: Path, schedule: ExpectedSessionSchedule, last_month: int
) -> IngestionCommand:
    return IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, last_month, 28 if last_month == 2 else 31),
        "1m",
        root,
        schedule,
        "nse-equity-month@v1",
        max_total_provider_attempts=last_month,
    )


def _plan_for_month(month: int) -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|INE002A01018",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2026,
        month,
        date(2026, month, 1),
        date(2026, month, 28 if month == 2 else 31),
    )


def _request_observer(**_kwargs: object) -> SimpleNamespace:
    def observe(plan: PlannedInstrumentMonth) -> SimpleNamespace:
        return SimpleNamespace(
            plan=plan,
            outcome=PartitionRecoveryOutcome.REQUEST_REQUIRED,
            final_manifest=None,
            evidence=None,
            failure_category=None,
            error_code=None,
        )

    return SimpleNamespace(observe=observe)


def _active_manifest(plan: PlannedInstrumentMonth, run_id: str) -> PartitionManifest:
    started = datetime(2026, 4, 1, tzinfo=UTC)
    return PartitionManifest(
        1,
        plan,
        run_id,
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        "nse-equity-month@v1+sessions-sha256:" + "a" * 64,
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


def _lifecycle_result(
    plan: PlannedInstrumentMonth,
    run_id: str,
    outcome: PartitionLifecycleOutcome,
) -> PartitionLifecycleResult:
    active = _active_manifest(plan, run_id)
    timestamp = datetime(plan.year, plan.month, 2, 3, 45, tzinfo=UTC)
    if outcome is PartitionLifecycleOutcome.VERIFIED:
        return PartitionLifecycleResult(
            plan,
            outcome,
            run_id,
            1,
            verify_manifest(
                active,
                active.updated_at + timedelta(microseconds=1),
                timestamp,
                timestamp,
                1,
                "a" * 64,
                "canonical.parquet",
            ),
            None,
            None,
        )
    category = (
        FailureCategory.INTERRUPTED
        if outcome is PartitionLifecycleOutcome.CANCELLED
        else FailureCategory.PROVIDER_NON_RETRYABLE
    )
    return PartitionLifecycleResult(
        plan,
        outcome,
        run_id,
        1,
        fail_manifest(active, active.updated_at + timedelta(microseconds=1), category),
        category,
        "CANCELLED"
        if outcome is PartitionLifecycleOutcome.CANCELLED
        else "PROVIDER_CLIENT",
    )


def _fake_range_coordinator(
    schedule: ExpectedSessionSchedule,
    session: _RecordingSession,
    limiter: _RecordingLimiter,
    sleeper: _RecordingSleeper,
    cancellation: CancellationToken,
    lifecycle_factory: object,
) -> IngestionCoordinator:
    return IngestionCoordinator(
        session_factory=session,
        limiter=limiter,  # type: ignore[arg-type]
        clock=_FixedClock(datetime(2026, 4, 1, tzinfo=UTC)),
        cancellation=cancellation,
        sleeper=sleeper,  # type: ignore[arg-type]
        run_id_factory=lambda: "ark83-run",
        lease_acquirer=StorageRootLease.try_acquire,
        catalog_factory=lambda _root: _NoManifestCatalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _FixedScheduleStore(schedule),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    )


def test_cancellation_during_initial_limiter_wait_preserves_no_request_evidence(
    tmp_path: Path,
) -> None:
    schedule = _range_schedule(1)
    cancellation = CancellationToken()
    session = _RecordingSession([])
    limiter = _CancellingLimiter()
    sleeper = _RecordingSleeper()

    report = IngestionCoordinator(
        session_factory=session,
        limiter=limiter,  # type: ignore[arg-type]
        clock=_FixedClock(datetime(2026, 3, 1, tzinfo=UTC)),
        cancellation=cancellation,
        sleeper=sleeper,  # type: ignore[arg-type]
        run_id_factory=lambda: "ark83-limiter",
    ).run(_range_command(tmp_path, schedule, 1))

    assert report.results[0].error_code == "CANCELLED"
    assert report.outcome is IngestionRunOutcome.CANCELLED
    assert report.failure_code is RunFailureCode.CANCELLED
    assert [result.outcome for result in report.results] == [PartitionOutcome.CANCELLED]
    assert report.planned_count == report.cancelled_count == 1
    assert (
        report.provider_attempt_count
        == report.failed_count
        == report.not_attempted_count
        == 0
    )
    assert session.open_calls == len(limiter.acquires) == 1
    assert session.requests == []
    assert limiter.deferrals == []
    assert sleeper.delays == []
    assert report.results[0].final_manifest is not None
    assert report.results[0].final_manifest.state is ManifestState.FAILED
    assert report.results[0].failure_category is FailureCategory.INTERRUPTED
    assert report.results[0].error_code == "CANCELLED"


def test_between_partitions_cancellation_retains_failed_result_and_stops_later_work(
    tmp_path: Path,
) -> None:
    schedule = _range_schedule(2)
    cancellation = CancellationToken()
    session = _RecordingSession([])
    limiter = _RecordingLimiter()
    sleeper = _RecordingSleeper()
    executed: list[PlannedInstrumentMonth] = []

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: PlannedInstrumentMonth) -> PartitionLifecycleResult:
            executed.append(plan)
            cancellation.cancel()
            return _lifecycle_result(
                plan,
                kwargs["run_id"],
                PartitionLifecycleOutcome.FAILED,  # type: ignore[arg-type]
            )

        return SimpleNamespace(execute=execute)

    report = _fake_range_coordinator(
        schedule, session, limiter, sleeper, cancellation, lifecycle_factory
    ).run(_range_command(tmp_path, schedule, 2))

    assert report.outcome is IngestionRunOutcome.CANCELLED
    assert report.failure_code is RunFailureCode.CANCELLED
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.FAILED,
        PartitionOutcome.CANCELLED,
    ]
    assert report.planned_count == 2
    assert (
        report.failed_count
        == report.cancelled_count
        == report.provider_attempt_count
        == 1
    )
    assert report.not_attempted_count == report.verified_count == 0
    assert executed == [report.results[0].plan]
    assert session.requests == []
    assert limiter.acquires == limiter.deferrals == []
    assert sleeper.delays == []
    assert report.results[0].error_code == "PROVIDER_CLIENT"
    assert report.results[1].error_code == "CANCELLED"


def test_in_flight_cancellation_after_completed_partition_is_partial_and_ordered(
    tmp_path: Path,
) -> None:
    schedule = _range_schedule(3)
    cancellation = CancellationToken()
    session = _RecordingSession([])
    limiter = _RecordingLimiter()
    sleeper = _RecordingSleeper()
    executed: list[PlannedInstrumentMonth] = []

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: PlannedInstrumentMonth) -> PartitionLifecycleResult:
            executed.append(plan)
            outcome = (
                PartitionLifecycleOutcome.VERIFIED
                if len(executed) == 1
                else PartitionLifecycleOutcome.CANCELLED
            )
            if outcome is PartitionLifecycleOutcome.CANCELLED:
                cancellation.cancel()
            return _lifecycle_result(plan, kwargs["run_id"], outcome)  # type: ignore[arg-type]

        return SimpleNamespace(execute=execute)

    report = _fake_range_coordinator(
        schedule, session, limiter, sleeper, cancellation, lifecycle_factory
    ).run(_range_command(tmp_path, schedule, 3))

    assert report.outcome is IngestionRunOutcome.PARTIAL
    assert report.failure_code is RunFailureCode.CANCELLED
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.VERIFIED,
        PartitionOutcome.CANCELLED,
        PartitionOutcome.NOT_ATTEMPTED,
    ]
    assert report.planned_count == 3
    assert (
        report.verified_count
        == report.cancelled_count
        == report.not_attempted_count
        == 1
    )
    assert report.provider_attempt_count == 2
    assert report.failed_count == 0
    assert executed == [report.results[0].plan, report.results[1].plan]
    assert session.requests == []
    assert limiter.acquires == limiter.deferrals == []
    assert sleeper.delays == []
    assert report.results[1].error_code == "CANCELLED"


def test_post_terminal_cancellation_preserves_partial_and_failed_precedence(
    tmp_path: Path,
) -> None:
    cases = (
        (
            (PartitionLifecycleOutcome.VERIFIED, PartitionLifecycleOutcome.FAILED),
            IngestionRunOutcome.PARTIAL,
            1,
            1,
        ),
        (
            (PartitionLifecycleOutcome.FAILED, PartitionLifecycleOutcome.FAILED),
            IngestionRunOutcome.FAILED,
            0,
            2,
        ),
    )
    for outcomes, expected_outcome, verified_count, failed_count in cases:
        root = tmp_path / expected_outcome.value
        root.mkdir()
        schedule = _range_schedule(2)
        cancellation = CancellationToken()
        session = _RecordingSession([])
        limiter = _RecordingLimiter()
        sleeper = _RecordingSleeper()
        executed: list[PlannedInstrumentMonth] = []

        def lifecycle_factory(
            _outcomes: tuple[PartitionLifecycleOutcome, ...] = outcomes,
            _cancellation: CancellationToken = cancellation,
            _executed: list[PlannedInstrumentMonth] = executed,
            **kwargs: object,
        ) -> SimpleNamespace:
            def execute(plan: PlannedInstrumentMonth) -> PartitionLifecycleResult:
                _executed.append(plan)
                outcome = _outcomes[len(_executed) - 1]
                if len(_executed) == len(_outcomes):
                    _cancellation.cancel()
                return _lifecycle_result(plan, kwargs["run_id"], outcome)  # type: ignore[arg-type]

            return SimpleNamespace(execute=execute)

        report = _fake_range_coordinator(
            schedule, session, limiter, sleeper, cancellation, lifecycle_factory
        ).run(_range_command(root, schedule, 2))

        assert report.outcome is expected_outcome
        assert report.failure_code is RunFailureCode.PARTITION_FAILURE
        assert report.planned_count == report.provider_attempt_count == 2
        assert report.verified_count == verified_count
        assert report.failed_count == failed_count
        assert report.cancelled_count == report.not_attempted_count == 0
        assert len(executed) == 2
        assert session.requests == []
        assert limiter.acquires == limiter.deferrals == []
        assert sleeper.delays == []
        assert all(result.error_code != "CANCELLED" for result in report.results)


def _canonical_path(plan: PlannedInstrumentMonth) -> Path:
    return Path(
        "candles/"
        f"provider={plan.provider}/exchange={plan.exchange}/segment={plan.segment}/"
        f"instrument_type={plan.instrument_type}/security_id={plan.security_id}/"
        f"interval={plan.interval}/year={plan.year:04d}/month={plan.month:02d}/"
        "bars.parquet"
    )


def _canonical_candle(plan: PlannedInstrumentMonth) -> CanonicalCandle:
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
        datetime(2026, 4, 1, tzinfo=UTC),
        "upstox-historical-v3",
        "raw",
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


def _recovery_active_manifest(
    plan: PlannedInstrumentMonth, schedule: ScheduleEvidenceResult, run_id: str
) -> PartitionManifest:
    assert schedule.digest is not None
    started = datetime(2026, 4, 1, tzinfo=UTC)
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


def _seed_verified_partition(
    root: Path,
    plan: PlannedInstrumentMonth,
    schedule: ScheduleEvidenceResult,
    run_id: str,
) -> None:
    published = publish_partition(root, plan, (_canonical_candle(plan),))
    active = _recovery_active_manifest(plan, schedule, run_id)
    verified = verify_manifest(
        active,
        active.updated_at + timedelta(microseconds=1),
        published.actual_from_ts,
        published.actual_to_ts,
        published.row_count,
        published.checksum_sha256,
        published.canonical_path,
    )
    with DuckDBCatalog(root) as catalog:
        catalog.create_manifest(active)
        catalog.transition_manifest(active, verified)


def _seed_in_progress_partition(
    root: Path,
    plan: PlannedInstrumentMonth,
    schedule: ScheduleEvidenceResult,
    run_id: str,
) -> None:
    with DuckDBCatalog(root) as catalog:
        catalog.create_manifest(_recovery_active_manifest(plan, schedule, run_id))


def _stored_manifest(root: Path, plan: PlannedInstrumentMonth) -> PartitionManifest:
    with DuckDBCatalog(root) as catalog:
        manifest = catalog.get_manifest(plan)
    assert manifest is not None
    return manifest


def test_in_progress_valid_final_recovers_locally_without_provider_or_limiter(
    tmp_path: Path,
) -> None:
    schedule = _range_schedule(2)
    retained = _retain_schedule(tmp_path, schedule)
    january, february = (_plan_for_month(1), _plan_for_month(2))
    _seed_verified_partition(tmp_path, january, retained, "neighbor-run")
    publish_partition(tmp_path, february, (_canonical_candle(february),))
    _seed_in_progress_partition(tmp_path, february, retained, "crashed-run")
    january_path = tmp_path / _canonical_path(january)
    february_path = tmp_path / _canonical_path(february)
    january_bytes = january_path.read_bytes()
    january_checksum = hashlib.sha256(january_bytes).hexdigest()
    february_bytes = february_path.read_bytes()
    session = _RecordingSession([])
    limiter = _RecordingLimiter()

    report = IngestionCoordinator(
        session_factory=session,
        limiter=limiter,  # type: ignore[arg-type]
        clock=_FixedClock(datetime(2026, 4, 1, tzinfo=UTC)),
        run_id_factory=lambda: "ark83-recovery",
    ).run(_range_command(tmp_path, schedule, 2))

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.RECOVERED_LOCALLY,
    ]
    assert report.planned_count == 2
    assert report.skipped_count == report.locally_recovered_count == 1
    assert report.provider_attempt_count == report.verified_count == 0
    assert session.open_calls == len(session.requests) == len(limiter.acquires) == 0
    assert january_path.read_bytes() == january_bytes
    assert hashlib.sha256(january_path.read_bytes()).hexdigest() == january_checksum
    assert february_path.read_bytes() == february_bytes
    assert _stored_manifest(tmp_path, february).state is ManifestState.VERIFIED


def test_in_progress_invalid_final_quarantines_only_target_then_requests_once(
    tmp_path: Path,
) -> None:
    schedule = _range_schedule(2)
    retained = _retain_schedule(tmp_path, schedule)
    january, february = (_plan_for_month(1), _plan_for_month(2))
    _seed_verified_partition(tmp_path, january, retained, "neighbor-run")
    target = tmp_path / _canonical_path(february)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"not-a-parquet-file")
    temporary = target.parent / (".publish-" + "a" * 32 + ".tmp")
    temporary.write_bytes(b"abandoned")
    _seed_in_progress_partition(tmp_path, february, retained, "crashed-run")
    january_path = tmp_path / _canonical_path(january)
    january_bytes = january_path.read_bytes()
    january_checksum = hashlib.sha256(january_bytes).hexdigest()
    session = _RecordingSession(
        [
            HistoricalResponse(
                200,
                [["2026-02-02T03:45:00+00:00", 100.0, 101.0, 99.0, 100.5, 10, None]],
            )
        ]
    )
    limiter = _RecordingLimiter()

    report = IngestionCoordinator(
        session_factory=session,
        limiter=limiter,  # type: ignore[arg-type]
        clock=_FixedClock(datetime(2026, 4, 1, tzinfo=UTC)),
        run_id_factory=lambda: "ark83-repair",
    ).run(_range_command(tmp_path, schedule, 2))

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.VERIFIED,
    ]
    assert report.planned_count == 2
    assert report.skipped_count == report.verified_count == 1
    assert report.provider_attempt_count == 1
    assert session.open_calls == len(session.requests) == len(limiter.acquires) == 1
    assert session.requests[0].from_date == date(2026, 2, 1)  # type: ignore[union-attr]
    assert limiter.deferrals == []
    assert not temporary.exists()
    quarantines = tuple(target.parent.glob(".quarantine-*.parquet"))
    assert len(quarantines) == 1
    assert quarantines[0].read_bytes() == b"not-a-parquet-file"
    assert january_path.read_bytes() == january_bytes
    assert hashlib.sha256(january_path.read_bytes()).hexdigest() == january_checksum
    assert target.exists()
    assert _stored_manifest(tmp_path, february).state is ManifestState.VERIFIED
