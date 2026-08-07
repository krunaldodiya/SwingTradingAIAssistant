"""Coordinate one request-minimal closed-month ingestion range."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from .catalog import DuckDBCatalog
from .historical import (
    AccountRateLimiter,
    CancellableSleeper,
    CancellationSignal,
    CancellationToken,
    HistoricalFetchCode,
    HistoricalFetchFailure,
    HistoricalFetchResult,
    HistoricalProviderSession,
    HistoricalRequestExecutor,
    JitterSource,
    RetryPolicy,
    UtcClock,
)
from .instruments import Instrument
from .manifest_lifecycle import FailureCategory, ManifestState, PartitionManifest
from .monthly_request_planner import PlannedInstrumentMonth, plan_upstox_equity_months
from .partition_ingestion import (
    PartitionCatalogFailure,
    PartitionIngestionExecutor,
    PartitionLifecycleOutcome,
    PartitionLifecycleResult,
)
from .partition_reconciliation import (
    PartitionDecision,
    RequestReason,
    reconcile_partition_plans,
)
from .partition_recovery import (
    PartitionRecoveryObserver,
    PartitionRecoveryOutcome,
    PartitionRecoveryResult,
)
from .schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceResult,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    canonical_schedule_bytes,
    schedule_covers_full_calendar_range,
    schedule_digest,
)
from .storage_root_lease import LeaseOutcome, LeaseResult, StorageRootLease
from .validation import EquityMonthValidationPolicy

_SAFE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_IST = timezone(timedelta(hours=5, minutes=30))


class _LifecycleResultUnsupported(ValueError):
    """A Child H result did not satisfy the exact coordinator boundary."""


class IngestionRunOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ALREADY_RUNNING = "ALREADY_RUNNING"
    REJECTED = "REJECTED"


class RunFailureCode(StrEnum):
    NONE = "NONE"
    UNSUPPORTED_INTERVAL = "UNSUPPORTED_INTERVAL"
    ALREADY_RUNNING = "ALREADY_RUNNING"
    PARTITION_NOT_CLOSED = "PARTITION_NOT_CLOSED"
    SCHEDULE_UNSUPPORTED = "SCHEDULE_UNSUPPORTED"
    STORAGE_UNSAFE = "STORAGE_UNSAFE"
    CATALOG_UNAVAILABLE = "CATALOG_UNAVAILABLE"
    ATTEMPT_BUDGET_INSUFFICIENT = "ATTEMPT_BUDGET_INSUFFICIENT"
    ATTEMPT_BUDGET_EXHAUSTED = "ATTEMPT_BUDGET_EXHAUSTED"
    MAPPING_MIGRATION_REQUIRED = "MAPPING_MIGRATION_REQUIRED"
    RETRY_WAIT_BOUND_EXCEEDED = "RETRY_WAIT_BOUND_EXCEEDED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    LOCAL_REPAIR_BLOCKED = "LOCAL_REPAIR_BLOCKED"
    CANCELLED = "CANCELLED"
    PARTITION_FAILURE = "PARTITION_FAILURE"


class PartitionOutcome(StrEnum):
    SKIPPED_VERIFIED = "SKIPPED_VERIFIED"
    RECOVERED_LOCALLY = "RECOVERED_LOCALLY"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class IngestionCommand:
    instrument: Instrument
    from_date: date
    to_date: date
    interval: str
    storage_root: Path
    expected_sessions: ExpectedSessionSchedule
    validation_policy_version: str
    retry_policy: RetryPolicy = RetryPolicy()
    max_total_provider_attempts: int = 1

    def __post_init__(self) -> None:
        if (
            type(self.instrument) is not Instrument
            or type(self.from_date) is not date
            or type(self.to_date) is not date
            or self.from_date > self.to_date
            or type(self.interval) is not str
            or type(self.storage_root) is not type(Path())
            or type(self.expected_sessions) is not ExpectedSessionSchedule
            or type(self.validation_policy_version) is not str
            or not self.validation_policy_version.strip()
            or type(self.retry_policy) is not RetryPolicy
            or type(self.max_total_provider_attempts) is not int
            or self.max_total_provider_attempts < 0
        ):
            raise ValueError("invalid ingestion command")
        if self.from_date < date(2022, 1, 1):
            raise ValueError("dates before 2022-01-01 are not supported")


@dataclass(frozen=True, slots=True)
class PartitionResult:
    plan: PlannedInstrumentMonth
    outcome: PartitionOutcome
    reconciliation_reasons: tuple[RequestReason, ...]
    ingestion_run_id: str | None
    provider_attempts: int
    final_manifest: PartitionManifest | None
    failure_category: FailureCategory | None
    error_code: str | None

    def __post_init__(self) -> None:
        if (
            type(self.plan) is not PlannedInstrumentMonth
            or type(self.outcome) is not PartitionOutcome
            or type(self.reconciliation_reasons) is not tuple
            or any(
                type(reason) is not RequestReason
                for reason in self.reconciliation_reasons
            )
            or type(self.ingestion_run_id) not in (str, type(None))
            or (
                self.ingestion_run_id is not None
                and _SAFE_ID.fullmatch(self.ingestion_run_id) is None
            )
            or type(self.provider_attempts) is not int
            or self.provider_attempts < 0
            or (
                self.final_manifest is not None
                and type(self.final_manifest) is not PartitionManifest
            )
            or (
                self.failure_category is not None
                and type(self.failure_category) is not FailureCategory
            )
            or (
                self.error_code is not None
                and (
                    type(self.error_code) is not str
                    or _SAFE_CODE.fullmatch(self.error_code) is None
                )
            )
        ):
            raise ValueError("invalid partition result")
        if self.outcome in {
            PartitionOutcome.SKIPPED_VERIFIED,
            PartitionOutcome.RECOVERED_LOCALLY,
            PartitionOutcome.VERIFIED,
        } and (self.failure_category is not None or self.error_code is not None):
            raise ValueError("invalid partition result")
        if self.outcome is PartitionOutcome.VERIFIED and self.provider_attempts < 1:
            raise ValueError("invalid partition result")
        if (
            self.outcome
            in {
                PartitionOutcome.SKIPPED_VERIFIED,
                PartitionOutcome.RECOVERED_LOCALLY,
                PartitionOutcome.NOT_ATTEMPTED,
            }
            and self.provider_attempts != 0
        ):
            raise ValueError("invalid partition result")
        if self.outcome is PartitionOutcome.NOT_ATTEMPTED and any(
            value is not None
            for value in (
                self.ingestion_run_id,
                self.final_manifest,
                self.failure_category,
                self.error_code,
            )
        ):
            raise ValueError("invalid partition result")
        if self.outcome is PartitionOutcome.FAILED and (
            self.error_code is None or self.error_code == "CANCELLED"
        ):
            raise ValueError("invalid partition result")
        if (
            self.outcome is PartitionOutcome.CANCELLED
            and self.error_code != "CANCELLED"
        ):
            raise ValueError("invalid partition result")


@dataclass(frozen=True, slots=True)
class IngestionReport:
    outcome: IngestionRunOutcome
    failure_code: RunFailureCode
    results: tuple[PartitionResult, ...]
    planned_count: int
    skipped_count: int
    locally_recovered_count: int
    provider_attempt_count: int
    verified_count: int
    failed_count: int
    not_attempted_count: int
    cancelled_count: int
    started_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.outcome) is not IngestionRunOutcome
            or type(self.failure_code) is not RunFailureCode
        ):
            raise ValueError("invalid ingestion report")
        if type(self.results) is not tuple or any(
            type(item) is not PartitionResult for item in self.results
        ):
            raise ValueError("invalid ingestion report")
        expected = {
            "planned_count": len(self.results),
            "skipped_count": sum(
                item.outcome is PartitionOutcome.SKIPPED_VERIFIED
                for item in self.results
            ),
            "locally_recovered_count": sum(
                item.outcome is PartitionOutcome.RECOVERED_LOCALLY
                for item in self.results
            ),
            "provider_attempt_count": sum(
                item.provider_attempts for item in self.results
            ),
            "verified_count": sum(
                item.outcome is PartitionOutcome.VERIFIED for item in self.results
            ),
            "failed_count": sum(
                item.outcome is PartitionOutcome.FAILED for item in self.results
            ),
            "not_attempted_count": sum(
                item.outcome is PartitionOutcome.NOT_ATTEMPTED for item in self.results
            ),
            "cancelled_count": sum(
                item.outcome is PartitionOutcome.CANCELLED for item in self.results
            ),
        }
        if any(getattr(self, key) != value for key, value in expected.items()):
            raise ValueError("ingestion report counts do not match results")
        if (
            type(self.started_at) is not datetime
            or type(self.completed_at) is not datetime
            or self.started_at.tzinfo is None
            or self.completed_at.tzinfo is None
            or self.completed_at < self.started_at
            or self.started_at.utcoffset() != timedelta(0)
            or self.completed_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("invalid ingestion report timestamps")
        completed = (
            self.skipped_count + self.locally_recovered_count + self.verified_count
        )
        if not _report_outcome_is_consistent(
            self.outcome,
            self.failure_code,
            completed,
            self.failed_count,
            self.not_attempted_count,
            self.cancelled_count,
        ):
            raise ValueError("ingestion report outcome contradicts results")


def _report_outcome_is_consistent(
    outcome: IngestionRunOutcome,
    failure_code: RunFailureCode,
    completed: int,
    failed: int,
    not_attempted: int,
    cancelled: int,
) -> bool:
    if outcome is IngestionRunOutcome.SUCCEEDED:
        return failure_code is RunFailureCode.NONE and not (
            failed or not_attempted or cancelled
        )
    if outcome is IngestionRunOutcome.ALREADY_RUNNING:
        return (
            failure_code is RunFailureCode.ALREADY_RUNNING
            and completed == failed == cancelled == 0
            and not_attempted > 0
        )
    if outcome is IngestionRunOutcome.REJECTED:
        return (
            failure_code
            in {
                RunFailureCode.UNSUPPORTED_INTERVAL,
                RunFailureCode.PARTITION_NOT_CLOSED,
                RunFailureCode.SCHEDULE_UNSUPPORTED,
                RunFailureCode.STORAGE_UNSAFE,
                RunFailureCode.ATTEMPT_BUDGET_INSUFFICIENT,
            }
            and completed == failed == cancelled == 0
        )
    if outcome is IngestionRunOutcome.CANCELLED:
        return (
            failure_code is RunFailureCode.CANCELLED
            and completed == 0
            and cancelled > 0
        )
    if outcome is IngestionRunOutcome.PARTIAL:
        return failure_code is not RunFailureCode.NONE and completed > 0
    return (
        outcome is IngestionRunOutcome.FAILED
        and failure_code is not RunFailureCode.NONE
        and completed == 0
        and (failed > 0 or not_attempted > 0)
    )


class ProviderSessionFactory(Protocol):
    def open(self) -> HistoricalProviderSession:
        """Open one authenticated provider session lazily."""

        ...


class ProviderSessionAuthenticationError(RuntimeError):
    """A session could not be opened because credentials are unavailable or invalid."""


class ProviderSessionAuthorizationError(RuntimeError):
    """A session opened by this account is not authorized for the requested service."""


class RunIdFactory(Protocol):
    def __call__(self) -> str:
        """Return one safe run identifier."""

        ...


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class _NoopLimiter:
    def acquire(
        self, cancellation: CancellationSignal, remaining_wait: timedelta
    ) -> timedelta | None:
        del cancellation, remaining_wait
        return timedelta(0)

    def defer_for(
        self, delay: timedelta, remaining_wait: timedelta
    ) -> timedelta | None:
        del delay, remaining_wait
        return timedelta(0)


class _UnavailableSessionFactory:
    def open(self) -> HistoricalProviderSession:
        raise RuntimeError()


class _RangeFetcher:
    def __init__(
        self,
        executor: HistoricalRequestExecutor,
        max_attempts: int,
        max_wait: timedelta,
    ) -> None:
        self._executor = executor
        self._remaining_attempts = max_attempts
        self._max_wait = max_wait
        self._used_wait = timedelta(0)

    def fetch(self, plan: PlannedInstrumentMonth) -> HistoricalFetchResult:
        if self._remaining_attempts < 1:
            return HistoricalFetchResult(
                response=None,
                attempts=0,
                failure=HistoricalFetchFailure(
                    # The executor normally produces this value.  This path is
                    # kept typed so no request is issued after exhaustion.
                    code=HistoricalFetchCode.ATTEMPT_BUDGET_EXHAUSTED,
                    attempts=0,
                ),
            )
        result = self._executor.fetch(
            plan,
            remaining_attempts=self._remaining_attempts,
            remaining_wait=max(self._max_wait - self._used_wait, timedelta(0)),
        )
        self._remaining_attempts -= result.attempts
        self._used_wait = result.wait_consumed
        return result

    @property
    def remaining_attempts(self) -> int:
        return self._remaining_attempts


class IngestionCoordinator:
    """Compose Children A through H for one sequential date-range command."""

    def __init__(
        self,
        *,
        session_factory: ProviderSessionFactory | None = None,
        limiter: AccountRateLimiter | None = None,
        clock: UtcClock | None = None,
        cancellation: CancellationSignal | None = None,
        sleeper: CancellableSleeper | None = None,
        jitter: JitterSource | None = None,
        event_sink: Callable[[object], None] | None = None,
        run_id_factory: RunIdFactory | None = None,
        lease_acquirer: Callable[[object], LeaseResult] = StorageRootLease.try_acquire,
        catalog_factory: Callable[
            [Path], AbstractContextManager[object]
        ] = DuckDBCatalog,
        schedule_store_factory: Callable[
            [Path, StorageRootLease], ScheduleEvidenceStore
        ] = ScheduleEvidenceStore,
        recovery_observer_factory: Callable[
            ..., PartitionRecoveryObserver
        ] = PartitionRecoveryObserver,
        lifecycle_executor_factory: Callable[
            ..., PartitionIngestionExecutor
        ] = PartitionIngestionExecutor,
    ) -> None:
        self._session_factory = session_factory or _UnavailableSessionFactory()
        self._limiter = limiter or _NoopLimiter()
        self._clock = clock or _SystemClock()
        self._cancellation = cancellation or CancellationToken()
        self._sleeper = sleeper
        self._jitter = jitter
        self._event_sink = event_sink
        self._run_id_factory = run_id_factory or (lambda: uuid4().hex)
        self._lease_acquirer = lease_acquirer
        self._catalog_factory = catalog_factory
        self._schedule_store_factory = schedule_store_factory
        self._recovery_observer_factory = recovery_observer_factory
        self._lifecycle_executor_factory = lifecycle_executor_factory

    def run(self, command: IngestionCommand) -> IngestionReport:
        started = self._now()
        prepared = self._prepare_run(command, started)
        if isinstance(prepared, IngestionReport):
            return prepared
        plans, policy = prepared

        lease_result = self._safe_acquire_lease(command.storage_root)
        if lease_result is None:
            return self._report(
                IngestionRunOutcome.REJECTED,
                RunFailureCode.STORAGE_UNSAFE,
                _not_attempted_results(plans),
                started,
            )
        if lease_result.outcome is LeaseOutcome.ALREADY_RUNNING:
            return self._report(
                IngestionRunOutcome.ALREADY_RUNNING,
                RunFailureCode.ALREADY_RUNNING,
                _not_attempted_results(plans),
                started,
            )
        lease = lease_result.lease
        if lease is None:
            return self._report(
                IngestionRunOutcome.REJECTED,
                RunFailureCode.STORAGE_UNSAFE,
                _not_attempted_results(plans),
                started,
            )

        try:
            with lease:
                return self._run_leased(command, plans, lease, policy, started)
        except Exception:
            return self._report(
                IngestionRunOutcome.FAILED,
                RunFailureCode.CATALOG_UNAVAILABLE,
                _not_attempted_results(plans),
                started,
            )

    def _prepare_run(
        self, command: IngestionCommand, started: datetime
    ) -> (
        tuple[tuple[PlannedInstrumentMonth, ...], EquityMonthValidationPolicy]
        | IngestionReport
    ):
        if command.interval != "1m":
            return self._report(
                IngestionRunOutcome.REJECTED,
                RunFailureCode.UNSUPPORTED_INTERVAL,
                (),
                started,
            )
        try:
            plans = _canonical_plans(command)
        except Exception:
            return self._report(
                IngestionRunOutcome.REJECTED,
                RunFailureCode.SCHEDULE_UNSUPPORTED,
                (),
                started,
            )
        if self._is_cancelled():
            return self._report(
                IngestionRunOutcome.CANCELLED,
                RunFailureCode.CANCELLED,
                _cancelled_results(plans),
                started,
            )
        if not _plans_are_closed(plans, self._local_date()):
            return self._report(
                IngestionRunOutcome.REJECTED,
                RunFailureCode.PARTITION_NOT_CLOSED,
                _not_attempted_results(plans),
                started,
            )
        if not _schedule_covers_plans(command.expected_sessions, plans):
            return self._report(
                IngestionRunOutcome.REJECTED,
                RunFailureCode.SCHEDULE_UNSUPPORTED,
                _not_attempted_results(plans),
                started,
            )
        try:
            policy = EquityMonthValidationPolicy(command.validation_policy_version)
        except Exception:
            return self._report(
                IngestionRunOutcome.REJECTED,
                RunFailureCode.SCHEDULE_UNSUPPORTED,
                _not_attempted_results(plans),
                started,
            )

        return plans, policy

    def _run_leased(
        self,
        command: IngestionCommand,
        plans: tuple[PlannedInstrumentMonth, ...],
        lease: StorageRootLease,
        policy: EquityMonthValidationPolicy,
        started: datetime,
    ) -> IngestionReport:
        try:
            schedule_store = self._schedule_store_factory(command.storage_root, lease)
            schedule = schedule_store.retain(command.expected_sessions)
        except Exception:
            return self._report(
                IngestionRunOutcome.REJECTED,
                RunFailureCode.SCHEDULE_UNSUPPORTED,
                _not_attempted_results(plans),
                started,
            )
        if not _is_exact_command_schedule(schedule, command.expected_sessions):
            return self._report(
                IngestionRunOutcome.REJECTED,
                RunFailureCode.SCHEDULE_UNSUPPORTED,
                _not_attempted_results(plans),
                started,
            )
        recovery_run_ids: set[str] = set()

        def recovery_run_id() -> str:
            value = self._run_id_factory()
            if type(value) is str:
                recovery_run_ids.add(value)
            return value

        with self._catalog_factory(command.storage_root) as catalog:
            observer = self._recovery_observer_factory(
                lease=lease,
                storage_root=command.storage_root,
                catalog=catalog,
                schedule_store=schedule_store,
                expected_sessions=schedule,
                validation_policy_version=command.validation_policy_version,
                clock=self._clock,
                run_id_factory=recovery_run_id,
                cancellation=self._cancellation,
            )
            recovery_results = self._observe_all(observer, plans)
            evidence = tuple(
                result.evidence
                for result in recovery_results
                if result.evidence is not None
            )
            decisions = reconcile_partition_plans(plans, evidence)
            by_plan = {decision.plan: decision for decision in decisions}
            local, pending, local_fatal = self._local_results(recovery_results, by_plan)
            completed = self._local_preflight(
                command,
                plans,
                local,
                pending,
                local_fatal,
                recovery_run_ids,
                started,
            )
            if completed is not None:
                return completed
            return self._execute_requests(
                command,
                plans,
                catalog,
                schedule,
                policy,
                local,
                pending,
                started,
            )

    def _local_preflight(
        self,
        command: IngestionCommand,
        plans: tuple[PlannedInstrumentMonth, ...],
        local: dict[int, PartitionResult],
        pending: dict[int, PartitionDecision],
        local_fatal: RunFailureCode | None,
        recovery_run_ids: set[str],
        started: datetime,
    ) -> IngestionReport | None:
        cancelled = [
            index
            for index, item in local.items()
            if item.outcome is PartitionOutcome.CANCELLED
        ]
        if cancelled:
            current = _current_recovery_cancellation(local, cancelled, recovery_run_ids)
            if current is None:
                for index in cancelled:
                    local.pop(index, None)
            return self._finish_cancelled(
                plans, local, pending, started, current=current
            )
        if local_fatal is not None:
            return self._finish_fatal(plans, local, pending, local_fatal, started)
        if not pending:
            return self._report(
                IngestionRunOutcome.SUCCEEDED,
                RunFailureCode.NONE,
                tuple(local[index] for index in range(len(plans))),
                started,
            )
        if self._is_cancelled():
            return self._finish_cancelled(plans, local, pending, started)
        if command.max_total_provider_attempts < len(pending):
            return self._report(
                IngestionRunOutcome.REJECTED,
                RunFailureCode.ATTEMPT_BUDGET_INSUFFICIENT,
                _merge_results(plans, local, pending, None),
                started,
            )
        return None

    def _observe_all(
        self,
        observer: PartitionRecoveryObserver,
        plans: Sequence[PlannedInstrumentMonth],
    ) -> tuple[PartitionRecoveryResult, ...]:
        results: list[PartitionRecoveryResult] = []
        for plan in plans:
            try:
                result = observer.observe(plan)
            except Exception:
                # The child owns diagnostic translation; the coordinator emits
                # only its stable run-level category at this boundary.
                result = _synthetic_recovery_failure(plan, "CATALOG_UNAVAILABLE")
            results.append(result)
            if _recovery_stops_run(result):
                break
        return tuple(results)

    def _local_results(
        self,
        recovery: Sequence[PartitionRecoveryResult],
        decisions: dict[PlannedInstrumentMonth, PartitionDecision],
    ) -> tuple[
        dict[int, PartitionResult], dict[int, PartitionDecision], RunFailureCode | None
    ]:
        local: dict[int, PartitionResult] = {}
        pending: dict[int, PartitionDecision] = {}
        fatal: RunFailureCode | None = None
        for index, result in enumerate(recovery):
            if result.outcome is PartitionRecoveryOutcome.SKIPPED_VERIFIED:
                local[index] = _partition_from_recovery(
                    result, PartitionOutcome.SKIPPED_VERIFIED, decisions[result.plan]
                )
            elif result.outcome is PartitionRecoveryOutcome.RECOVERED_LOCALLY:
                local[index] = _partition_from_recovery(
                    result, PartitionOutcome.RECOVERED_LOCALLY, decisions[result.plan]
                )
            elif result.outcome in {
                PartitionRecoveryOutcome.REQUEST_REQUIRED,
                PartitionRecoveryOutcome.INVALIDATED,
            }:
                pending[index] = decisions[result.plan]
            else:
                code = _run_code(result.error_code)
                local[index] = _partition_from_recovery(
                    result,
                    (
                        PartitionOutcome.CANCELLED
                        if code is RunFailureCode.CANCELLED
                        else PartitionOutcome.FAILED
                    ),
                    decisions[result.plan],
                )
                if code is not RunFailureCode.CANCELLED:
                    fatal = code or RunFailureCode.LOCAL_REPAIR_BLOCKED
        return local, pending, fatal

    def _execute_requests(
        self,
        command: IngestionCommand,
        plans: tuple[PlannedInstrumentMonth, ...],
        catalog: object,
        schedule: ScheduleEvidenceResult,
        policy: EquityMonthValidationPolicy,
        local: dict[int, PartitionResult],
        pending: dict[int, PartitionDecision],
        started: datetime,
    ) -> IngestionReport:
        provider, session_failure = self._open_provider(command)
        if provider is None:
            return self._finish_fatal(plans, local, pending, session_failure, started)
        fetcher = _RangeFetcher(
            provider,
            command.max_total_provider_attempts,
            command.retry_policy.max_total_wait,
        )
        results = dict(local)
        fatal: RunFailureCode | None = None
        for index, decision in pending.items():
            if self._is_cancelled():
                return self._finish_cancelled(plans, results, pending, started)
            result, mapped_fatal, run_id = self._execute_partition(
                command, catalog, schedule, policy, fetcher, decision
            )
            results[index] = result
            if result.error_code == "CANCELLED":
                if not _is_current_lifecycle_cancellation(result, run_id):
                    results[index] = _cancelled_result(decision.plan, decision.reasons)
                    return self._finish_cancelled(plans, results, pending, started)
                return self._finish_cancelled(
                    plans, results, pending, started, current=index
                )
            if mapped_fatal is not None:
                fatal = mapped_fatal
                break
            code = _run_code(result.error_code)
            if code in _FATAL_CODES:
                fatal = code
                break
            if fetcher.remaining_attempts == 0 and index != next(reversed(pending)):
                fatal = RunFailureCode.ATTEMPT_BUDGET_EXHAUSTED
                break
        if fatal is not None:
            return self._finish_fatal(plans, results, pending, fatal, started)
        return self._finish_results(plans, results, started)

    def _execute_partition(
        self,
        command: IngestionCommand,
        catalog: object,
        schedule: ScheduleEvidenceResult,
        policy: EquityMonthValidationPolicy,
        fetcher: _RangeFetcher,
        decision: PartitionDecision,
    ) -> tuple[PartitionResult, RunFailureCode | None, str | None]:
        remaining_before = fetcher.remaining_attempts
        run_id: str | None = None
        try:
            candidate_run_id = self._run_id_factory()
            if type(candidate_run_id) is str and _SAFE_ID.fullmatch(candidate_run_id):
                run_id = candidate_run_id
            executor = self._lifecycle_executor_factory(
                instrument=command.instrument,
                expected_sessions=schedule,
                validation_policy=policy,
                fetcher=fetcher,
                catalog=catalog,
                storage_root=command.storage_root,
                clock=self._clock,
                run_id=candidate_run_id,
                cancellation=self._cancellation,
            )
            lifecycle = executor.execute(decision.plan)
            if not _accepted_lifecycle_result(lifecycle, decision.plan, run_id):
                raise _LifecycleResultUnsupported
            return (
                _partition_from_lifecycle(lifecycle, decision),
                None,
                run_id,
            )
        except Exception as error:
            attempts = _attempt_delta(remaining_before, fetcher.remaining_attempts)
            manifest = _current_run_manifest(catalog, decision.plan, run_id)
            result, fatal = _partition_from_lifecycle_exception(
                decision.plan,
                decision.reasons,
                error,
                ingestion_run_id=run_id,
                provider_attempts=attempts,
                final_manifest=manifest,
                failure_category=_terminal_failure_category(manifest),
            )
            return result, fatal, run_id

    def _open_provider(
        self, command: IngestionCommand
    ) -> tuple[HistoricalRequestExecutor | None, RunFailureCode]:
        try:
            session = self._session_factory.open()
        except ProviderSessionAuthenticationError:
            return None, RunFailureCode.AUTHENTICATION_FAILED
        except ProviderSessionAuthorizationError:
            return None, RunFailureCode.AUTHORIZATION_FAILED
        except Exception:
            return None, RunFailureCode.AUTHENTICATION_FAILED
        try:
            return (
                HistoricalRequestExecutor(
                    session=session,
                    limiter=self._limiter,
                    retry_policy=command.retry_policy,
                    clock=self._clock,
                    sleeper=self._sleeper,
                    jitter=self._jitter,
                    cancellation=self._cancellation,
                    event_sink=self._event_sink,
                    run_id=self._run_id_factory(),
                ),
                RunFailureCode.NONE,
            )
        except Exception:
            return None, RunFailureCode.AUTHENTICATION_FAILED

    def _safe_acquire_lease(self, storage_root: Path) -> LeaseResult | None:
        try:
            result = self._lease_acquirer(storage_root)
            if type(result) is not LeaseResult:
                return None
            if (
                result.outcome is LeaseOutcome.ACQUIRED
                and type(result.lease) is not StorageRootLease
            ):
                return None
            return result
        except Exception:
            return None

    def _finish_fatal(
        self,
        plans: tuple[PlannedInstrumentMonth, ...],
        local: dict[int, PartitionResult],
        pending: dict[int, PartitionDecision],
        code: RunFailureCode,
        started: datetime,
    ) -> IngestionReport:
        results = _merge_results(plans, local, pending, None)
        return self._finish_results(plans, results, started, code=code)

    def _finish_cancelled(
        self,
        plans: tuple[PlannedInstrumentMonth, ...],
        local: dict[int, PartitionResult],
        pending: dict[int, PartitionDecision],
        started: datetime,
        *,
        current: int | None = None,
    ) -> IngestionReport:
        results = dict(local)
        if current is not None:
            current_result = results.get(current)
            if (
                current_result is None
                or current_result.outcome is not PartitionOutcome.CANCELLED
            ):
                decision = pending.get(current)
                if decision is not None:
                    results[current] = _cancelled_result(
                        decision.plan, decision.reasons
                    )
            for index, decision in pending.items():
                if index > current:
                    results[index] = _not_attempted_result(
                        decision.plan, decision.reasons
                    )
        else:
            for index, plan in enumerate(plans):
                if index not in results:
                    decision = pending.get(index)
                    results[index] = _cancelled_result(
                        plan, decision.reasons if decision is not None else ()
                    )
        report_results = _merge_results(plans, results, {}, None)
        completed = any(
            item.outcome
            in {
                PartitionOutcome.SKIPPED_VERIFIED,
                PartitionOutcome.RECOVERED_LOCALLY,
                PartitionOutcome.VERIFIED,
            }
            for item in report_results
        )
        outcome = (
            IngestionRunOutcome.PARTIAL if completed else IngestionRunOutcome.CANCELLED
        )
        return self._report(outcome, RunFailureCode.CANCELLED, report_results, started)

    def _finish_results(
        self,
        plans: tuple[PlannedInstrumentMonth, ...],
        results: dict[int, PartitionResult] | tuple[PartitionResult, ...],
        started: datetime,
        *,
        code: RunFailureCode | None = None,
    ) -> IngestionReport:
        ordered = _merge_results(plans, results, {}, None)
        has_failed = any(item.outcome is PartitionOutcome.FAILED for item in ordered)
        completed = any(
            item.outcome
            in {
                PartitionOutcome.SKIPPED_VERIFIED,
                PartitionOutcome.RECOVERED_LOCALLY,
                PartitionOutcome.VERIFIED,
            }
            for item in ordered
        )
        failure = code or (
            RunFailureCode.PARTITION_FAILURE if has_failed else RunFailureCode.NONE
        )
        if failure is RunFailureCode.NONE:
            outcome = IngestionRunOutcome.SUCCEEDED
        elif completed:
            outcome = IngestionRunOutcome.PARTIAL
        else:
            outcome = IngestionRunOutcome.FAILED
        return self._report(outcome, failure, ordered, started)

    def _report(
        self,
        outcome: IngestionRunOutcome,
        failure_code: RunFailureCode,
        results: tuple[PartitionResult, ...],
        started: datetime,
    ) -> IngestionReport:
        return IngestionReport(
            outcome,
            failure_code,
            results,
            len(results),
            sum(item.outcome is PartitionOutcome.SKIPPED_VERIFIED for item in results),
            sum(item.outcome is PartitionOutcome.RECOVERED_LOCALLY for item in results),
            sum(item.provider_attempts for item in results),
            sum(item.outcome is PartitionOutcome.VERIFIED for item in results),
            sum(item.outcome is PartitionOutcome.FAILED for item in results),
            sum(item.outcome is PartitionOutcome.NOT_ATTEMPTED for item in results),
            sum(item.outcome is PartitionOutcome.CANCELLED for item in results),
            started,
            self._now(),
        )

    def _now(self) -> datetime:
        try:
            value = self._clock.now()
            if type(value) is datetime and value.tzinfo is not None:
                return value.astimezone(UTC)
        except Exception:
            return datetime.now(UTC)
        return datetime.now(UTC)

    def _local_date(self) -> date:
        return self._now().astimezone(_IST).date()

    def _is_cancelled(self) -> bool:
        try:
            return self._cancellation.is_cancelled()
        except Exception:
            return True


_FATAL_CODES = frozenset(
    {
        RunFailureCode.AUTHENTICATION_FAILED,
        RunFailureCode.AUTHORIZATION_FAILED,
        RunFailureCode.CATALOG_UNAVAILABLE,
        RunFailureCode.LOCAL_REPAIR_BLOCKED,
        RunFailureCode.MAPPING_MIGRATION_REQUIRED,
        RunFailureCode.RETRY_WAIT_BOUND_EXCEEDED,
        RunFailureCode.ATTEMPT_BUDGET_EXHAUSTED,
    }
)


def _canonical_plans(command: IngestionCommand) -> tuple[PlannedInstrumentMonth, ...]:
    edge_plans = plan_upstox_equity_months(
        command.instrument,
        command.from_date,
        command.to_date,
        command.interval,
    )
    return tuple(
        PlannedInstrumentMonth(
            plan.provider,
            plan.instrument_key,
            plan.security_id,
            plan.symbol,
            plan.exchange,
            plan.segment,
            plan.instrument_type,
            plan.interval,
            plan.year,
            plan.month,
            date(plan.year, plan.month, 1),
            _month_end(plan.year, plan.month),
        )
        for plan in edge_plans
    )


def _plans_are_closed(
    plans: Sequence[PlannedInstrumentMonth],
    local_date: date,
) -> bool:
    return all(plan.to_date < local_date for plan in plans)


def _schedule_covers_plans(
    schedule: ExpectedSessionSchedule, plans: Sequence[PlannedInstrumentMonth]
) -> bool:
    return all(
        schedule_covers_full_calendar_range(schedule, plan.from_date, plan.to_date)
        for plan in plans
    )


def _is_exact_command_schedule(
    evidence: object, command_schedule: ExpectedSessionSchedule
) -> bool:
    try:
        canonical = canonical_schedule_bytes(command_schedule)
        digest = schedule_digest(command_schedule)
        return (
            type(evidence) is ScheduleEvidenceResult
            and evidence.outcome in {ScheduleOutcome.RETAINED, ScheduleOutcome.RESOLVED}
            and evidence.schedule is not None
            and type(evidence.canonical_bytes) is bytes
            and evidence.canonical_bytes == canonical
            and evidence.digest == digest
            and evidence.relative_path == f"calendar-schedules/sha256/{digest}.json"
            and canonical_schedule_bytes(evidence.schedule) == canonical
        )
    except Exception:
        return False


def _month_end(year: int, month: int) -> date:
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return next_month - timedelta(days=1)


def _partition_from_recovery(
    result: PartitionRecoveryResult,
    outcome: PartitionOutcome,
    decision: PartitionDecision,
) -> PartitionResult:
    manifest = result.final_manifest
    return PartitionResult(
        result.plan,
        outcome,
        decision.reasons,
        manifest.ingestion_run_id if manifest is not None else None,
        0,
        manifest,
        result.failure_category,
        result.error_code,
    )


def _partition_from_lifecycle(
    result: PartitionLifecycleResult,
    decision: PartitionDecision,
) -> PartitionResult:
    if type(result) is not PartitionLifecycleResult:
        raise _LifecycleResultUnsupported
    outcome = {
        PartitionLifecycleOutcome.SKIPPED_VERIFIED: PartitionOutcome.SKIPPED_VERIFIED,
        PartitionLifecycleOutcome.VERIFIED: PartitionOutcome.VERIFIED,
        PartitionLifecycleOutcome.FAILED: PartitionOutcome.FAILED,
        PartitionLifecycleOutcome.CANCELLED: PartitionOutcome.CANCELLED,
    }[result.outcome]
    return PartitionResult(
        result.plan,
        outcome,
        decision.reasons,
        result.ingestion_run_id,
        result.provider_attempts,
        result.final_manifest,
        result.failure_category,
        result.error_code,
    )


def _run_code(code: str | None) -> RunFailureCode | None:
    if code is None:
        return None
    try:
        return RunFailureCode(code)
    except ValueError:
        return None


def _recovery_stops_run(result: object) -> bool:
    try:
        code = _run_code(result.error_code)  # type: ignore[union-attr]
        return code is RunFailureCode.CANCELLED or code in _FATAL_CODES
    except Exception:
        return True


def _synthetic_recovery_failure(
    plan: PlannedInstrumentMonth, code: str
) -> PartitionRecoveryResult:
    return PartitionRecoveryResult(
        plan, PartitionRecoveryOutcome.FAILED, None, None, None, code, None
    )


def _failed_partition_result(
    plan: PlannedInstrumentMonth,
    reasons: tuple[RequestReason, ...],
    *,
    error_code: str = "PARTITION_FAILURE",
    failure_category: FailureCategory | None = None,
    ingestion_run_id: str | None = None,
    provider_attempts: int = 0,
    final_manifest: PartitionManifest | None = None,
) -> PartitionResult:
    return PartitionResult(
        plan,
        PartitionOutcome.FAILED,
        reasons,
        ingestion_run_id,
        provider_attempts,
        final_manifest,
        failure_category,
        error_code,
    )


def _partition_from_lifecycle_exception(
    plan: PlannedInstrumentMonth,
    reasons: tuple[RequestReason, ...],
    error: BaseException,
    *,
    ingestion_run_id: str | None,
    provider_attempts: int,
    final_manifest: PartitionManifest | None,
    failure_category: FailureCategory | None,
) -> tuple[PartitionResult, RunFailureCode | None]:
    """Translate Child H boundary failures without exposing exception details."""
    if type(error) is PartitionCatalogFailure:
        return (
            _failed_partition_result(
                plan,
                reasons,
                error_code=RunFailureCode.CATALOG_UNAVAILABLE.value,
                ingestion_run_id=ingestion_run_id,
                provider_attempts=provider_attempts,
                final_manifest=final_manifest,
                failure_category=failure_category,
            ),
            RunFailureCode.CATALOG_UNAVAILABLE,
        )
    result = _failed_partition_result(
        plan,
        reasons,
        ingestion_run_id=ingestion_run_id,
        provider_attempts=provider_attempts,
        final_manifest=final_manifest,
        failure_category=failure_category,
    )
    return (
        result,
        RunFailureCode.PARTITION_FAILURE
        if provider_attempts or type(error) is _LifecycleResultUnsupported
        else None,
    )


def _attempt_delta(before: object, after: object) -> int:
    if type(before) is not int or type(after) is not int:
        return 0
    return max(0, before - after)


def _current_run_manifest(
    catalog: object, plan: PlannedInstrumentMonth, run_id: str | None
) -> PartitionManifest | None:
    if run_id is None:
        return None
    try:
        manifest = cast(object, catalog.get_manifest(plan))  # type: ignore[union-attr]
        if (
            type(manifest) is PartitionManifest
            and manifest.plan == plan
            and manifest.ingestion_run_id == run_id
        ):
            return manifest
    except Exception:
        return None
    return None


def _terminal_failure_category(
    manifest: PartitionManifest | None,
) -> FailureCategory | None:
    if manifest is None:
        return None
    return manifest.failure_category if manifest.state is ManifestState.FAILED else None


def _is_current_lifecycle_cancellation(
    result: PartitionResult, run_id: str | None
) -> bool:
    if run_id is None or result.ingestion_run_id != run_id:
        return False
    manifest = result.final_manifest
    return manifest is not None and manifest.ingestion_run_id == run_id


def _accepted_lifecycle_result(
    result: object,
    plan: PlannedInstrumentMonth,
    run_id: str | None,
) -> bool:
    if type(result) is not PartitionLifecycleResult or result.plan != plan:
        return False
    if result.outcome is not PartitionLifecycleOutcome.VERIFIED:
        return True
    manifest = result.final_manifest
    return (
        run_id is not None
        and result.ingestion_run_id == run_id
        and type(manifest) is PartitionManifest
        and manifest.plan == plan
        and manifest.ingestion_run_id == run_id
        and manifest.state is ManifestState.VERIFIED
    )


def _current_recovery_cancellation(
    local: dict[int, PartitionResult],
    cancelled: Sequence[int],
    current_run_ids: set[str],
) -> int | None:
    for index in cancelled:
        manifest = local[index].final_manifest
        if manifest is not None and manifest.ingestion_run_id in current_run_ids:
            return index
    return None


def _not_attempted_result(
    plan: PlannedInstrumentMonth, reasons: tuple[RequestReason, ...] = ()
) -> PartitionResult:
    return PartitionResult(
        plan, PartitionOutcome.NOT_ATTEMPTED, reasons, None, 0, None, None, None
    )


def _cancelled_result(
    plan: PlannedInstrumentMonth, reasons: tuple[RequestReason, ...] = ()
) -> PartitionResult:
    return PartitionResult(
        plan, PartitionOutcome.CANCELLED, reasons, None, 0, None, None, "CANCELLED"
    )


def _not_attempted_results(
    plans: Sequence[PlannedInstrumentMonth],
) -> tuple[PartitionResult, ...]:
    return tuple(_not_attempted_result(plan) for plan in plans)


def _cancelled_results(
    plans: Sequence[PlannedInstrumentMonth],
) -> tuple[PartitionResult, ...]:
    return tuple(_cancelled_result(plan) for plan in plans)


def _merge_results(
    plans: Sequence[PlannedInstrumentMonth],
    values: dict[int, PartitionResult] | tuple[PartitionResult, ...],
    pending: dict[int, PartitionDecision],
    _unused: object,
) -> tuple[PartitionResult, ...]:
    if isinstance(values, tuple):
        return values
    return tuple(
        values.get(
            index,
            _not_attempted_result(
                plan,
                pending[index].reasons if index in pending else (),
            ),
        )
        for index, plan in enumerate(plans)
    )
