from __future__ import annotations

import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import swing_trading_ai_assistant.market_data.partition_publication as publication_module
import swing_trading_ai_assistant.market_data.range_ingestion as ingestion_module
import swing_trading_ai_assistant.market_data.validation as validation_module
from swing_trading_ai_assistant.market_data.catalog import (
    CatalogPersistenceError,
    DuckDBCatalog,
)
from swing_trading_ai_assistant.market_data.historical import (
    CancellationToken,
    HistoricalFetchCode,
    HistoricalFetchResult,
    HistoricalResponse,
    RetryPolicy,
)
from swing_trading_ai_assistant.market_data.http import ProviderErrorCategory
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
    plan_upstox_equity_months,
)
from swing_trading_ai_assistant.market_data.partition_ingestion import (
    PartitionCatalogFailure,
    PartitionClockFailure,
    PartitionIngestionExecutor,
    PartitionLifecycleConflict,
    PartitionLifecycleOutcome,
    PartitionLifecycleResult,
)
from swing_trading_ai_assistant.market_data.partition_reconciliation import (
    PartitionEvidence,
    RequestReason,
)
from swing_trading_ai_assistant.market_data.partition_recovery import (
    PartitionRecoveryOutcome,
    PartitionRecoveryResult,
)
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionReport,
    IngestionRunOutcome,
    PartitionOutcome,
    PartitionResult,
    ProviderSessionAuthenticationError,
    ProviderSessionAuthorizationError,
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
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseFailureCode,
    LeaseOutcome,
    LeaseResult,
    StorageRootLease,
    StorageRootLeaseError,
)


def test_default_noop_limiter_accepts_the_cancellation_aware_protocol() -> None:
    assert ingestion_module._NoopLimiter().defer_for(
        timedelta(seconds=1),
        timedelta(seconds=1),
        CancellationToken(),
    ) == timedelta(0)


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
    session = ScheduleSession(
        date(2026, 1, 2),
        datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        datetime(2026, 1, 2, 3, 46, tzinfo=UTC),
        "regular",
    )
    return ExpectedSessionSchedule(
        2,
        "nse",
        "2026-01",
        datetime(2026, 2, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 1, 1),
        date(2026, 1, 31),
        (session,),
        _closures(date(2026, 1, 1), date(2026, 1, 31), (session,)),
    )


def _wide_schedule() -> ExpectedSessionSchedule:
    schedule = _schedule()
    return ExpectedSessionSchedule(
        schedule.schema_version,
        schedule.source,
        "2026-Q1",
        datetime(2026, 3, 1, tzinfo=UTC),
        schedule.timezone,
        date(2026, 1, 1),
        date(2026, 2, 28),
        schedule.sessions,
        _closures(date(2026, 1, 1), date(2026, 2, 28), schedule.sessions),
    )


def _closures(
    covered_from: date,
    covered_to: date,
    sessions: tuple[ScheduleSession, ...],
) -> tuple[ScheduleClosure, ...]:
    session_dates = {session.trade_date for session in sessions}
    closures: list[ScheduleClosure] = []
    current = covered_from
    while current <= covered_to:
        if current not in session_dates:
            closures.append(ScheduleClosure(current, "nse-source"))
        current += timedelta(days=1)
    return tuple(closures)


def _in_progress_manifest(plan: object, run_id: str) -> PartitionManifest:
    assert hasattr(plan, "from_date")
    started = datetime(2026, 3, 1, tzinfo=UTC)
    return PartitionManifest(
        1,
        plan,  # type: ignore[arg-type]
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
    outcome: PartitionLifecycleOutcome,
    run_id: str,
    *,
    attempts: int = 1,
    error_code: str | None = None,
) -> PartitionLifecycleResult:
    active = _in_progress_manifest(plan, run_id)
    if outcome is PartitionLifecycleOutcome.VERIFIED:
        verified = verify_manifest(
            active,
            active.updated_at + timedelta(microseconds=1),
            datetime(plan.year, plan.month, 2, 3, 45, tzinfo=UTC),
            datetime(plan.year, plan.month, 2, 3, 45, tzinfo=UTC),
            1,
            "a" * 64,
            "canonical.parquet",
        )
        return PartitionLifecycleResult(
            plan,
            outcome,
            run_id,
            attempts,
            verified,
            None,
            None,
        )
    if outcome is PartitionLifecycleOutcome.CANCELLED and attempts == 0:
        return PartitionLifecycleResult(
            plan,
            outcome,
            run_id,
            0,
            None,
            None,
            "CANCELLED",
        )
    category = (
        FailureCategory.INTERRUPTED
        if outcome is PartitionLifecycleOutcome.CANCELLED
        else FailureCategory.PROVIDER_NON_RETRYABLE
    )
    failed = fail_manifest(
        active, active.updated_at + timedelta(microseconds=1), category
    )
    return PartitionLifecycleResult(
        plan,
        outcome,
        run_id,
        attempts,
        failed,
        category,
        "CANCELLED" if outcome is PartitionLifecycleOutcome.CANCELLED else error_code,
    )


class _Lease:
    def __enter__(self) -> _Lease:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _Catalog:
    def __enter__(self) -> _Catalog:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get_manifest(self, _plan: PlannedInstrumentMonth) -> None:
        return None


class _ScheduleStore:
    def __init__(self, schedule: ExpectedSessionSchedule) -> None:
        self.schedule = schedule

    def retain(self, _schedule: ExpectedSessionSchedule) -> ScheduleEvidenceResult:
        canonical = canonical_schedule_bytes(self.schedule)
        return ScheduleEvidenceResult(
            ScheduleOutcome.RETAINED,
            ScheduleFailureCode.NONE,
            self.schedule,
            canonical,
            schedule_digest(self.schedule),
            "calendar-schedules/sha256/" + schedule_digest(self.schedule) + ".json",
        )


def _lease(root: Path) -> LeaseResult:
    return StorageRootLease.try_acquire(root)


def _request_observer(**_kwargs: object) -> SimpleNamespace:
    def observe(plan: object) -> SimpleNamespace:
        return SimpleNamespace(
            plan=plan,
            outcome=PartitionRecoveryOutcome.REQUEST_REQUIRED,
            final_manifest=None,
            evidence=None,
            failure_category=None,
            error_code=None,
        )

    return SimpleNamespace(observe=observe)


def _skip_observer(**_kwargs: object) -> SimpleNamespace:
    def observe(plan: object) -> SimpleNamespace:
        assert hasattr(plan, "from_date")
        evidence = PartitionEvidence(
            plan,  # type: ignore[arg-type]
            True,
            True,
            "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
            "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
            "year=2026/month=01/bars.parquet",
            "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
            "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
            "year=2026/month=01/bars.parquet",
            "a" * 64,
            "a" * 64,
            1,
            1,
            True,
            date(2026, 1, 1),
            date(2026, 1, 31),
            True,
            True,
        )
        return SimpleNamespace(
            plan=plan,
            outcome=PartitionRecoveryOutcome.SKIPPED_VERIFIED,
            final_manifest=None,
            evidence=evidence,
            failure_category=None,
            error_code=None,
        )

    return SimpleNamespace(observe=observe)


def _coordinator(
    observer_factory: object,
    *,
    session_factory: object | None = None,
    lifecycle_factory: object | None = None,
    limiter: object | None = None,
    sleeper: object | None = None,
    cancellation: CancellationToken | None = None,
    schedule: ExpectedSessionSchedule | None = None,
) -> IngestionCoordinator:
    return IngestionCoordinator(
        session_factory=session_factory,  # type: ignore[arg-type]
        limiter=limiter,  # type: ignore[arg-type]
        sleeper=sleeper,  # type: ignore[arg-type]
        cancellation=cancellation,
        lease_acquirer=_lease,
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(  # type: ignore[arg-type]
            schedule or _wide_schedule()
        ),
        recovery_observer_factory=observer_factory,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory or PartitionIngestionExecutor,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("stage", ("serialization", "retention", "recovery"))
@pytest.mark.parametrize("caller_lease", (False, True))
def test_internal_schedule_and_recovery_faults_escape_range_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    caller_lease: bool,
) -> None:
    failure = ValueError("private-range-implementation-fault")
    provider_calls: list[object] = []

    def fail(*_args: object) -> None:
        raise failure

    def unexpected_provider() -> None:
        provider_calls.append(object())
        raise AssertionError("provider must not run after local failure")

    def faulting_observer(**_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(observe=fail)

    command = IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, 1, 31),
        "1m",
        tmp_path,
        _wide_schedule(),
        "nse-equity-month@v1",
    )
    coordinator = _coordinator(
        faulting_observer if stage == "recovery" else _request_observer,
        session_factory=SimpleNamespace(open=unexpected_provider),
    )
    if stage == "serialization":
        monkeypatch.setattr(ingestion_module, "canonical_schedule_bytes", fail)
    elif stage == "retention":
        monkeypatch.setattr(_ScheduleStore, "retain", fail)
    lease = None
    if caller_lease:
        acquired = StorageRootLease.try_acquire(tmp_path)
        assert acquired.outcome is LeaseOutcome.ACQUIRED
        assert acquired.lease is not None
        lease = acquired.lease
    try:
        with pytest.raises(ValueError) as raised:
            if lease is None:
                coordinator.run(command)
            else:
                coordinator.run_under_lease(command, lease)
        assert raised.value is failure
        assert provider_calls == []
    finally:
        if lease is not None:
            lease.close()


def test_unsupported_interval_is_typed_rejection_before_operational_dependencies(
    tmp_path: Path,
) -> None:
    command = IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, 1, 31),
        "5m",
        tmp_path,
        _schedule(),
        "nse-equity-month@v1",
        max_total_provider_attempts=1,
    )

    report = IngestionCoordinator().run(command)

    assert report.outcome is IngestionRunOutcome.REJECTED
    assert report.failure_code is RunFailureCode.UNSUPPORTED_INTERVAL
    assert report.planned_count == 0
    assert report.provider_attempt_count == 0


def test_command_rejects_malformed_exact_boundary_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        IngestionCommand(  # type: ignore[arg-type]
            _instrument(),
            date(2026, 1, 1),
            date(2026, 1, 31),
            1,
            tmp_path,
            _schedule(),
            "nse-equity-month@v1",
        )


def test_range_report_rejects_outcome_that_contradicts_partition_results() -> None:
    plan = plan_upstox_equity_months(
        _instrument(), date(2026, 1, 1), date(2026, 1, 31), "1m"
    )[0]
    result = PartitionResult(
        plan,
        PartitionOutcome.FAILED,
        (),
        None,
        0,
        None,
        None,
        "PROVIDER_CONTRACT",
    )
    now = datetime(2026, 2, 1, tzinfo=UTC)

    with pytest.raises(ValueError):
        IngestionReport(
            IngestionRunOutcome.SUCCEEDED,
            RunFailureCode.NONE,
            (result,),
            1,
            0,
            0,
            0,
            0,
            1,
            0,
            0,
            now,
            now,
        )


def test_open_month_is_rejected_before_lease_or_provider_activity(
    tmp_path: Path,
) -> None:
    lease_calls: list[Path] = []

    def acquire(root: object) -> LeaseResult:
        assert isinstance(root, Path)
        lease_calls.append(root)
        return _lease(root)

    command = IngestionCommand(
        _instrument(),
        date(2026, 8, 1),
        date(2026, 8, 7),
        "1m",
        tmp_path,
        _schedule(),
        "nse-equity-month@v1",
        max_total_provider_attempts=1,
    )
    coordinator = IngestionCoordinator(
        clock=SimpleNamespace(now=lambda: datetime(2026, 8, 8, tzinfo=UTC)),
        lease_acquirer=acquire,
    )

    report = coordinator.run(command)

    assert report.outcome is IngestionRunOutcome.REJECTED
    assert report.failure_code is RunFailureCode.PARTITION_NOT_CLOSED
    assert [item.outcome for item in report.results] == [PartitionOutcome.NOT_ATTEMPTED]
    assert lease_calls == []


def test_incomplete_v2_schedule_is_rejected_before_lease_or_provider_activity(
    tmp_path: Path,
) -> None:
    complete = _schedule()
    incomplete = ExpectedSessionSchedule(
        complete.schema_version,
        complete.source,
        complete.source_release,
        complete.as_of,
        complete.timezone,
        complete.covered_from,
        complete.covered_to,
        complete.sessions,
        complete.closures[1:],
    )
    lease_calls: list[Path] = []

    class NeverOpen:
        def open(self) -> object:
            raise AssertionError("provider session must remain unopened")

    report = IngestionCoordinator(
        session_factory=NeverOpen(),  # type: ignore[arg-type]
        lease_acquirer=lambda root: lease_calls.append(root) or _lease(root),  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 1, 31),
            "1m",
            tmp_path,
            incomplete,
            "nse-equity-month@v1",
        )
    )

    assert report.outcome is IngestionRunOutcome.REJECTED
    assert report.failure_code is RunFailureCode.SCHEDULE_UNSUPPORTED
    assert report.not_attempted_count == 1
    assert report.provider_attempt_count == 0
    assert lease_calls == []


def test_v2_schedule_store_round_trip_and_corruption_fail_closed(
    tmp_path: Path,
) -> None:
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.outcome is LeaseOutcome.ACQUIRED
    assert lease_result.lease is not None
    lease = lease_result.lease
    store = ScheduleEvidenceStore(tmp_path, lease)
    try:
        schedule = _schedule()
        retained = store.retain(schedule)
        assert retained.outcome is ScheduleOutcome.RETAINED
        assert retained.canonical_bytes == canonical_schedule_bytes(schedule)
        assert retained.canonical_bytes is not None
        assert b'"closures"' in retained.canonical_bytes

        resolved = store.resolve(retained.digest)
        assert resolved.outcome is ScheduleOutcome.RESOLVED
        assert resolved.schedule == schedule

        assert retained.digest is not None
        object_path = (
            tmp_path / "calendar-schedules" / "sha256" / f"{retained.digest}.json"
        )
        object_path.write_bytes(b"corrupt")
        corrupt = store.resolve(retained.digest)
        assert corrupt.outcome is ScheduleOutcome.FAILED
        assert corrupt.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
    finally:
        lease.close()


def test_retained_schedule_must_prove_exact_command_provenance_before_catalog(
    tmp_path: Path,
) -> None:
    command_schedule = _schedule()
    retained = ExpectedSessionSchedule(
        command_schedule.schema_version,
        command_schedule.source,
        "different-source-release",
        command_schedule.as_of,
        command_schedule.timezone,
        command_schedule.covered_from,
        command_schedule.covered_to,
        command_schedule.sessions,
        command_schedule.closures,
    )
    catalog_calls: list[Path] = []

    class WrongScheduleStore:
        def retain(self, _: ExpectedSessionSchedule) -> ScheduleEvidenceResult:
            canonical = canonical_schedule_bytes(retained)
            digest = schedule_digest(retained)
            return ScheduleEvidenceResult(
                ScheduleOutcome.RETAINED,
                ScheduleFailureCode.NONE,
                retained,
                canonical,
                digest,
                f"calendar-schedules/sha256/{digest}.json",
            )

    class NeverOpen:
        def open(self) -> object:
            raise AssertionError("provider session must remain unopened")

    report = IngestionCoordinator(
        session_factory=NeverOpen(),  # type: ignore[arg-type]
        lease_acquirer=_lease,
        catalog_factory=lambda root: catalog_calls.append(root) or _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: WrongScheduleStore(),  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 1, 31),
            "1m",
            tmp_path,
            command_schedule,
            "nse-equity-month@v1",
        )
    )

    assert report.outcome is IngestionRunOutcome.REJECTED
    assert report.failure_code is RunFailureCode.SCHEDULE_UNSUPPORTED
    assert report.provider_attempt_count == 0
    assert catalog_calls == []


def test_all_local_reconciliation_skips_provider_session_and_attempts(
    tmp_path: Path,
) -> None:
    class _NeverOpen:
        def open(self) -> object:
            raise AssertionError("provider session must remain lazy")

    report = _coordinator(
        _skip_observer,
        session_factory=_NeverOpen(),
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 1, 31),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=0,
        )
    )

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert report.skipped_count == 1
    assert report.provider_attempt_count == 0


def test_obsolete_alias_migration_stops_the_run_before_provider_session(
    tmp_path: Path,
) -> None:
    session_opened: list[object] = []
    limiter_calls: list[str] = []
    sleeper_calls: list[object] = []
    recovery_plans: list[PlannedInstrumentMonth] = []
    lifecycle_plans: list[PlannedInstrumentMonth] = []
    failed_manifest: PartitionManifest | None = None

    class _NeverOpen:
        def open(self) -> object:
            session_opened.append(object())
            raise AssertionError("provider session must remain unopened")

    class _NeverLimit:
        def acquire(self, *_args: object) -> None:
            limiter_calls.append("acquire")
            raise AssertionError("limiter must remain unused")

        def defer_for(self, *_args: object) -> None:
            limiter_calls.append("defer_for")
            raise AssertionError("limiter must remain unused")

    def never_sleep(*args: object) -> None:
        sleeper_calls.extend(args)
        raise AssertionError("sleeper must remain unused")

    def observer_factory(**_kwargs: object) -> SimpleNamespace:
        def observe(plan: PlannedInstrumentMonth) -> PartitionRecoveryResult:
            nonlocal failed_manifest
            recovery_plans.append(plan)
            if plan.month != 1:
                raise AssertionError("fatal migration stop must prevent later recovery")
            stored_plan = PlannedInstrumentMonth(
                plan.provider,
                "NSE_EQ|OLD",
                plan.security_id,
                "OLD",
                plan.exchange,
                plan.segment,
                plan.instrument_type,
                plan.interval,
                plan.year,
                plan.month,
                plan.from_date,
                plan.to_date,
            )
            failed_manifest = fail_manifest(
                _in_progress_manifest(stored_plan, "old-run"),
                datetime(2026, 3, 1, 0, 0, 1, tzinfo=UTC),
                FailureCategory.EMPTY_RESPONSE,
                row_count=0,
            )
            return PartitionRecoveryResult(
                plan,
                PartitionRecoveryOutcome.FAILED,
                failed_manifest,
                None,
                None,
                "MAPPING_MIGRATION_REQUIRED",
                None,
            )

        return SimpleNamespace(observe=observe)

    def lifecycle_factory(**_kwargs: object) -> SimpleNamespace:
        def execute(plan: PlannedInstrumentMonth) -> object:
            lifecycle_plans.append(plan)
            raise AssertionError("lifecycle must remain unused")

        return SimpleNamespace(execute=execute)

    report = _coordinator(
        observer_factory,
        session_factory=_NeverOpen(),
        lifecycle_factory=lifecycle_factory,
        limiter=_NeverLimit(),
        sleeper=never_sleep,
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 2, 28),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=2,
        )
    )

    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is RunFailureCode.MAPPING_MIGRATION_REQUIRED
    assert report.planned_count == 2
    assert report.skipped_count == 0
    assert report.locally_recovered_count == 0
    assert report.provider_attempt_count == 0
    assert report.verified_count == 0
    assert report.failed_count == 1
    assert report.not_attempted_count == 1
    assert report.cancelled_count == 0
    assert session_opened == []
    assert limiter_calls == []
    assert sleeper_calls == []
    assert [plan.month for plan in recovery_plans] == [1]
    assert lifecycle_plans == []
    assert failed_manifest is not None
    assert failed_manifest.plan.instrument_key == "NSE_EQ|OLD"
    assert failed_manifest.state is ManifestState.FAILED
    assert failed_manifest.failure_category is FailureCategory.EMPTY_RESPONSE
    assert len(report.results) == 2

    failed, not_attempted = report.results
    assert failed.plan == recovery_plans[0]
    assert failed.outcome is PartitionOutcome.FAILED
    assert failed.reconciliation_reasons == (RequestReason.MISSING_EVIDENCE,)
    assert failed.ingestion_run_id == "old-run"
    assert failed.provider_attempts == 0
    assert failed.final_manifest is failed_manifest
    assert failed.failure_category is None
    assert failed.error_code == "MAPPING_MIGRATION_REQUIRED"

    assert not_attempted.plan.year == 2026
    assert not_attempted.plan.month == 2
    assert not_attempted.outcome is PartitionOutcome.NOT_ATTEMPTED
    assert not_attempted.reconciliation_reasons == ()
    assert not_attempted.ingestion_run_id is None
    assert not_attempted.provider_attempts == 0
    assert not_attempted.final_manifest is None
    assert not_attempted.failure_category is None
    assert not_attempted.error_code is None
    assert "MAPPING_MIGRATION_REQUIRED" in repr(report)
    assert "provider session must remain unopened" not in repr(report)


def test_complete_local_reconciliation_precedes_one_lazy_sequential_session(
    tmp_path: Path,
) -> None:
    class _SessionFactory:
        def __init__(self) -> None:
            self.open_count = 0

        def open(self) -> object:
            self.open_count += 1
            return SimpleNamespace(fetch=lambda _request: None)

    session_factory = _SessionFactory()
    observed: list[date] = []
    executed: list[date] = []

    def observer_factory(**_kwargs: object) -> SimpleNamespace:
        def observe(plan: object) -> SimpleNamespace:
            observed.append(plan.from_date)  # type: ignore[union-attr]
            return SimpleNamespace(
                plan=plan,
                outcome=PartitionRecoveryOutcome.REQUEST_REQUIRED,
                final_manifest=None,
                evidence=None,
                failure_category=None,
                error_code=None,
            )

        return SimpleNamespace(observe=observe)

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            executed.append(plan.from_date)  # type: ignore[union-attr]
            return _lifecycle_result(
                plan,
                PartitionLifecycleOutcome.VERIFIED,
                kwargs["run_id"],  # type: ignore[arg-type]
            )

        return SimpleNamespace(execute=execute)

    report = IngestionCoordinator(
        session_factory=session_factory,  # type: ignore[arg-type]
        lease_acquirer=_lease,
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
        recovery_observer_factory=observer_factory,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 15),
            date(2026, 2, 10),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=2,
        )
    )

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.planned_count == 2
    assert report.verified_count == 2
    assert session_factory.open_count == 1
    assert observed == [date(2026, 1, 1), date(2026, 2, 1)]
    assert executed == observed


def test_shared_gate_keeps_provider_fetch_outside_serial_catalog_phase(
    tmp_path: Path,
) -> None:
    class Gate:
        def __init__(self) -> None:
            self._lock = threading.RLock()
            self.depth = 0

        def __enter__(self) -> Gate:
            self._lock.acquire()
            self.depth += 1
            return self

        def __exit__(self, *_args: object) -> None:
            self.depth -= 1
            self._lock.release()

    gate = Gate()
    fetches: list[date] = []
    publications: list[date] = []

    def provider_fetch(request: object) -> HistoricalResponse:
        assert gate.depth == 0
        fetches.append(request.from_date)  # type: ignore[attr-defined]
        return HistoricalResponse(200, [])

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: PlannedInstrumentMonth) -> PartitionLifecycleResult:
            assert gate.depth == 1
            fetched = kwargs["fetcher"].fetch(plan)  # type: ignore[union-attr]
            assert fetched.response is not None
            publications.append(plan.from_date)
            return _lifecycle_result(
                plan,
                PartitionLifecycleOutcome.VERIFIED,
                kwargs["run_id"],  # type: ignore[arg-type]
                attempts=fetched.attempts,
            )

        return SimpleNamespace(execute=execute)

    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with lease_result.lease as lease:
        report = IngestionCoordinator(
            session_factory=SimpleNamespace(
                open=lambda: SimpleNamespace(fetch=provider_fetch)
            ),  # type: ignore[arg-type]
            lease_acquirer=_lease,
            catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
            schedule_store_factory=lambda _root, _lease: _ScheduleStore(_schedule()),  # type: ignore[arg-type]
            recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
            lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
            publication_gate=gate,
        ).run_under_lease(
            IngestionCommand(
                _instrument(),
                date(2026, 1, 1),
                date(2026, 1, 31),
                "1m",
                tmp_path,
                _schedule(),
                "nse-equity-month@v1",
                max_total_provider_attempts=1,
            ),
            lease,
        )

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert fetches == [date(2026, 1, 1)]
    assert publications == fetches


def test_attempt_budget_insufficient_is_zero_session_after_local_reconciliation(
    tmp_path: Path,
) -> None:
    class _NeverOpen:
        def open(self) -> object:
            raise AssertionError("provider session must remain lazy")

    report = _coordinator(
        _request_observer,
        session_factory=_NeverOpen(),
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 2, 28),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=1,
        )
    )

    assert report.outcome is IngestionRunOutcome.REJECTED
    assert report.failure_code is RunFailureCode.ATTEMPT_BUDGET_INSUFFICIENT
    assert report.not_attempted_count == 2
    assert report.provider_attempt_count == 0


def test_prefetched_replay_enforces_exact_plan_and_attempt_budget() -> None:
    plan = plan_upstox_equity_months(
        _instrument(), date(2026, 1, 1), date(2026, 1, 31), "1m"
    )[0]
    missing = ingestion_module._PrefetchedRangeFetcher({}, 1).fetch(plan)
    assert missing.failure is not None
    assert missing.failure.code is HistoricalFetchCode.ATTEMPT_BUDGET_EXHAUSTED

    over_budget = HistoricalFetchResult(
        HistoricalResponse(200, []), 2, retrieved_at=datetime(2026, 1, 2, tzinfo=UTC)
    )
    replay = ingestion_module._PrefetchedRangeFetcher({plan: over_budget}, 1).fetch(
        plan
    )
    assert replay.failure is not None
    assert replay.failure.code is HistoricalFetchCode.ATTEMPT_BUDGET_EXHAUSTED

    with pytest.raises(RuntimeError):
        _coordinator(_request_observer)._run_concurrent_under_lease(
            object(),
            (),
            object(),
            object(),
            datetime(2026, 1, 1, tzinfo=UTC),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("error_type", "expected_code"),
    (
        (ProviderSessionAuthenticationError, RunFailureCode.AUTHENTICATION_FAILED),
        (ProviderSessionAuthorizationError, RunFailureCode.AUTHORIZATION_FAILED),
    ),
)
def test_session_open_errors_are_typed_sanitized_and_stop_later_plans(
    tmp_path: Path,
    error_type: type[RuntimeError],
    expected_code: RunFailureCode,
) -> None:
    class FailingSessionFactory:
        def __init__(self) -> None:
            self.calls = 0

        def open(self) -> object:
            self.calls += 1
            raise error_type("provider account secret")

    session_factory = FailingSessionFactory()
    report = _coordinator(
        _request_observer,
        session_factory=session_factory,
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 2, 28),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=2,
        )
    )

    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is expected_code
    assert session_factory.calls == 1
    assert report.not_attempted_count == 2
    assert report.provider_attempt_count == 0
    assert "secret" not in report.failure_code.value


@pytest.mark.parametrize("shared_gate", (False, True))
def test_default_unavailable_session_preserves_authentication_failure(
    tmp_path: Path, shared_gate: bool
) -> None:
    coordinator = IngestionCoordinator(
        session_factory=None,
        lease_acquirer=_lease,
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(  # type: ignore[arg-type]
            _wide_schedule()
        ),
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        publication_gate=threading.RLock() if shared_gate else None,
    )
    command = IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, 2, 28),
        "1m",
        tmp_path,
        _wide_schedule(),
        "nse-equity-month@v1",
        max_total_provider_attempts=2,
    )
    if shared_gate:
        lease_result = StorageRootLease.try_acquire(tmp_path)
        assert lease_result.lease is not None
        with lease_result.lease as lease:
            report = coordinator.run_under_lease(command, lease)
    else:
        report = coordinator.run(command)

    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is RunFailureCode.AUTHENTICATION_FAILED
    assert report.provider_attempt_count == 0
    assert tuple(result.outcome for result in report.results) == (
        PartitionOutcome.NOT_ATTEMPTED,
        PartitionOutcome.NOT_ATTEMPTED,
    )


@pytest.mark.parametrize("stage", ("open", "request_executor"))
def test_unknown_provider_setup_faults_escape_before_fetch(
    tmp_path: Path, stage: str
) -> None:
    failure = RuntimeError("private-provider-implementation-fault")
    session_calls: list[object] = []
    fetches: list[object] = []

    def open_session() -> object:
        session_calls.append(object())
        if stage == "open":
            raise failure
        return SimpleNamespace(
            fetch=lambda request: fetches.append(request) or HistoricalResponse(500, [])
        )

    def run_id() -> str:
        if stage == "request_executor":
            raise failure
        return "run"

    coordinator = IngestionCoordinator(
        session_factory=SimpleNamespace(open=open_session),  # type: ignore[arg-type]
        run_id_factory=run_id,
        lease_acquirer=_lease,
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
    )
    command = IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, 2, 28),
        "1m",
        tmp_path,
        _wide_schedule(),
        "nse-equity-month@v1",
        max_total_provider_attempts=2,
    )

    with pytest.raises(RuntimeError) as raised:
        coordinator.run(command)

    assert raised.value is failure
    assert len(session_calls) == 1
    assert fetches == []


def test_invalid_validation_policy_rejects_before_lease_or_other_side_effects(
    tmp_path: Path,
) -> None:
    lease_calls: list[Path] = []
    schedule_calls: list[object] = []
    catalog_calls: list[object] = []
    session_calls: list[object] = []

    def catalog_factory(root: object) -> None:
        catalog_calls.append(root)

    report = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: (
                session_calls.append(object())
                or SimpleNamespace(fetch=lambda _request: None)
            )
        ),  # type: ignore[arg-type]
        lease_acquirer=lambda root: lease_calls.append(root) or _lease(root),  # type: ignore[arg-type]
        schedule_store_factory=lambda *_args: schedule_calls.append(object()),  # type: ignore[arg-type]
        catalog_factory=catalog_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 1, 31),
            "1m",
            tmp_path,
            _wide_schedule(),
            "not-a-validation-policy",
        )
    )

    assert report.outcome is IngestionRunOutcome.REJECTED
    assert report.failure_code is RunFailureCode.SCHEDULE_UNSUPPORTED
    assert lease_calls == []
    assert schedule_calls == []
    assert catalog_calls == []
    assert session_calls == []


def test_run_fatal_stops_later_requestable_plans_with_not_attempted_results(
    tmp_path: Path,
) -> None:
    executed: list[date] = []

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            executed.append(plan.from_date)  # type: ignore[union-attr]
            return _lifecycle_result(
                plan,
                PartitionLifecycleOutcome.FAILED,
                kwargs["run_id"],  # type: ignore[arg-type]
                attempts=0,
                error_code="AUTHENTICATION_FAILED",
            )

        return SimpleNamespace(execute=execute)

    report = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(fetch=lambda _request: None)
        ),  # type: ignore[arg-type]
        lease_acquirer=_lease,
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 2, 28),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=2,
        )
    )

    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is RunFailureCode.AUTHENTICATION_FAILED
    assert executed == [date(2026, 1, 1)]
    assert report.results[1].outcome is PartitionOutcome.NOT_ATTEMPTED


@pytest.mark.parametrize(
    ("status", "category", "expected_code"),
    [
        (
            401,
            ProviderErrorCategory.AUTHENTICATION,
            RunFailureCode.AUTHENTICATION_FAILED,
        ),
        (403, ProviderErrorCategory.AUTHORIZATION, RunFailureCode.AUTHORIZATION_FAILED),
    ],
)
def test_real_http_auth_statuses_propagate_as_distinct_run_fatals(
    tmp_path: Path,
    status: int,
    category: ProviderErrorCategory,
    expected_code: RunFailureCode,
) -> None:
    session_calls: list[object] = []

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            fetched = kwargs["fetcher"].fetch(plan)  # type: ignore[union-attr]
            assert fetched.failure is not None
            return _lifecycle_result(
                plan,
                PartitionLifecycleOutcome.FAILED,
                kwargs["run_id"],  # type: ignore[arg-type]
                attempts=fetched.attempts,
                error_code=fetched.failure.code.value,
            )

        return SimpleNamespace(execute=execute)

    report = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(
                fetch=lambda _request: (
                    session_calls.append(object())
                    or HistoricalResponse(status, [], error_category=category)
                )
            )
        ),  # type: ignore[arg-type]
        run_id_factory=lambda: "current-run",
        lease_acquirer=_lease,  # type: ignore[arg-type]
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 2, 28),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=2,
        )
    )

    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is expected_code
    assert report.provider_attempt_count == 1
    assert report.not_attempted_count == 1
    assert len(session_calls) == 1


def test_provider_attempt_budget_carries_across_partitions(tmp_path: Path) -> None:
    responses = [
        HistoricalResponse(500, []),
        HistoricalResponse(200, []),
        HistoricalResponse(500, []),
    ]
    requests: list[object] = []
    waits: list[timedelta] = []

    class Sleeper:
        def sleep(self, delay: timedelta, _cancellation: object) -> None:
            waits.append(delay)

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            fetched = kwargs["fetcher"].fetch(plan)  # type: ignore[union-attr]
            return _lifecycle_result(
                plan,
                (
                    PartitionLifecycleOutcome.VERIFIED
                    if fetched.failure is None
                    else PartitionLifecycleOutcome.FAILED
                ),
                kwargs["run_id"],  # type: ignore[arg-type]
                attempts=fetched.attempts,
                error_code=None
                if fetched.failure is None
                else fetched.failure.code.value,
            )

        return SimpleNamespace(execute=execute)

    report = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(
                fetch=lambda _request: requests.append(_request) or responses.pop(0)
            )
        ),  # type: ignore[arg-type]
        sleeper=Sleeper(),  # type: ignore[arg-type]
        jitter=SimpleNamespace(uniform=lambda _lower, _upper: 0.0),  # type: ignore[arg-type]
        run_id_factory=lambda: "current-run",
        lease_acquirer=_lease,  # type: ignore[arg-type]
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 2, 28),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            retry_policy=RetryPolicy(
                max_attempts_per_partition=2,
                base_backoff=timedelta(seconds=1),
                max_backoff=timedelta(seconds=1),
                max_total_wait=timedelta(milliseconds=750),
            ),
            max_total_provider_attempts=4,
        )
    )

    assert report.outcome is IngestionRunOutcome.PARTIAL
    assert report.failure_code is RunFailureCode.RETRY_WAIT_BOUND_EXCEEDED
    assert report.provider_attempt_count == 3
    assert report.verified_count == 1
    assert report.failed_count == 1
    assert len(requests) == 3
    assert waits == [timedelta(milliseconds=500)]


def test_child_h_catalog_failure_stops_later_lifecycle_work(
    tmp_path: Path,
) -> None:
    executed: list[date] = []
    schedule = _three_month_schedule()

    def lifecycle_factory(**_kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            executed.append(plan.from_date)  # type: ignore[union-attr]
            if plan.from_date == date(2026, 2, 1):  # type: ignore[union-attr]
                raise PartitionCatalogFailure("catalog secret")
            return _lifecycle_result(
                plan,
                PartitionLifecycleOutcome.VERIFIED,
                _kwargs["run_id"],  # type: ignore[arg-type]
            )

        return SimpleNamespace(execute=execute)

    report = _range_with_lifecycle(
        tmp_path, schedule, CancellationToken(), lifecycle_factory
    )

    assert report.outcome is IngestionRunOutcome.PARTIAL
    assert report.failure_code is RunFailureCode.CATALOG_UNAVAILABLE
    assert executed == [date(2026, 1, 1), date(2026, 2, 1)]
    assert report.verified_count == 1
    assert report.failed_count == 1
    assert report.not_attempted_count == 1
    assert report.results[1].error_code == "CATALOG_UNAVAILABLE"


def test_real_lifecycle_catalog_defect_escapes_before_later_fetch(
    tmp_path: Path,
) -> None:
    failure = AssertionError("private-catalog-implementation-fault")
    created: list[date] = []
    fetches: list[object] = []

    class Catalog(_Catalog):
        def get_manifest(self, _plan: object) -> None:
            return None

        def create_manifest(self, manifest: PartitionManifest) -> None:
            created.append(manifest.plan.from_date)
            if manifest.plan.from_date == date(2026, 1, 1):
                raise failure

    catalog = Catalog()
    coordinator = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(
                fetch=lambda request: (
                    fetches.append(request) or HistoricalResponse(500, [])
                )
            )
        ),  # type: ignore[arg-type]
        lease_acquirer=_lease,
        catalog_factory=lambda _root: catalog,  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
    )
    command = IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, 2, 28),
        "1m",
        tmp_path,
        _wide_schedule(),
        "nse-equity-month@v1",
        max_total_provider_attempts=2,
    )

    with pytest.raises(AssertionError) as raised:
        coordinator.run(command)

    assert raised.value is failure
    assert created == [date(2026, 1, 1)]
    assert fetches == []


def test_default_lifecycle_clock_fault_escapes_before_later_range_work(
    tmp_path: Path,
) -> None:
    failure = RuntimeError("clock implementation fault")
    catalog_lookups: list[date] = []
    provider_fetches: list[object] = []

    class FaultingClock:
        def __init__(self) -> None:
            self.calls = 0

        def now(self) -> datetime:
            self.calls += 1
            if self.calls >= 3:
                raise failure
            return datetime(2026, 3, 1, tzinfo=UTC)

    class Catalog(_Catalog):
        def get_manifest(self, plan: PlannedInstrumentMonth) -> None:
            catalog_lookups.append(plan.from_date)
            return None

    coordinator = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(fetch=provider_fetches.append)
        ),  # type: ignore[arg-type]
        clock=FaultingClock(),
        lease_acquirer=_lease,
        catalog_factory=lambda _root: Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
    )
    command = IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, 2, 28),
        "1m",
        tmp_path,
        _wide_schedule(),
        "nse-equity-month@v1",
        max_total_provider_attempts=2,
    )

    with pytest.raises(RuntimeError) as raised:
        coordinator.run(command)

    assert raised.value is failure
    assert catalog_lookups == [date(2026, 1, 1)]
    assert provider_fetches == []


@pytest.mark.parametrize("stage", ("session", "schedule", "publisher"))
def test_real_lifecycle_unknown_fault_escapes_before_later_month_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    failure = AssertionError(f"private-{stage}-implementation-fault")
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
    schedule = ExpectedSessionSchedule(
        2,
        "nse",
        "2026-Q1",
        datetime(2026, 3, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 1, 1),
        date(2026, 2, 28),
        sessions,
        _closures(date(2026, 1, 1), date(2026, 2, 28), sessions),
    )
    requests: list[date] = []

    def fetch(request: object) -> HistoricalResponse:
        requests.append(request.from_date)  # type: ignore[union-attr]
        if stage == "session":
            raise failure
        if request.from_date != date(2026, 1, 1):  # type: ignore[union-attr]
            raise AssertionError("later month request must not occur")
        return HistoricalResponse(
            200,
            [["2026-01-02T03:45:00+00:00", 1, 1, 1, 1, 1, None]],
        )

    if stage == "schedule":
        monkeypatch.setattr(
            validation_module,
            "canonical_schedule_bytes",
            lambda _schedule: (_ for _ in ()).throw(failure),
        )
    elif stage == "publisher":
        monkeypatch.setattr(
            publication_module,
            "iter_candles_from_parquet",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
        )

    command = IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, 2, 28),
        "1m",
        tmp_path,
        schedule,
        "nse-equity-month@v1",
        max_total_provider_attempts=2,
    )

    def catalog_factory(root: Path) -> DuckDBCatalog:
        return DuckDBCatalog(root)

    coordinator = IngestionCoordinator(
        session_factory=SimpleNamespace(open=lambda: SimpleNamespace(fetch=fetch)),  # type: ignore[arg-type]
        lease_acquirer=_lease,
        catalog_factory=catalog_factory,
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(schedule),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
    )

    with pytest.raises(AssertionError) as raised:
        coordinator.run(command)

    assert raised.value is failure
    assert requests == [date(2026, 1, 1)]
    assert list(tmp_path.rglob("bars.parquet")) == []
    plans = plan_upstox_equity_months(
        _instrument(), date(2026, 1, 1), date(2026, 2, 28), "1m"
    )
    with DuckDBCatalog(tmp_path) as catalog:
        first = catalog.get_manifest(plans[0])
        assert first is not None
        assert first.state is ManifestState.IN_PROGRESS
        assert catalog.get_manifest(plans[1]) is None


def test_first_local_fatal_stops_observation_and_marks_later_plans_not_attempted(
    tmp_path: Path,
) -> None:
    observed: list[date] = []

    def observer_factory(**_kwargs: object) -> SimpleNamespace:
        def observe(plan: object) -> SimpleNamespace:
            observed.append(plan.from_date)  # type: ignore[union-attr]
            return SimpleNamespace(
                plan=plan,
                outcome=PartitionRecoveryOutcome.FAILED,
                final_manifest=None,
                evidence=None,
                failure_category=None,
                error_code="CATALOG_UNAVAILABLE",
            )

        return SimpleNamespace(observe=observe)

    report = _coordinator(observer_factory).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 2, 28),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=2,
        )
    )

    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is RunFailureCode.CATALOG_UNAVAILABLE
    assert observed == [date(2026, 1, 1)]
    assert report.failed_count == 1
    assert report.not_attempted_count == 1
    assert report.provider_attempt_count == 0


def test_cancellation_before_any_terminal_result_makes_no_lease_or_provider_calls(
    tmp_path: Path,
) -> None:
    cancellation = CancellationToken()
    cancellation.cancel()
    lease_calls: list[Path] = []

    report = IngestionCoordinator(
        cancellation=cancellation,
        lease_acquirer=lambda root: lease_calls.append(root) or _lease(root),  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 2, 28),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=2,
        )
    )

    assert report.outcome is IngestionRunOutcome.CANCELLED
    assert report.failure_code is RunFailureCode.CANCELLED
    assert report.cancelled_count == 2
    assert lease_calls == []


def test_lease_contention_is_typed_refusal_with_no_other_work(tmp_path: Path) -> None:
    coordinator = IngestionCoordinator(
        lease_acquirer=lambda _root: LeaseResult(
            LeaseOutcome.ALREADY_RUNNING,
            LeaseFailureCode.ALREADY_RUNNING,
            None,
        )
    )

    report = coordinator.run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 1, 31),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
        )
    )

    assert report.outcome is IngestionRunOutcome.ALREADY_RUNNING
    assert report.failure_code is RunFailureCode.ALREADY_RUNNING
    assert report.not_attempted_count == 1


@pytest.mark.parametrize("raises", [False, True])
def test_hostile_lease_port_rejects_before_schedule_catalog_or_provider(
    tmp_path: Path, raises: bool
) -> None:
    schedule_calls: list[object] = []
    catalog_calls: list[object] = []
    provider_calls: list[object] = []

    def acquire(_root: object) -> object:
        if raises:
            raise StorageRootLeaseError("storage authority unavailable")
        return SimpleNamespace(outcome=LeaseOutcome.ACQUIRED, lease=_Lease())

    report = IngestionCoordinator(
        session_factory=SimpleNamespace(open=lambda: provider_calls.append(object())),  # type: ignore[arg-type]
        lease_acquirer=acquire,  # type: ignore[arg-type]
        schedule_store_factory=lambda *_args: schedule_calls.append(object()),  # type: ignore[arg-type]
        catalog_factory=lambda _root: catalog_calls.append(object()),  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 1, 31),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
        )
    )

    assert report.outcome is IngestionRunOutcome.REJECTED
    assert report.failure_code is RunFailureCode.STORAGE_UNSAFE
    assert report.not_attempted_count == 1
    assert schedule_calls == []
    assert catalog_calls == []
    assert provider_calls == []


def test_unknown_lease_acquisition_fault_escapes_before_dependencies(
    tmp_path: Path,
) -> None:
    failure = RuntimeError("private-lease-implementation-fault")
    schedule_calls: list[object] = []
    catalog_calls: list[object] = []
    provider_calls: list[object] = []
    coordinator = IngestionCoordinator(
        session_factory=SimpleNamespace(open=lambda: provider_calls.append(object())),  # type: ignore[arg-type]
        lease_acquirer=lambda _root: (_ for _ in ()).throw(failure),  # type: ignore[arg-type]
        schedule_store_factory=lambda *_args: schedule_calls.append(object()),  # type: ignore[arg-type]
        catalog_factory=lambda _root: catalog_calls.append(object()),  # type: ignore[arg-type]
    )
    command = IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, 1, 31),
        "1m",
        tmp_path,
        _wide_schedule(),
        "nse-equity-month@v1",
    )

    with pytest.raises(RuntimeError) as raised:
        coordinator.run(command)

    assert raised.value is failure
    assert schedule_calls == []
    assert catalog_calls == []
    assert provider_calls == []


@pytest.mark.parametrize("raises", [False, True])
def test_hostile_schedule_port_rejects_before_catalog_or_provider(
    tmp_path: Path, raises: bool
) -> None:
    catalog_calls: list[object] = []
    provider_calls: list[object] = []

    def schedule_store_factory(*_args: object) -> object:
        if raises:
            raise RuntimeError("schedule secret")
        return SimpleNamespace()

    with pytest.raises(RuntimeError if raises else AttributeError):
        IngestionCoordinator(
            session_factory=SimpleNamespace(
                open=lambda: provider_calls.append(object())
            ),  # type: ignore[arg-type]
            lease_acquirer=_lease,  # type: ignore[arg-type]
            schedule_store_factory=schedule_store_factory,  # type: ignore[arg-type]
            catalog_factory=lambda _root: catalog_calls.append(object()),  # type: ignore[arg-type]
        ).run(
            IngestionCommand(
                _instrument(),
                date(2026, 1, 1),
                date(2026, 1, 31),
                "1m",
                tmp_path,
                _wide_schedule(),
                "nse-equity-month@v1",
            )
        )
    assert catalog_calls == []
    assert provider_calls == []


def test_ordinary_partition_failure_isolated_and_reported_partial(
    tmp_path: Path,
) -> None:
    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            is_first = plan.from_date == date(2026, 1, 1)  # type: ignore[union-attr]
            return _lifecycle_result(
                plan,
                (
                    PartitionLifecycleOutcome.FAILED
                    if is_first
                    else PartitionLifecycleOutcome.VERIFIED
                ),
                kwargs["run_id"],  # type: ignore[arg-type]
                error_code="PROVIDER_CLIENT" if is_first else None,
            )

        return SimpleNamespace(execute=execute)

    report = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(fetch=lambda _request: None)
        ),  # type: ignore[arg-type]
        lease_acquirer=_lease,
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 2, 28),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=2,
        )
    )

    assert report.outcome is IngestionRunOutcome.PARTIAL
    assert report.failure_code is RunFailureCode.PARTITION_FAILURE
    assert report.failed_count == 1
    assert report.verified_count == 1
    assert report.provider_attempt_count == 2


def test_schedule_failure_and_catalog_failure_are_zero_provider_paths(
    tmp_path: Path,
) -> None:
    class _FailedSchedule:
        def retain(self, _schedule: ExpectedSessionSchedule) -> SimpleNamespace:
            return SimpleNamespace(outcome=ScheduleOutcome.FAILED)

    command = IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, 1, 31),
        "1m",
        tmp_path,
        _wide_schedule(),
        "nse-equity-month@v1",
    )
    schedule_report = IngestionCoordinator(
        lease_acquirer=_lease,
        schedule_store_factory=lambda _root, _lease: _FailedSchedule(),  # type: ignore[arg-type]
    ).run(command)
    catalog_report = IngestionCoordinator(
        lease_acquirer=_lease,
        catalog_factory=lambda _root: (_ for _ in ()).throw(CatalogPersistenceError()),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
    ).run(command)

    assert schedule_report.failure_code is RunFailureCode.SCHEDULE_UNSUPPORTED
    assert schedule_report.provider_attempt_count == 0
    assert catalog_report.outcome is IngestionRunOutcome.FAILED
    assert catalog_report.failure_code is RunFailureCode.CATALOG_UNAVAILABLE
    assert catalog_report.provider_attempt_count == 0


def test_cancellation_between_requestable_partitions_marks_remaining_cancelled(
    tmp_path: Path,
) -> None:
    cancellation = CancellationToken()

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            cancellation.cancel()
            return _lifecycle_result(
                plan,
                PartitionLifecycleOutcome.VERIFIED,
                kwargs["run_id"],  # type: ignore[arg-type]
            )

        return SimpleNamespace(execute=execute)

    report = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(fetch=lambda _request: None)
        ),  # type: ignore[arg-type]
        cancellation=cancellation,
        lease_acquirer=_lease,
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 2, 28),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=2,
        )
    )

    assert report.outcome is IngestionRunOutcome.PARTIAL
    assert report.failure_code is RunFailureCode.CANCELLED
    assert report.verified_count == 1
    assert report.cancelled_count == 1
    assert report.results[1].outcome is PartitionOutcome.CANCELLED


def test_pre_in_progress_recovery_cancellation_marks_every_plan_cancelled(
    tmp_path: Path,
) -> None:
    observed: list[date] = []
    schedule = _three_month_schedule()

    def observer_factory(**_kwargs: object) -> SimpleNamespace:
        def observe(plan: object) -> SimpleNamespace:
            observed.append(plan.from_date)  # type: ignore[union-attr]
            return SimpleNamespace(
                plan=plan,
                outcome=PartitionRecoveryOutcome.FAILED,
                final_manifest=None,
                evidence=None,
                failure_category=None,
                error_code="CANCELLED",
            )

        return SimpleNamespace(observe=observe)

    report = _coordinator(observer_factory, schedule=schedule).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 3, 31),
            "1m",
            tmp_path,
            schedule,
            "nse-equity-month@v1",
            max_total_provider_attempts=3,
        )
    )

    assert observed == [date(2026, 1, 1)]
    assert report.outcome is IngestionRunOutcome.CANCELLED
    assert report.failure_code is RunFailureCode.CANCELLED
    assert report.cancelled_count == 3
    assert report.not_attempted_count == 0


@pytest.mark.parametrize(
    "historical_state", [ManifestState.FAILED, ManifestState.VERIFIED]
)
def test_recovery_cancellation_never_retains_a_historical_manifest(
    tmp_path: Path, historical_state: ManifestState
) -> None:
    schedule = _three_month_schedule()

    def observer_factory(**_kwargs: object) -> SimpleNamespace:
        def observe(plan: object) -> SimpleNamespace:
            active = _in_progress_manifest(plan, "old-run")
            historical = (
                fail_manifest(
                    active,
                    active.updated_at + timedelta(microseconds=1),
                    FailureCategory.VALIDATION_FAILED,
                )
                if historical_state is ManifestState.FAILED
                else verify_manifest(
                    active,
                    active.updated_at + timedelta(microseconds=1),
                    datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
                    datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
                    1,
                    "a" * 64,
                    "canonical.parquet",
                )
            )
            return SimpleNamespace(
                plan=plan,
                outcome=PartitionRecoveryOutcome.FAILED,
                final_manifest=historical,
                evidence=None,
                failure_category=None,
                error_code="CANCELLED",
            )

        return SimpleNamespace(observe=observe)

    report = _coordinator(observer_factory, schedule=schedule).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 3, 31),
            "1m",
            tmp_path,
            schedule,
            "nse-equity-month@v1",
            max_total_provider_attempts=3,
        )
    )

    assert report.outcome is IngestionRunOutcome.CANCELLED
    assert report.cancelled_count == 3
    assert all(result.final_manifest is None for result in report.results)
    assert all(result.ingestion_run_id is None for result in report.results)


def test_lifecycle_cancellation_requires_the_current_invocation_run_id(
    tmp_path: Path,
) -> None:
    schedule = _three_month_schedule()

    def lifecycle_factory(**_kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            return _lifecycle_result(
                plan, PartitionLifecycleOutcome.CANCELLED, "old-run", attempts=0
            )

        return SimpleNamespace(execute=execute)

    report = _range_with_lifecycle(
        tmp_path,
        schedule,
        CancellationToken(),
        lifecycle_factory,
        run_id_factory=lambda: "current-run",
    )

    assert report.outcome is IngestionRunOutcome.CANCELLED
    assert report.cancelled_count == 3
    assert report.not_attempted_count == 0
    assert all(result.final_manifest is None for result in report.results)


def test_same_run_pre_in_progress_cancellation_marks_every_plan_cancelled(
    tmp_path: Path,
) -> None:
    schedule = _three_month_schedule()

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> PartitionLifecycleResult:
            return _lifecycle_result(
                plan,  # type: ignore[arg-type]
                PartitionLifecycleOutcome.CANCELLED,
                kwargs["run_id"],  # type: ignore[arg-type]
                attempts=0,
            )

        return SimpleNamespace(execute=execute)

    report = _range_with_lifecycle(
        tmp_path,
        schedule,
        CancellationToken(),
        lifecycle_factory,
        run_id_factory=lambda: "current-run",
    )

    assert report.outcome is IngestionRunOutcome.CANCELLED
    assert report.cancelled_count == 3
    assert report.not_attempted_count == 0


def test_duck_typed_lifecycle_result_is_a_sanitized_partition_failure(
    tmp_path: Path,
) -> None:
    def lifecycle_factory(**_kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            return SimpleNamespace(
                plan=plan,
                outcome=PartitionLifecycleOutcome.VERIFIED,
                ingestion_run_id="run",
                provider_attempts=1,
                final_manifest=None,
                failure_category=None,
                error_code=None,
            )

        return SimpleNamespace(execute=execute)

    report = _range_with_lifecycle(
        tmp_path,
        _three_month_schedule(),
        CancellationToken(),
        lifecycle_factory,
        run_id_factory=lambda: "run",
    )

    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is RunFailureCode.PARTITION_FAILURE
    assert report.failed_count == 1
    assert report.results[0].error_code == "PARTITION_FAILURE"
    assert report.not_attempted_count == 2


def test_acquired_lease_with_fake_authority_rejects_before_dependencies(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    report = IngestionCoordinator(
        lease_acquirer=lambda _root: LeaseResult(
            LeaseOutcome.ACQUIRED,
            LeaseFailureCode.NONE,
            _Lease(),  # type: ignore[arg-type]
        ),
        schedule_store_factory=lambda *_args: calls.append("schedule"),  # type: ignore[arg-type]
        catalog_factory=lambda _root: calls.append("catalog"),  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 1, 31),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
        )
    )

    assert report.outcome is IngestionRunOutcome.REJECTED
    assert report.failure_code is RunFailureCode.STORAGE_UNSAFE
    assert report.not_attempted_count == 1
    assert calls == []


@pytest.mark.parametrize(
    ("evidence", "expected_manifest", "expected_category"),
    [
        ("terminal_failed", True, FailureCategory.NORMALIZATION_FAILED),
        ("in_progress", True, None),
        ("verified", True, None),
        ("historical_failed", False, None),
        ("unreadable", False, None),
    ],
)
def test_post_attempt_exception_category_evidence_matrix(
    tmp_path: Path,
    evidence: str,
    expected_manifest: bool,
    expected_category: FailureCategory | None,
) -> None:
    schedule = _three_month_schedule()

    class Catalog(_Catalog):
        manifest: PartitionManifest | None = None
        unreadable = False

        def get_manifest(self, _plan: object) -> PartitionManifest | None:
            if self.unreadable:
                raise CatalogPersistenceError("catalog unavailable")
            return self.manifest

    catalog = Catalog()

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            run_id = kwargs["run_id"]
            assert type(run_id) is str
            active = _in_progress_manifest(plan, run_id)
            if evidence == "terminal_failed":
                catalog.manifest = fail_manifest(
                    active,
                    active.updated_at + timedelta(microseconds=1),
                    FailureCategory.NORMALIZATION_FAILED,
                )
            elif evidence == "in_progress":
                catalog.manifest = active
            elif evidence == "verified":
                catalog.manifest = verify_manifest(
                    active,
                    active.updated_at + timedelta(microseconds=1),
                    datetime(plan.year, plan.month, 2, 3, 45, tzinfo=UTC),  # type: ignore[union-attr]
                    datetime(plan.year, plan.month, 2, 3, 45, tzinfo=UTC),  # type: ignore[union-attr]
                    1,
                    "a" * 64,
                    "canonical.parquet",
                )
            elif evidence == "historical_failed":
                old = _in_progress_manifest(plan, "old-run")
                catalog.manifest = fail_manifest(
                    old,
                    old.updated_at + timedelta(microseconds=1),
                    FailureCategory.NORMALIZATION_FAILED,
                )
            else:
                catalog.unreadable = True
            kwargs["fetcher"]._remaining_attempts -= 1  # type: ignore[union-attr,reportPrivateUsage]
            raise PartitionClockFailure("clock unavailable")

        return SimpleNamespace(execute=execute)

    report = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(fetch=lambda _request: None)
        ),  # type: ignore[arg-type]
        run_id_factory=lambda: "current-run",
        lease_acquirer=_lease,  # type: ignore[arg-type]
        catalog_factory=lambda _root: catalog,  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(schedule),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 3, 31),
            "1m",
            tmp_path,
            schedule,
            "nse-equity-month@v1",
            max_total_provider_attempts=3,
        )
    )

    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is RunFailureCode.PARTITION_FAILURE
    assert report.provider_attempt_count == 1
    assert report.failed_count == 1
    assert report.not_attempted_count == 2
    assert report.results[0].final_manifest is (
        catalog.manifest if expected_manifest else None
    )
    assert report.results[0].failure_category is expected_category
    assert report.results[0].error_code == "PARTITION_FAILURE"
    assert "secret" not in report.results[0].error_code


@pytest.mark.parametrize(
    ("error_type", "expected_code"),
    [
        (PartitionClockFailure, RunFailureCode.PARTITION_FAILURE),
        (PartitionLifecycleConflict, RunFailureCode.PARTITION_FAILURE),
        (PartitionCatalogFailure, RunFailureCode.CATALOG_UNAVAILABLE),
    ],
)
def test_post_attempt_lifecycle_exceptions_are_fatal_and_preserve_current_evidence(
    tmp_path: Path,
    error_type: type[Exception],
    expected_code: RunFailureCode,
) -> None:
    schedule = _three_month_schedule()

    class Catalog(_Catalog):
        manifest: PartitionManifest | None = None

        def get_manifest(self, _plan: object) -> PartitionManifest | None:
            return self.manifest

    catalog = Catalog()
    executed: list[date] = []

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            executed.append(plan.from_date)  # type: ignore[union-attr]
            run_id = kwargs["run_id"]
            assert type(run_id) is str
            catalog.manifest = _in_progress_manifest(plan, run_id)
            fetcher = kwargs["fetcher"]
            fetcher._remaining_attempts -= 1  # type: ignore[union-attr,reportPrivateUsage]
            raise error_type("secret external detail")

        return SimpleNamespace(execute=execute)

    report = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(fetch=lambda _request: None)
        ),  # type: ignore[arg-type]
        run_id_factory=lambda: "current-run",
        lease_acquirer=_lease,  # type: ignore[arg-type]
        catalog_factory=lambda _root: catalog,  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(schedule),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 3, 31),
            "1m",
            tmp_path,
            schedule,
            "nse-equity-month@v1",
            max_total_provider_attempts=3,
        )
    )

    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is expected_code
    assert executed == [date(2026, 1, 1)]
    assert report.provider_attempt_count == 1
    assert report.results[0].ingestion_run_id == "current-run"
    assert report.results[0].final_manifest is catalog.manifest
    assert report.not_attempted_count == 2
    assert "secret" not in report.results[0].error_code  # type: ignore[operator]


def test_typed_current_manifest_lookup_failure_preserves_lifecycle_primary(
    tmp_path: Path,
) -> None:
    executed: list[date] = []
    fetches: list[object] = []

    class Catalog(_Catalog):
        def get_manifest(self, _plan: object) -> None:
            raise CatalogPersistenceError("catalog unavailable")

    def lifecycle_factory(**_kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> None:
            executed.append(plan.from_date)  # type: ignore[union-attr]
            raise PartitionClockFailure("clock unavailable")

        return SimpleNamespace(execute=execute)

    report = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(fetch=fetches.append)
        ),  # type: ignore[arg-type]
        lease_acquirer=_lease,
        catalog_factory=lambda _root: Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 2, 28),
            "1m",
            tmp_path,
            _wide_schedule(),
            "nse-equity-month@v1",
            max_total_provider_attempts=2,
        )
    )

    assert report.failure_code is RunFailureCode.PARTITION_FAILURE
    assert executed == [date(2026, 1, 1), date(2026, 2, 1)]
    assert fetches == []
    assert report.failed_count == 2
    assert report.not_attempted_count == 0


def test_unknown_current_manifest_lookup_fault_escapes_lifecycle_mapping(
    tmp_path: Path,
) -> None:
    failure = RuntimeError("private-current-manifest-implementation-fault")
    executed: list[date] = []
    fetches: list[object] = []

    class Catalog(_Catalog):
        def get_manifest(self, _plan: object) -> None:
            raise failure

    def lifecycle_factory(**_kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> None:
            executed.append(plan.from_date)  # type: ignore[union-attr]
            raise PartitionClockFailure("clock unavailable")

        return SimpleNamespace(execute=execute)

    coordinator = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(fetch=fetches.append)
        ),  # type: ignore[arg-type]
        lease_acquirer=_lease,
        catalog_factory=lambda _root: Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(_wide_schedule()),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    )
    command = IngestionCommand(
        _instrument(),
        date(2026, 1, 1),
        date(2026, 2, 28),
        "1m",
        tmp_path,
        _wide_schedule(),
        "nse-equity-month@v1",
        max_total_provider_attempts=2,
    )

    with pytest.raises(RuntimeError) as raised:
        coordinator.run(command)

    assert raised.value is failure
    assert executed == [date(2026, 1, 1)]
    assert fetches == []


def test_between_partition_cancellation_marks_every_remaining_plan_cancelled(
    tmp_path: Path,
) -> None:
    cancellation = CancellationToken()

    def lifecycle_factory(**_kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            cancellation.cancel()
            return _lifecycle_result(
                plan,
                PartitionLifecycleOutcome.VERIFIED,
                _kwargs["run_id"],  # type: ignore[arg-type]
            )

        return SimpleNamespace(execute=execute)

    schedule = _wide_schedule()
    march = ExpectedSessionSchedule(
        schedule.schema_version,
        schedule.source,
        schedule.source_release,
        datetime(2026, 4, 1, tzinfo=UTC),
        schedule.timezone,
        date(2026, 1, 1),
        date(2026, 3, 31),
        schedule.sessions,
        _closures(date(2026, 1, 1), date(2026, 3, 31), schedule.sessions),
    )
    report = IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(fetch=lambda _request: None)
        ),  # type: ignore[arg-type]
        cancellation=cancellation,
        lease_acquirer=_lease,
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(march),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 3, 31),
            "1m",
            tmp_path,
            march,
            "nse-equity-month@v1",
            max_total_provider_attempts=3,
        )
    )

    assert report.outcome is IngestionRunOutcome.PARTIAL
    assert report.failure_code is RunFailureCode.CANCELLED
    assert report.verified_count == 1
    assert report.cancelled_count == 2
    assert report.not_attempted_count == 0


def test_in_flight_cancellation_keeps_current_result_and_later_plans_not_attempted(
    tmp_path: Path,
) -> None:
    cancellation = CancellationToken()
    schedule = _three_month_schedule()

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            cancellation.cancel()
            return _lifecycle_result(
                plan,
                PartitionLifecycleOutcome.CANCELLED,
                kwargs["run_id"],  # type: ignore[arg-type]
                attempts=1,
            )

        return SimpleNamespace(execute=execute)

    report = _range_with_lifecycle(tmp_path, schedule, cancellation, lifecycle_factory)

    assert report.outcome is IngestionRunOutcome.CANCELLED
    assert report.failure_code is RunFailureCode.CANCELLED
    assert report.cancelled_count == 1
    assert report.not_attempted_count == 2
    assert report.provider_attempt_count == 1


def test_cancellation_after_all_terminal_results_is_observationally_irrelevant(
    tmp_path: Path,
) -> None:
    cancellation = CancellationToken()
    schedule = _three_month_schedule()
    calls = 0

    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: object) -> SimpleNamespace:
            nonlocal calls
            calls += 1
            if calls == 3:
                cancellation.cancel()
            return _lifecycle_result(
                plan,
                PartitionLifecycleOutcome.VERIFIED,
                kwargs["run_id"],  # type: ignore[arg-type]
            )

        return SimpleNamespace(execute=execute)

    report = _range_with_lifecycle(tmp_path, schedule, cancellation, lifecycle_factory)

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert report.verified_count == 3
    assert report.cancelled_count == 0


def _three_month_schedule() -> ExpectedSessionSchedule:
    schedule = _wide_schedule()
    return ExpectedSessionSchedule(
        schedule.schema_version,
        schedule.source,
        schedule.source_release,
        datetime(2026, 4, 1, tzinfo=UTC),
        schedule.timezone,
        date(2026, 1, 1),
        date(2026, 3, 31),
        schedule.sessions,
        _closures(date(2026, 1, 1), date(2026, 3, 31), schedule.sessions),
    )


def _range_with_lifecycle(
    tmp_path: Path,
    schedule: ExpectedSessionSchedule,
    cancellation: CancellationToken,
    lifecycle_factory: object,
    *,
    run_id_factory: object | None = None,
) -> IngestionReport:
    return IngestionCoordinator(
        session_factory=SimpleNamespace(
            open=lambda: SimpleNamespace(fetch=lambda _request: None)
        ),  # type: ignore[arg-type]
        cancellation=cancellation,
        run_id_factory=run_id_factory or (lambda: "run"),  # type: ignore[arg-type]
        lease_acquirer=_lease,
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(schedule),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 3, 31),
            "1m",
            tmp_path,
            schedule,
            "nse-equity-month@v1",
            max_total_provider_attempts=3,
        )
    )
