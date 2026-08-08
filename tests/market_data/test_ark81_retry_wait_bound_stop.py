"""End-to-end proof that one retry wait ledger stops later provider work."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from swing_trading_ai_assistant.market_data.historical import (
    CancellationToken,
    HistoricalResponse,
    ProviderEvent,
    RetryPolicy,
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
    plan_upstox_equity_months,
)
from swing_trading_ai_assistant.market_data.partition_ingestion import (
    PartitionLifecycleOutcome,
    PartitionLifecycleResult,
)
from swing_trading_ai_assistant.market_data.partition_reconciliation import (
    RequestReason,
)
from swing_trading_ai_assistant.market_data.partition_recovery import (
    PartitionRecoveryOutcome,
)
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionRunOutcome,
    PartitionOutcome,
    PartitionResult,
    RunFailureCode,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceResult,
    ScheduleFailureCode,
    ScheduleOutcome,
    ScheduleSession,
    canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    StorageRootLease,
)


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
    covered_from = date(2026, 1, 1)
    covered_to = date(2026, 3, 31)
    closures: list[ScheduleClosure] = []
    current = covered_from
    while current <= covered_to:
        if current != session.trade_date:
            closures.append(ScheduleClosure(current, "nse-source"))
        current += timedelta(days=1)
    return ExpectedSessionSchedule(
        2,
        "nse",
        "2026-Q1",
        datetime(2026, 4, 1, tzinfo=UTC),
        "Asia/Kolkata",
        covered_from,
        covered_to,
        (session,),
        tuple(closures),
    )


class _Catalog:
    def __enter__(self) -> _Catalog:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _ScheduleStore:
    def __init__(self, schedule: ExpectedSessionSchedule) -> None:
        self._schedule = schedule

    def retain(self, _schedule: ExpectedSessionSchedule) -> ScheduleEvidenceResult:
        digest = schedule_digest(self._schedule)
        return ScheduleEvidenceResult(
            ScheduleOutcome.RETAINED,
            ScheduleFailureCode.NONE,
            self._schedule,
            canonical_schedule_bytes(self._schedule),
            digest,
            f"calendar-schedules/sha256/{digest}.json",
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
    outcome: PartitionLifecycleOutcome,
    run_id: str,
    *,
    attempts: int,
    error_code: str | None,
) -> PartitionLifecycleResult:
    active = _active_manifest(plan, run_id)
    if outcome is PartitionLifecycleOutcome.VERIFIED:
        return PartitionLifecycleResult(
            plan,
            outcome,
            run_id,
            attempts,
            verify_manifest(
                active,
                active.updated_at + timedelta(microseconds=1),
                datetime(plan.year, plan.month, 2, 3, 45, tzinfo=UTC),
                datetime(plan.year, plan.month, 2, 3, 45, tzinfo=UTC),
                1,
                "a" * 64,
                "canonical.parquet",
            ),
            None,
            None,
        )
    return PartitionLifecycleResult(
        plan,
        outcome,
        run_id,
        attempts,
        fail_manifest(
            active,
            active.updated_at + timedelta(microseconds=1),
            FailureCategory.PROVIDER_RETRYABLE,
        ),
        FailureCategory.PROVIDER_RETRYABLE,
        error_code,
    )


class _SessionFactory:
    def __init__(self, responses: list[HistoricalResponse]) -> None:
        self._responses = responses
        self.open_count = 0
        self.requests: list[object] = []

    def open(self) -> _SessionFactory:
        self.open_count += 1
        return self

    def fetch(self, request: object) -> HistoricalResponse:
        self.requests.append(request)
        return self._responses.pop(0)


class _Limiter:
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


class _Sleeper:
    def __init__(self) -> None:
        self.delays: list[timedelta] = []

    def sleep(self, delay: timedelta, _cancellation: CancellationToken) -> None:
        self.delays.append(delay)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _expected_plans() -> tuple[PlannedInstrumentMonth, ...]:
    return plan_upstox_equity_months(
        _instrument(), date(2026, 1, 1), date(2026, 3, 31), "1m"
    )


def _coordinator(
    schedule: ExpectedSessionSchedule,
    session_factory: _SessionFactory,
    limiter: _Limiter,
    sleeper: _Sleeper,
    events: list[ProviderEvent],
    clock: _Clock,
) -> IngestionCoordinator:
    def lifecycle_factory(**kwargs: object) -> SimpleNamespace:
        def execute(plan: PlannedInstrumentMonth) -> PartitionLifecycleResult:
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

    return IngestionCoordinator(
        session_factory=session_factory,  # type: ignore[arg-type]
        limiter=limiter,  # type: ignore[arg-type]
        clock=clock,  # type: ignore[arg-type]
        sleeper=sleeper,  # type: ignore[arg-type]
        jitter=SimpleNamespace(uniform=lambda lower, _upper: lower),  # type: ignore[arg-type]
        event_sink=events.append,
        run_id_factory=lambda: "ark81-run",
        lease_acquirer=StorageRootLease.try_acquire,
        catalog_factory=lambda _root: _Catalog(),  # type: ignore[arg-type]
        schedule_store_factory=lambda _root, _lease: _ScheduleStore(schedule),  # type: ignore[arg-type]
        recovery_observer_factory=_request_observer,  # type: ignore[arg-type]
        lifecycle_executor_factory=lifecycle_factory,  # type: ignore[arg-type]
    )


def test_retry_wait_bound_stops_before_second_sleep_or_later_month_request(
    tmp_path: Path,
) -> None:
    schedule = _schedule()
    hostile_response_rows: list[object] = [
        "secret-token",
        "/hostile/path",
        "hostile-payload",
    ]
    session_factory = _SessionFactory(
        [
            HistoricalResponse(200, []),
            HistoricalResponse(500, [hostile_response_rows]),
            HistoricalResponse(500, [hostile_response_rows]),
        ]
    )
    limiter = _Limiter()
    sleeper = _Sleeper()
    events: list[ProviderEvent] = []
    event_time = datetime(2026, 8, 8, 10, 30, tzinfo=UTC)

    report = _coordinator(
        schedule,
        session_factory,
        limiter,
        sleeper,
        events,
        _Clock(event_time),
    ).run(
        IngestionCommand(
            _instrument(),
            date(2026, 1, 1),
            date(2026, 3, 31),
            "1m",
            tmp_path,
            schedule,
            "nse-equity-month@v1",
            retry_policy=RetryPolicy(
                max_attempts_per_partition=3,
                base_backoff=timedelta(seconds=1),
                max_backoff=timedelta(seconds=1),
                max_total_wait=timedelta(milliseconds=750),
            ),
            max_total_provider_attempts=5,
        )
    )

    assert report.outcome is IngestionRunOutcome.PARTIAL
    assert report.failure_code is RunFailureCode.RETRY_WAIT_BOUND_EXCEEDED
    assert [item.outcome for item in report.results] == [
        PartitionOutcome.VERIFIED,
        PartitionOutcome.FAILED,
        PartitionOutcome.NOT_ATTEMPTED,
    ]
    assert all(type(item) is PartitionResult for item in report.results)
    assert [item.plan for item in report.results] == list(_expected_plans())
    assert [item.reconciliation_reasons for item in report.results] == [
        (RequestReason.MISSING_EVIDENCE,),
        (RequestReason.MISSING_EVIDENCE,),
        (RequestReason.MISSING_EVIDENCE,),
    ]
    assert [item.ingestion_run_id for item in report.results] == [
        "ark81-run",
        "ark81-run",
        None,
    ]
    assert [item.provider_attempts for item in report.results] == [1, 2, 0]
    assert [
        item.final_manifest.state if item.final_manifest is not None else None
        for item in report.results
    ] == [ManifestState.VERIFIED, ManifestState.FAILED, None]
    assert [item.failure_category for item in report.results] == [
        None,
        FailureCategory.PROVIDER_RETRYABLE,
        None,
    ]
    assert [item.error_code for item in report.results] == [
        None,
        "RETRY_WAIT_BOUND_EXCEEDED",
        None,
    ]
    assert (
        report.planned_count,
        report.skipped_count,
        report.locally_recovered_count,
        report.provider_attempt_count,
        report.verified_count,
        report.failed_count,
        report.not_attempted_count,
        report.cancelled_count,
    ) == (3, 0, 0, 3, 1, 1, 1, 0)
    assert [request.from_date for request in session_factory.requests] == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 2, 1),
    ]
    assert session_factory.open_count == 1
    assert limiter.acquires == [
        timedelta(milliseconds=750),
        timedelta(milliseconds=750),
        timedelta(milliseconds=250),
    ]
    assert limiter.deferrals == []
    assert sleeper.delays == [timedelta(milliseconds=500)]
    assert all(type(event) is ProviderEvent for event in events)
    assert [
        (
            event.run_id,
            event.attempt_ordinal,
            event.category,
            event.status_class,
            event.occurred_at,
        )
        for event in events
    ] == [
        ("ark81-run", 1, "provider_success", "2xx", event_time),
        ("ark81-run", 1, "provider_retryable", "5xx", event_time),
        ("ark81-run", 2, "provider_retryable", "5xx", event_time),
    ]
    public_evidence = repr((report, tuple(events)))
    assert "secret-token" not in public_evidence
    assert "/hostile/path" not in public_evidence
    assert "hostile-payload" not in public_evidence
