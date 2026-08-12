"""Session-anchored higher intraday views derived from canonical one-minute data."""

from __future__ import annotations

import threading
import time
from contextlib import ExitStack, suppress
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from inspect import Parameter, signature
from pathlib import Path
from typing import Any, Protocol, cast

import duckdb as _duckdb

from .daily_ohlcv import (
    DailyScheduleResolutionV1,
    DailyScheduleResolverPortV1,
    VerifiedClosureV1,
    VerifiedSessionV1,
)
from .equity_admission import EquityAdmissionPolicyV1, Nifty50AdmissionPolicyV1
from .public_contract import (
    DERIVED_INTRADAY_BUCKET_MINUTES_V1,
    DERIVED_INTRADAY_CALCULATION_VERSION_V1,
    MAX_DAILY_VOLUME_V1,
    CandleFieldV1,
    CoverageStateV1,
    DerivedIntradayQueryPayloadV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    PublicQueryRequestV1,
    PublicQueryRowV1,
    QueryPayloadV1,
    QueryReportV1,
)
from .public_coverage import (
    CoverageEvaluationFailureV1,
    CoverageEvaluationV1,
    CoverageRequestV1,
    ExistingCoverageAdmissionV1,
    VerifiedPartitionReadHandleV1,
    VerifiedPartitionV1,
)
from .public_query import (
    MAX_QUERY_PARQUET_PATHS_V1,
    QUERY_MEMORY_LIMIT_V1,
    QUERY_TIMEOUT_SECONDS_V1,
    QueryClockV1,
    QueryCoveragePortV1,
    QueryExecutionFailureV1,
    QueryRequestV1,
    QueryResourceLimitV1,
    QueryTimeoutV1,
)
from .schedule_evidence import (
    ScheduleEvidenceResult,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    canonical_schedule_bytes,
    schedule_digest,
)
from .storage_root_lease import LeaseOutcome, StorageRootLease

duckdb: Any = cast(Any, _duckdb)

__all__ = [
    "DERIVED_INTRADAY_CALCULATION_VERSION_V1",
    "DerivedEvidenceIncompleteV1",
    "DerivedIntradayQueryServiceV1",
    "DuckDBIntradayViewEngineV1",
    "OpenMonthDerivedIntradayQueryServiceV1",
    "RetainedOpenMonthScheduleResolverV1",
]

MAX_DERIVED_INPUT_ROWS_V1 = 500_000
_IST = timezone(timedelta(hours=5, minutes=30))


class _QueryDeadlineV1:
    """One monotonic deadline shared by a complete derived query operation."""

    def __init__(self, clock: QueryClockV1) -> None:
        candidate = getattr(clock, "monotonic", None)
        self._monotonic = candidate if callable(candidate) else time.monotonic
        start = self._monotonic()
        if type(start) not in (int, float):
            raise ValueError("invalid monotonic clock")
        self._ends_at = float(cast(float, start)) + QUERY_TIMEOUT_SECONDS_V1

    def remaining_seconds(self) -> float:
        value = self._monotonic()
        if type(value) not in (int, float):
            raise ValueError("invalid monotonic clock")
        return self._ends_at - float(cast(float, value))

    def ensure_live(self) -> None:
        if self.remaining_seconds() <= 0:
            raise QueryTimeoutV1


def _call_with_deadline(
    method: object, *args: object, deadline: _QueryDeadlineV1
) -> object:
    """Use an additive deadline seam when a dependency explicitly supports it."""
    if not callable(method):
        raise QueryExecutionFailureV1
    deadline.ensure_live()
    try:
        parameters = signature(method).parameters.values()
        accepts_deadline = any(
            parameter.name == "deadline" or parameter.kind is Parameter.VAR_KEYWORD
            for parameter in parameters
        )
    except (TypeError, ValueError):
        accepts_deadline = False
    value = method(*args, deadline=deadline) if accepts_deadline else method(*args)
    deadline.ensure_live()
    return value


def _ensure_deadline_live(deadline: _QueryDeadlineV1 | None) -> None:
    if deadline is not None:
        deadline.ensure_live()


class DerivedEvidenceIncompleteV1(RuntimeError):
    """The raw minute grid cannot prove every requested derived bucket."""


class MinuteQueryPortV1(Protocol):
    def query_under_lease(
        self,
        request: object,
        lease: StorageRootLease,
        *,
        deadline: _QueryDeadlineV1 | None = None,
    ) -> QueryReportV1: ...


class OpenMonthScheduleResolverPortV1(Protocol):
    def resolve(
        self,
        root: Path,
        digest: str,
        invocation: datetime,
        lease: StorageRootLease,
        *,
        deadline: _QueryDeadlineV1 | None = None,
    ) -> DailyScheduleResolutionV1: ...


class RetainedOpenMonthScheduleResolverV1:
    """Resolve exact authoritative sessions from retained immutable evidence."""

    def resolve(
        self,
        root: Path,
        digest: str,
        invocation: datetime,
        lease: StorageRootLease,
        *,
        deadline: _QueryDeadlineV1 | None = None,
    ) -> DailyScheduleResolutionV1:
        try:
            _ensure_deadline_live(deadline)
            result = ScheduleEvidenceStore(root, lease).resolve(
                digest, deadline=deadline
            )
            _ensure_deadline_live(deadline)
            if type(result) is not ScheduleEvidenceResult:
                raise ValueError
            evidence = replace(result)
            schedule = evidence.schedule
            if (
                evidence != result
                or evidence.outcome is not ScheduleOutcome.RESOLVED
                or schedule is None
                or evidence.digest != digest
                or schedule.as_of > invocation
                or schedule_digest(schedule) != digest
                or canonical_schedule_bytes(schedule) != evidence.canonical_bytes
            ):
                raise ValueError
            _ensure_deadline_live(deadline)
            return DailyScheduleResolutionV1(
                tuple(
                    VerifiedSessionV1(
                        session.trade_date,
                        session.open_at,
                        session.close_at,
                        digest,
                    )
                    for session in schedule.sessions
                ),
                tuple(
                    VerifiedClosureV1(closure.trade_date, digest)
                    for closure in schedule.closures
                ),
            )
        except QueryTimeoutV1:
            raise
        except Exception:
            raise QueryExecutionFailureV1 from None


class OpenMonthDerivedIntradayQueryServiceV1:
    """Aggregate persisted provisional minutes through the latest complete bucket."""

    def __init__(
        self,
        minute_service: MinuteQueryPortV1,
        resolver: OpenMonthScheduleResolverPortV1,
        *,
        clock: QueryClockV1,
    ) -> None:
        self._minute_service = minute_service
        self._resolver = resolver
        self._clock = clock

    def query(
        self, request: object
    ) -> PublicCommandReportV1[DerivedIntradayQueryPayloadV1]:
        try:
            typed = _validated_raw_request(request)
        except ValueError:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        acquired = StorageRootLease.try_admit_read_existing(typed.storage_root)
        if acquired.outcome is not LeaseOutcome.ACQUIRED or acquired.lease is None:
            return _terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )
        with acquired.lease as lease:
            return self.query_under_lease(typed, lease)

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> PublicCommandReportV1[DerivedIntradayQueryPayloadV1]:
        if type(lease) is not StorageRootLease:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        try:
            deadline = _QueryDeadlineV1(self._clock)
            prepared = _prepare_open_request(request, self._clock)
            deadline.ensure_live()
            if not isinstance(prepared, tuple):
                return prepared
            typed, invocation, public_request = prepared
            return self._query_prepared(
                typed, invocation, public_request, lease, deadline
            )
        except QueryTimeoutV1:
            return _terminal(
                PublicCommandStatusV1.FAILED, PublicFailureCodeV1.QUERY_TIMEOUT
            )
        except Exception:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            )

    def _query_prepared(
        self,
        typed: QueryRequestV1,
        invocation: datetime,
        public_request: PublicQueryRequestV1,
        lease: StorageRootLease,
        deadline: _QueryDeadlineV1,
    ) -> PublicCommandReportV1[DerivedIntradayQueryPayloadV1]:
        try:
            deadline.ensure_live()
            minute_request = replace(
                typed,
                timeframe="1m",
                fields=tuple(value.value for value in CandleFieldV1),
                max_rows=10_000,
            )
            report = _call_with_deadline(
                self._minute_service.query_under_lease,
                minute_request,
                lease,
                deadline=deadline,
            )
            forwarded = _forward_minute_failure(report, public_request)
            if forwarded is not None:
                return forwarded
            minute_payload = _validated_minute_payload(report, minute_request)
            if len(minute_payload.months) != 1:
                raise QueryExecutionFailureV1
            month = minute_payload.months[0]
            if month.schedule_digest_sha256 is None or month.data_cutoff is None:
                raise QueryExecutionFailureV1
            resolution = _call_with_deadline(
                self._resolver.resolve,
                typed.storage_root,
                month.schedule_digest_sha256,
                invocation,
                lease,
                deadline=deadline,
            )
            selected_sessions = _validated_open_resolution(
                public_request,
                month.schedule_digest_sha256,
                resolution,
            )
            try:
                deadline.ensure_live()
                rows = _aggregate_available_rows(
                    public_request,
                    selected_sessions,
                    minute_payload.rows,
                    month.data_cutoff,
                )
                deadline.ensure_live()
            except DerivedEvidenceIncompleteV1:
                return _open_incomplete_report(public_request, minute_payload)
            deadline.ensure_live()
            ExistingCoverageAdmissionV1(typed.storage_root, lease).ensure_live(
                typed.storage_root
            )
            deadline.ensure_live()
            payload = DerivedIntradayQueryPayloadV1(
                public_request,
                DERIVED_INTRADAY_CALCULATION_VERSION_V1,
                "raw",
                DERIVED_INTRADAY_BUCKET_MINUTES_V1[typed.timeframe],
                len(rows),
                minute_payload.months,
                rows,
            )
            return PublicCommandReportV1(
                "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
            )
        except QueryResourceLimitV1:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED,
            )
        except QueryTimeoutV1:
            return _terminal(
                PublicCommandStatusV1.FAILED, PublicFailureCodeV1.QUERY_TIMEOUT
            )
        except Exception:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            )


class DerivedIntradayQueryServiceV1:
    """Expose closed verified session views without provider activity."""

    def __init__(
        self,
        policy: EquityAdmissionPolicyV1,
        evaluator: QueryCoveragePortV1,
        *,
        resolver: DailyScheduleResolverPortV1,
        engine: DuckDBIntradayViewEngineV1,
        clock: QueryClockV1,
    ) -> None:
        self._policy = policy
        self._evaluator = evaluator
        self._resolver = resolver
        self._engine = engine
        self._clock = clock

    def query(
        self, request: object
    ) -> PublicCommandReportV1[DerivedIntradayQueryPayloadV1]:
        return self._query(request, None)

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> PublicCommandReportV1[DerivedIntradayQueryPayloadV1]:
        if type(lease) is not StorageRootLease:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        return self._query(request, lease)

    def _query(
        self, request: object, lease: StorageRootLease | None
    ) -> PublicCommandReportV1[DerivedIntradayQueryPayloadV1]:
        prepared = _prepare_closed_request(request, self._policy)
        if not isinstance(prepared, tuple):
            return prepared
        typed, public_request = prepared
        try:
            deadline = _QueryDeadlineV1(self._clock)
            invocation = _validated_invocation(self._clock.now())
            deadline.ensure_live()
            coverage_request = CoverageRequestV1(
                typed.segment,
                typed.symbol,
                typed.from_date,
                typed.to_date,
                typed.storage_root,
            )
            if lease is None:
                with self._evaluator.admit(typed.storage_root) as untyped_admission:
                    return self._execute(
                        typed,
                        public_request,
                        coverage_request,
                        invocation,
                        cast(ExistingCoverageAdmissionV1, untyped_admission),
                        deadline,
                    )
            return self._execute(
                typed,
                public_request,
                coverage_request,
                invocation,
                ExistingCoverageAdmissionV1(typed.storage_root, lease),
                deadline,
            )
        except CoverageEvaluationFailureV1 as error:
            return _terminal(error.status, error.code)
        except QueryResourceLimitV1:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED,
            )
        except QueryTimeoutV1:
            return _terminal(
                PublicCommandStatusV1.FAILED, PublicFailureCodeV1.QUERY_TIMEOUT
            )
        except Exception:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            )

    def _execute(
        self,
        request: QueryRequestV1,
        public_request: PublicQueryRequestV1,
        coverage_request: CoverageRequestV1,
        invocation: datetime,
        admission: ExistingCoverageAdmissionV1,
        deadline: _QueryDeadlineV1,
    ) -> PublicCommandReportV1[DerivedIntradayQueryPayloadV1]:
        deadline.ensure_live()
        evaluation = (
            _call_with_deadline(
                self._evaluator.evaluate_under_admission_with_policy,
                coverage_request,
                invocation,
                admission,
                self._policy,
                deadline=deadline,
            )
            if isinstance(self._policy, Nifty50AdmissionPolicyV1)
            else _call_with_deadline(
                self._evaluator.evaluate_under_admission,
                coverage_request,
                invocation,
                admission,
                deadline=deadline,
            )
        )
        evaluation = _validated_evaluation(evaluation)
        empty = _payload(public_request, evaluation, ())
        affected = tuple(
            month.month
            for month in evaluation.months
            if month.coverage_state is not CoverageStateV1.VERIFIED
        )
        if affected:
            return PublicCommandReportV1(
                "v1",
                "query",
                PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
                _failure(PublicFailureCodeV1.COVERAGE_INSUFFICIENT, affected),
                0,
                empty,
            )
        resolution = _call_with_deadline(
            self._resolver.resolve,
            public_request,
            request.storage_root,
            evaluation,
            invocation,
            admission,
            deadline=deadline,
        )
        sessions = _validated_resolution(public_request, evaluation, resolution)
        try:
            rows = _call_with_deadline(
                self._engine.execute,
                public_request,
                request.storage_root,
                evaluation,
                sessions,
                self._evaluator,
                admission,
                deadline=deadline,
            )
            rows = _validated_derived_rows(public_request, sessions, rows)
        except DerivedEvidenceIncompleteV1:
            months = tuple(month.month for month in evaluation.months)
            return PublicCommandReportV1(
                "v1",
                "query",
                PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
                _failure(PublicFailureCodeV1.COVERAGE_INSUFFICIENT, months),
                0,
                empty,
            )
        admission.ensure_live(request.storage_root)
        deadline.ensure_live()
        payload = _payload(public_request, evaluation, rows)
        return PublicCommandReportV1(
            "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
        )


class DuckDBIntradayViewEngineV1:
    """Aggregate verified descriptor-pinned Parquet under strict resource bounds."""

    def execute(
        self,
        request: PublicQueryRequestV1,
        root: Path,
        evaluation: CoverageEvaluationV1,
        sessions: tuple[VerifiedSessionV1, ...],
        evaluator: QueryCoveragePortV1,
        admission: ExistingCoverageAdmissionV1,
        *,
        deadline: _QueryDeadlineV1 | None = None,
    ) -> tuple[PublicQueryRowV1, ...]:
        try:
            if type(request) is not PublicQueryRequestV1:
                raise ValueError
            request = replace(request)
            evaluation = _validated_evaluation(evaluation)
            sessions = _validated_sessions(request, evaluation, sessions)
        except Exception:
            raise QueryExecutionFailureV1 from None
        bucket_minutes = DERIVED_INTRADAY_BUCKET_MINUTES_V1.get(request.timeframe)
        expected_output = (
            sum(
                (_session_minutes(session) + bucket_minutes - 1) // bucket_minutes
                for session in sessions
            )
            if bucket_minutes is not None
            else 0
        )
        if (
            bucket_minutes is None
            or len(evaluation.verified_partitions) != len(evaluation.months)
            or not 1
            <= len(evaluation.verified_partitions)
            <= MAX_QUERY_PARQUET_PATHS_V1
            or sum(_session_minutes(session) for session in sessions)
            > MAX_DERIVED_INPUT_ROWS_V1
            or expected_output > request.max_rows
        ):
            raise QueryResourceLimitV1
        if not sessions:
            return ()
        _ensure_deadline_live(deadline)
        admission.ensure_live(root)
        _ensure_deadline_live(deadline)
        try:
            with ExitStack() as handles:
                untyped = tuple(
                    handles.enter_context(
                        evaluator.open_verified_partition_under_admission(
                            root, selection, admission
                        )
                    )
                    for selection in evaluation.verified_partitions
                )
                pinned = _validated_handles(untyped, evaluation.verified_partitions)
                _ensure_deadline_live(deadline)
                admission.ensure_live(root)
                _ensure_deadline_live(deadline)
                rows = self._execute(
                    request, sessions, pinned, bucket_minutes, deadline=deadline
                )
                _ensure_deadline_live(deadline)
                admission.ensure_live(root)
                _ensure_deadline_live(deadline)
                return rows
        except (
            DerivedEvidenceIncompleteV1,
            QueryResourceLimitV1,
            QueryTimeoutV1,
            QueryExecutionFailureV1,
        ):
            raise
        except Exception:
            raise QueryExecutionFailureV1 from None

    def _execute(
        self,
        request: PublicQueryRequestV1,
        sessions: tuple[VerifiedSessionV1, ...],
        pinned: tuple[VerifiedPartitionReadHandleV1, ...],
        bucket_minutes: int,
        *,
        deadline: _QueryDeadlineV1 | None = None,
    ) -> tuple[PublicQueryRowV1, ...]:
        connection: Any | None = None
        timer: threading.Timer | None = None
        deadline_event = threading.Event()
        try:
            active: Any = duckdb.connect(config=_connection_config())
            connection = active
            timeout_seconds = (
                deadline.remaining_seconds()
                if deadline is not None
                else QUERY_TIMEOUT_SECONDS_V1
            )
            if timeout_seconds <= 0:
                raise QueryTimeoutV1
            timer = threading.Timer(
                timeout_seconds, _expire_query, (deadline_event, active)
            )
            timer.daemon = True
            timer.start()
            raw: object = active.execute(
                _INTRADAY_SQL,
                [
                    [_epoch_us(value.open_at) for value in sessions],
                    [_epoch_us(value.close_at) for value in sessions],
                    bucket_minutes * 60_000_000,
                    bucket_minutes * 60_000_000,
                    [value.duckdb_path for value in pinned],
                ],
            ).fetchall()
            rows = _intraday_rows(request, sessions, bucket_minutes, raw)
            timer.cancel()
            timer.join(timeout=1.0)
            timer = None
            if deadline_event.is_set():
                raise QueryTimeoutV1
            _ensure_deadline_live(deadline)
            return rows
        except duckdb.InterruptException:
            raise QueryTimeoutV1 from None
        except duckdb.OutOfMemoryException:
            raise QueryResourceLimitV1 from None
        except (
            DerivedEvidenceIncompleteV1,
            QueryResourceLimitV1,
            QueryTimeoutV1,
            QueryExecutionFailureV1,
        ):
            raise
        except Exception:
            raise QueryExecutionFailureV1 from None
        finally:
            if timer is not None:
                timer.cancel()
                timer.join(timeout=1.0)
            if connection is not None:
                connection.close()


_INTRADAY_SQL = """
WITH sessions AS (
    SELECT unnest(?)::BIGINT AS open_us, unnest(?)::BIGINT AS close_us
), joined AS (
    SELECT
        sessions.open_us,
        sessions.close_us,
        ?::BIGINT AS bucket_us,
        floor((epoch_us(candles.ts) - sessions.open_us) / ?::DOUBLE)::BIGINT AS bucket_index,
        candles.ts,
        candles.open,
        candles.high,
        candles.low,
        candles.close,
        candles.volume
    FROM sessions
    LEFT JOIN read_parquet(?) AS candles
      ON epoch_us(candles.ts) >= sessions.open_us
     AND epoch_us(candles.ts) < sessions.close_us
)
SELECT
    open_us,
    close_us,
    bucket_us,
    bucket_index,
    open_us + bucket_index * bucket_us AS bucket_start_us,
    least(open_us + (bucket_index + 1) * bucket_us, close_us) AS bucket_end_us,
    first(open ORDER BY ts),
    max(high),
    min(low),
    first(close ORDER BY ts DESC),
    sum(volume)::HUGEINT,
    count(ts)::BIGINT,
    count(DISTINCT ts)::BIGINT,
    min(epoch_us(ts)),
    max(epoch_us(ts)),
    count(ts) FILTER (
        WHERE (epoch_us(ts) - open_us) % 60000000 <> 0
    )::BIGINT
FROM joined
GROUP BY open_us, close_us, bucket_us, bucket_index
ORDER BY bucket_start_us
""".strip()


def _intraday_rows(
    request: PublicQueryRequestV1,
    sessions: tuple[VerifiedSessionV1, ...],
    bucket_minutes: int,
    value: object,
) -> tuple[PublicQueryRowV1, ...]:
    if type(value) is not list:
        raise QueryExecutionFailureV1
    raw_values = cast(list[object], value)
    expected = sum(
        (_session_minutes(session) + bucket_minutes - 1) // bucket_minutes
        for session in sessions
    )
    if len(raw_values) != expected or len(raw_values) > request.max_rows:
        raise DerivedEvidenceIncompleteV1
    rows = tuple(
        _intraday_row(request.fields, sessions, bucket_minutes, raw)
        for raw in raw_values
    )
    if any(left.ts >= right.ts for left, right in zip(rows, rows[1:], strict=False)):
        raise QueryExecutionFailureV1
    return rows


def _intraday_row(
    fields: tuple[CandleFieldV1, ...],
    sessions: tuple[VerifiedSessionV1, ...],
    bucket_minutes: int,
    raw: object,
) -> PublicQueryRowV1:
    if type(raw) is not tuple:
        raise QueryExecutionFailureV1
    values = cast(tuple[object, ...], raw)
    if len(values) != 16:
        raise QueryExecutionFailureV1
    (
        open_us,
        close_us,
        bucket_us,
        bucket_index,
        bucket_start_us,
        bucket_end_us,
        open_value,
        high,
        low,
        close,
        volume,
        row_count,
        distinct_count,
        first_us,
        last_us,
        off_grid_count,
    ) = values
    if (
        any(type(value) is not int for value in values[:6])
        or bucket_us != bucket_minutes * 60_000_000
    ):
        raise QueryExecutionFailureV1
    typed_open_us = cast(int, open_us)
    typed_close_us = cast(int, close_us)
    typed_bucket_us = cast(int, bucket_us)
    typed_bucket_index = cast(int, bucket_index)
    typed_bucket_start_us = cast(int, bucket_start_us)
    typed_bucket_end_us = cast(int, bucket_end_us)
    session = next(
        (
            value
            for value in sessions
            if _epoch_us(value.open_at) == typed_open_us
            and _epoch_us(value.close_at) == typed_close_us
        ),
        None,
    )
    expected_start = typed_open_us + typed_bucket_index * typed_bucket_us
    expected_end = min(expected_start + typed_bucket_us, typed_close_us)
    expected_rows = (expected_end - expected_start) // 60_000_000
    if (
        session is None
        or typed_bucket_index < 0
        or typed_bucket_start_us != expected_start
        or typed_bucket_end_us != expected_end
        or type(row_count) is not int
        or type(distinct_count) is not int
        or row_count != expected_rows
        or distinct_count != expected_rows
        or first_us != expected_start
        or last_us != expected_end - 60_000_000
        or type(off_grid_count) is not int
        or off_grid_count != 0
        or any(type(value) is not float for value in (open_value, high, low, close))
        or type(volume) is not int
    ):
        raise DerivedEvidenceIncompleteV1
    typed_open = cast(float, open_value)
    typed_high = cast(float, high)
    typed_low = cast(float, low)
    typed_close = cast(float, close)
    if typed_high < max(typed_open, typed_close, typed_low) or typed_low > min(
        typed_open, typed_close, typed_high
    ):
        raise QueryExecutionFailureV1
    if volume < 0 or volume > MAX_DAILY_VOLUME_V1:
        raise QueryResourceLimitV1
    selected = set(fields)
    return PublicQueryRowV1(
        _from_epoch_us(typed_bucket_start_us),
        typed_open if CandleFieldV1.OPEN in selected else None,
        typed_high if CandleFieldV1.HIGH in selected else None,
        typed_low if CandleFieldV1.LOW in selected else None,
        typed_close if CandleFieldV1.CLOSE in selected else None,
        volume if CandleFieldV1.VOLUME in selected else None,
    )


def _validated_evaluation(value: object) -> CoverageEvaluationV1:
    try:
        if type(value) is not CoverageEvaluationV1:
            raise ValueError
        return CoverageEvaluationV1(
            tuple(replace(item) for item in value.months),
            tuple(replace(item) for item in value.verified_partitions),
        )
    except Exception:
        raise QueryExecutionFailureV1 from None


def _validated_sessions(
    request: PublicQueryRequestV1,
    evaluation: CoverageEvaluationV1,
    value: object,
) -> tuple[VerifiedSessionV1, ...]:
    try:
        if type(value) is not tuple:
            raise ValueError
        untyped = cast(tuple[object, ...], value)
        if any(type(item) is not VerifiedSessionV1 for item in untyped):
            raise ValueError
        typed = cast(tuple[VerifiedSessionV1, ...], untyped)
        sessions = tuple(replace(item) for item in typed)
    except Exception:
        raise QueryExecutionFailureV1 from None
    digests = {
        (selection.plan.year, selection.plan.month): selection.schedule_digest_sha256
        for selection in evaluation.verified_partitions
    }
    if (
        sessions != value
        or any(
            not request.from_date <= item.trade_date <= request.to_date
            or digests.get((item.trade_date.year, item.trade_date.month))
            != item.schedule_digest_sha256
            for item in sessions
        )
        or any(
            left.open_at >= right.open_at or left.close_at > right.open_at
            for left, right in zip(sessions, sessions[1:], strict=False)
        )
    ):
        raise QueryExecutionFailureV1
    return sessions


def _validated_handles(
    value: object,
    selections: tuple[VerifiedPartitionV1, ...],
) -> tuple[VerifiedPartitionReadHandleV1, ...]:
    try:
        if type(value) is not tuple:
            raise ValueError
        untyped = cast(tuple[object, ...], value)
        if any(type(item) is not VerifiedPartitionReadHandleV1 for item in untyped):
            raise ValueError
        typed = cast(tuple[VerifiedPartitionReadHandleV1, ...], untyped)
        handles = tuple(replace(item) for item in typed)
    except Exception:
        raise QueryExecutionFailureV1 from None
    if handles != value or tuple(item.selection for item in handles) != selections:
        raise QueryExecutionFailureV1
    return handles


def _session_minutes(value: VerifiedSessionV1) -> int:
    return int((value.close_at - value.open_at).total_seconds() // 60)


def _epoch_us(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = value - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _from_epoch_us(value: int) -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=value)


def _connection_config() -> dict[str, object]:
    return {
        "threads": 1,
        "memory_limit": QUERY_MEMORY_LIMIT_V1,
        "max_temp_directory_size": "0B",
        "preserve_insertion_order": False,
        "autoinstall_known_extensions": False,
        "autoload_known_extensions": False,
    }


def _expire_query(deadline: threading.Event, connection: Any) -> None:
    deadline.set()
    with suppress(Exception):
        connection.interrupt()


def _validated_raw_request(value: object) -> QueryRequestV1:
    try:
        if type(value) is not QueryRequestV1:
            raise ValueError
        return replace(value)
    except Exception:
        raise ValueError("invalid derived intraday query request") from None


def _public_request(request: QueryRequestV1) -> PublicQueryRequestV1:
    if (
        request.from_date > request.to_date
        or request.from_date < date(2022, 1, 1)
        or not request.storage_root.is_absolute()
        or any(
            character in part
            for part in request.storage_root.parts
            for character in "~*?[]"
        )
    ):
        raise ValueError("invalid derived intraday request")
    if (
        (request.to_date.year - request.from_date.year) * 12
        + request.to_date.month
        - request.from_date.month
        + 1
        > 12
        or not 1 <= request.max_rows <= 10_000
    ):
        raise QueryResourceLimitV1
    try:
        return PublicQueryRequestV1(
            request.segment,
            request.symbol,
            request.from_date,
            request.to_date,
            cast(Any, request.timeframe),
            tuple(CandleFieldV1(value) for value in request.fields),
            request.max_rows,
        )
    except ValueError:
        raise QueryResourceLimitV1 from None


def _public_open_request(
    request: QueryRequestV1, invocation: datetime
) -> PublicQueryRequestV1:
    local_today = invocation.astimezone(_IST).date()
    if (
        request.timeframe not in DERIVED_INTRADAY_BUCKET_MINUTES_V1
        or (request.from_date.year, request.from_date.month)
        != (local_today.year, local_today.month)
        or (request.to_date.year, request.to_date.month)
        != (local_today.year, local_today.month)
        or request.to_date > local_today
    ):
        raise ValueError("invalid open-month derived query")
    return _public_request(request)


def _prepare_closed_request(
    request: object,
    policy: EquityAdmissionPolicyV1,
) -> (
    tuple[QueryRequestV1, PublicQueryRequestV1]
    | PublicCommandReportV1[DerivedIntradayQueryPayloadV1]
):
    try:
        typed = _validated_raw_request(request)
    except ValueError:
        return _terminal(
            PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
        )
    if not policy.admits(typed.segment, typed.symbol):
        return _terminal(
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
        )
    if typed.timeframe not in DERIVED_INTRADAY_BUCKET_MINUTES_V1:
        return _terminal(
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME,
        )
    try:
        return typed, _public_request(typed)
    except QueryResourceLimitV1:
        return _terminal(
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED,
        )
    except ValueError:
        return _terminal(
            PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
        )


def _prepare_open_request(
    request: object,
    clock: QueryClockV1,
) -> (
    tuple[QueryRequestV1, datetime, PublicQueryRequestV1]
    | PublicCommandReportV1[DerivedIntradayQueryPayloadV1]
):
    try:
        typed = _validated_raw_request(request)
    except ValueError:
        return _terminal(
            PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
        )
    if typed.timeframe not in DERIVED_INTRADAY_BUCKET_MINUTES_V1:
        return _terminal(
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME,
        )
    try:
        invocation = _validated_invocation(clock.now())
    except Exception:
        return _terminal(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        )
    try:
        return typed, invocation, _public_open_request(typed, invocation)
    except QueryResourceLimitV1:
        return _terminal(
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED,
        )
    except ValueError:
        return _terminal(
            PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
        )


def _forward_minute_failure(
    value: object,
    request: PublicQueryRequestV1,
) -> PublicCommandReportV1[DerivedIntradayQueryPayloadV1] | None:
    try:
        if type(value) is not PublicCommandReportV1:
            raise ValueError
        report = cast(PublicCommandReportV1[object], value)
        if report.command != "query" or report.provider_attempt_count != 0:
            raise ValueError
        if report.status is PublicCommandStatusV1.SUCCEEDED:
            return None
        if report.failure is None:
            raise ValueError
        failure = replace(report.failure)
        if type(report.payload) is QueryPayloadV1:
            typed_source = report.payload
            source = replace(
                typed_source,
                request=replace(typed_source.request),
                months=tuple(replace(value) for value in typed_source.months),
                rows=tuple(replace(value) for value in typed_source.rows),
            )
            if (
                source.request.segment != request.segment
                or source.request.symbol != request.symbol
                or source.request.from_date != request.from_date
                or source.request.to_date != request.to_date
                or source.request.timeframe != "1m"
                or source.request.fields != tuple(CandleFieldV1)
                or source.request.max_rows != 10_000
            ):
                raise ValueError
            empty = DerivedIntradayQueryPayloadV1(
                request,
                DERIVED_INTRADAY_CALCULATION_VERSION_V1,
                "raw",
                DERIVED_INTRADAY_BUCKET_MINUTES_V1[request.timeframe],
                0,
                source.months,
                (),
            )
            return PublicCommandReportV1(
                "v1", "query", report.status, failure, 0, empty
            )
        return _terminal(report.status, failure.code)
    except Exception:
        raise QueryExecutionFailureV1 from None


def _validated_minute_payload(value: object, request: QueryRequestV1) -> QueryPayloadV1:
    try:
        if type(value) is not PublicCommandReportV1:
            raise ValueError
        report = cast(PublicCommandReportV1[object], value)
        if (
            report.command != "query"
            or report.status is not PublicCommandStatusV1.SUCCEEDED
            or report.failure is not None
            or report.provider_attempt_count != 0
            or type(report.payload) is not QueryPayloadV1
        ):
            raise ValueError
        payload = replace(report.payload)
        if (
            payload.request.segment != request.segment
            or payload.request.symbol != request.symbol
            or payload.request.from_date != request.from_date
            or payload.request.to_date != request.to_date
            or payload.request.timeframe != "1m"
            or payload.request.fields != tuple(CandleFieldV1)
            or payload.request.max_rows != 10_000
        ):
            raise ValueError
        return payload
    except Exception:
        raise QueryExecutionFailureV1 from None


def _open_incomplete_report(
    request: PublicQueryRequestV1,
    source: QueryPayloadV1,
) -> PublicCommandReportV1[DerivedIntradayQueryPayloadV1]:
    empty = DerivedIntradayQueryPayloadV1(
        request,
        DERIVED_INTRADAY_CALCULATION_VERSION_V1,
        "raw",
        DERIVED_INTRADAY_BUCKET_MINUTES_V1[request.timeframe],
        0,
        source.months,
        (),
    )
    months = tuple(value.month for value in source.months)
    return PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
        _failure(PublicFailureCodeV1.COVERAGE_INSUFFICIENT, months),
        0,
        empty,
    )


def _validated_open_resolution(
    request: PublicQueryRequestV1,
    digest: str,
    value: object,
) -> tuple[VerifiedSessionV1, ...]:
    try:
        if type(value) is not DailyScheduleResolutionV1:
            raise ValueError
        resolution = replace(value)
    except Exception:
        raise QueryExecutionFailureV1 from None
    sessions = tuple(
        session
        for session in resolution.sessions
        if request.from_date <= session.trade_date <= request.to_date
    )
    closures = tuple(
        closure
        for closure in resolution.closures
        if request.from_date <= closure.trade_date <= request.to_date
    )
    observed = tuple(value.trade_date for value in (*sessions, *closures))
    expected = tuple(
        request.from_date + timedelta(days=offset)
        for offset in range((request.to_date - request.from_date).days + 1)
    )
    if (
        len(observed) != len(expected)
        or set(observed) != set(expected)
        or any(value.schedule_digest_sha256 != digest for value in sessions)
        or any(value.schedule_digest_sha256 != digest for value in closures)
    ):
        raise QueryExecutionFailureV1
    return sessions


def _validated_derived_rows(
    request: PublicQueryRequestV1,
    sessions: tuple[VerifiedSessionV1, ...],
    value: object,
) -> tuple[PublicQueryRowV1, ...]:
    try:
        if type(value) is not tuple:
            raise ValueError
        untyped = cast(tuple[object, ...], value)
        if any(type(row) is not PublicQueryRowV1 for row in untyped):
            raise ValueError
        rows = tuple(
            replace(row) for row in cast(tuple[PublicQueryRowV1, ...], untyped)
        )
    except Exception:
        raise QueryExecutionFailureV1 from None
    bucket_minutes = DERIVED_INTRADAY_BUCKET_MINUTES_V1.get(request.timeframe)
    if bucket_minutes is None:
        raise QueryExecutionFailureV1
    interval = timedelta(minutes=bucket_minutes)
    expected: list[datetime] = []
    for session in sessions:
        current = session.open_at
        while current < session.close_at:
            expected.append(current)
            current = min(current + interval, session.close_at)
    if rows != value or tuple(row.ts for row in rows) != tuple(expected):
        raise DerivedEvidenceIncompleteV1
    return rows


def _aggregate_available_rows(
    request: PublicQueryRequestV1,
    sessions: tuple[VerifiedSessionV1, ...],
    minute_rows: tuple[PublicQueryRowV1, ...],
    cutoff: datetime,
) -> tuple[PublicQueryRowV1, ...]:
    sessions, minute_rows, bucket_minutes = _validated_available_inputs(
        request, sessions, minute_rows, cutoff
    )
    by_timestamp = {value.ts: value for value in minute_rows}
    selected = set(request.fields)
    output: list[PublicQueryRowV1] = []
    available_through = cutoff.astimezone(UTC) + timedelta(minutes=1)
    interval = timedelta(minutes=bucket_minutes)
    for session in sessions:
        bucket_start = session.open_at
        while bucket_start < session.close_at:
            bucket_end = min(bucket_start + interval, session.close_at)
            if bucket_end > available_through:
                break
            bucket = _complete_bucket(by_timestamp, bucket_start, bucket_end)
            output.append(_aggregate_bucket(selected, bucket_start, bucket))
            if len(output) > request.max_rows:
                raise QueryResourceLimitV1
            bucket_start = bucket_end
    return tuple(output)


def _validated_available_inputs(
    request: PublicQueryRequestV1,
    sessions: tuple[VerifiedSessionV1, ...],
    minute_rows: tuple[PublicQueryRowV1, ...],
    cutoff: datetime,
) -> tuple[tuple[VerifiedSessionV1, ...], tuple[PublicQueryRowV1, ...], int]:
    bucket_minutes = DERIVED_INTRADAY_BUCKET_MINUTES_V1.get(request.timeframe)
    if bucket_minutes is None or cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise QueryExecutionFailureV1
    try:
        sessions = tuple(replace(value) for value in sessions)
        minute_rows = tuple(replace(value) for value in minute_rows)
    except Exception:
        raise QueryExecutionFailureV1 from None
    if (
        any(type(value) is not VerifiedSessionV1 for value in sessions)
        or any(type(value) is not PublicQueryRowV1 for value in minute_rows)
        or any(
            left.open_at >= right.open_at or left.close_at > right.open_at
            for left, right in zip(sessions, sessions[1:], strict=False)
        )
        or len({value.ts for value in minute_rows}) != len(minute_rows)
        or len(minute_rows) > 10_000
    ):
        raise QueryExecutionFailureV1
    full_fields = all(
        all(
            value is not None
            for value in (row.open, row.high, row.low, row.close, row.volume)
        )
        for row in minute_rows
    )
    if not full_fields:
        raise QueryExecutionFailureV1
    if any(
        row.ts > cutoff
        or not any(session.open_at <= row.ts < session.close_at for session in sessions)
        for row in minute_rows
    ):
        raise DerivedEvidenceIncompleteV1
    return sessions, minute_rows, bucket_minutes


def _complete_bucket(
    by_timestamp: dict[datetime, PublicQueryRowV1],
    start: datetime,
    end: datetime,
) -> tuple[PublicQueryRowV1, ...]:
    expected = tuple(
        start + timedelta(minutes=offset)
        for offset in range(int((end - start).total_seconds() // 60))
    )
    try:
        return tuple(by_timestamp[value] for value in expected)
    except KeyError:
        raise DerivedEvidenceIncompleteV1 from None


def _aggregate_bucket(
    selected: set[CandleFieldV1],
    start: datetime,
    bucket: tuple[PublicQueryRowV1, ...],
) -> PublicQueryRowV1:
    opens = cast(tuple[float, ...], tuple(value.open for value in bucket))
    highs = cast(tuple[float, ...], tuple(value.high for value in bucket))
    lows = cast(tuple[float, ...], tuple(value.low for value in bucket))
    closes = cast(tuple[float, ...], tuple(value.close for value in bucket))
    volumes = cast(tuple[int, ...], tuple(value.volume for value in bucket))
    volume = sum(volumes)
    if volume < 0 or volume > MAX_DAILY_VOLUME_V1:
        raise QueryResourceLimitV1
    return PublicQueryRowV1(
        start,
        opens[0] if CandleFieldV1.OPEN in selected else None,
        max(highs) if CandleFieldV1.HIGH in selected else None,
        min(lows) if CandleFieldV1.LOW in selected else None,
        closes[-1] if CandleFieldV1.CLOSE in selected else None,
        volume if CandleFieldV1.VOLUME in selected else None,
    )


def _validated_invocation(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("invalid derived query invocation")
    return value.astimezone(UTC)


def _validated_resolution(
    request: PublicQueryRequestV1,
    evaluation: CoverageEvaluationV1,
    value: object,
) -> tuple[VerifiedSessionV1, ...]:
    try:
        if type(value) is not DailyScheduleResolutionV1:
            raise ValueError
        resolution = replace(value)
    except Exception:
        raise QueryExecutionFailureV1 from None
    sessions = _validated_sessions(request, evaluation, resolution.sessions)
    digests = {
        (selection.plan.year, selection.plan.month): selection.schedule_digest_sha256
        for selection in evaluation.verified_partitions
    }
    if any(
        not request.from_date <= item.trade_date <= request.to_date
        or digests.get((item.trade_date.year, item.trade_date.month))
        != item.schedule_digest_sha256
        for item in resolution.closures
    ):
        raise QueryExecutionFailureV1
    observed = {item.trade_date for item in sessions} | {
        item.trade_date for item in resolution.closures
    }
    expected = {
        request.from_date + timedelta(days=offset)
        for offset in range((request.to_date - request.from_date).days + 1)
    }
    if observed != expected or len(sessions) + len(resolution.closures) != len(
        expected
    ):
        raise QueryExecutionFailureV1
    return sessions


def _payload(
    request: PublicQueryRequestV1,
    evaluation: CoverageEvaluationV1,
    rows: tuple[PublicQueryRowV1, ...],
) -> DerivedIntradayQueryPayloadV1:
    bucket_minutes = DERIVED_INTRADAY_BUCKET_MINUTES_V1.get(request.timeframe)
    if bucket_minutes is None:
        raise QueryExecutionFailureV1
    return DerivedIntradayQueryPayloadV1(
        request,
        DERIVED_INTRADAY_CALCULATION_VERSION_V1,
        "raw",
        bucket_minutes,
        len(rows),
        evaluation.months,
        rows,
    )


def _terminal(
    status: PublicCommandStatusV1,
    code: PublicFailureCodeV1,
) -> PublicCommandReportV1[DerivedIntradayQueryPayloadV1]:
    return PublicCommandReportV1("v1", "query", status, _failure(code, ()), 0, None)


def _failure(code: PublicFailureCodeV1, months: tuple[str, ...]) -> PublicFailureV1:
    return PublicFailureV1(code, None, None, None, None, months)
