"""Session-aware daily OHLCV derived only from verified one-minute evidence."""

from __future__ import annotations

import threading
from contextlib import ExitStack, suppress
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, cast

import duckdb as _duckdb

from .equity_admission import EquityAdmissionPolicyV1, Nifty50AdmissionPolicyV1
from .public_contract import (
    DAILY_CALCULATION_VERSION_V1,
    MAX_DAILY_QUERY_ROWS_V1,
    MAX_DAILY_VOLUME_V1,
    CandleFieldV1,
    CoverageStateV1,
    DailyQueryPayloadV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    PublicQueryRequestV1,
    PublicQueryRowV1,
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
    ExpectedSessionSchedule,
    ScheduleEvidenceResult,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    canonical_schedule_bytes,
    schedule_digest,
)
from .storage_root_lease import StorageRootLease

duckdb: Any = cast(Any, _duckdb)

MAX_DAILY_SESSION_MINUTES_V1 = 600
MAX_DAILY_INPUT_ROWS_V1 = MAX_DAILY_QUERY_ROWS_V1 * MAX_DAILY_SESSION_MINUTES_V1
_IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True, slots=True)
class VerifiedSessionV1:
    trade_date: date
    open_at: datetime
    close_at: datetime
    schedule_digest_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.trade_date) is not date
            or not _utc_minute(self.open_at)
            or not _utc_minute(self.close_at)
            or self.close_at <= self.open_at
            or self.open_at.astimezone(_IST).date() != self.trade_date
            or self.close_at.astimezone(_IST).date() != self.trade_date
            or not _valid_digest(self.schedule_digest_sha256)
            or _session_minutes(self) > MAX_DAILY_SESSION_MINUTES_V1
        ):
            raise ValueError("invalid verified session")


@dataclass(frozen=True, slots=True)
class VerifiedClosureV1:
    trade_date: date
    schedule_digest_sha256: str

    def __post_init__(self) -> None:
        if type(self.trade_date) is not date or not _valid_digest(
            self.schedule_digest_sha256
        ):
            raise ValueError("invalid verified closure")


@dataclass(frozen=True, slots=True)
class DailyScheduleResolutionV1:
    sessions: tuple[VerifiedSessionV1, ...]
    closures: tuple[VerifiedClosureV1, ...]

    def __post_init__(self) -> None:
        try:
            sessions = tuple(replace(value) for value in self.sessions)
            closures = tuple(replace(value) for value in self.closures)
        except Exception:
            raise ValueError("invalid daily schedule resolution") from None
        session_dates = tuple(value.trade_date for value in sessions)
        closure_dates = tuple(value.trade_date for value in closures)
        if (
            type(self.sessions) is not tuple
            or any(type(value) is not VerifiedSessionV1 for value in self.sessions)
            or sessions != self.sessions
            or type(self.closures) is not tuple
            or any(type(value) is not VerifiedClosureV1 for value in self.closures)
            or closures != self.closures
            or session_dates != tuple(sorted(set(session_dates)))
            or closure_dates != tuple(sorted(set(closure_dates)))
            or set(session_dates) & set(closure_dates)
        ):
            raise ValueError("invalid daily schedule resolution")


class DailyScheduleResolverPortV1(Protocol):
    def resolve(
        self,
        request: PublicQueryRequestV1,
        root: Path,
        evaluation: CoverageEvaluationV1,
        invocation: datetime,
        admission: ExistingCoverageAdmissionV1,
    ) -> DailyScheduleResolutionV1: ...


class DailyQueryEnginePortV1(Protocol):
    def execute(
        self,
        request: PublicQueryRequestV1,
        root: Path,
        evaluation: CoverageEvaluationV1,
        sessions: tuple[VerifiedSessionV1, ...],
        evaluator: QueryCoveragePortV1,
        admission: ExistingCoverageAdmissionV1,
    ) -> tuple[PublicQueryRowV1, ...]: ...


class PublicQueryPortV1(Protocol):
    def query(self, request: object) -> QueryReportV1: ...

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1: ...


class TimeframeQueryServiceV1:
    """Route one validated raw request to exactly one timeframe service."""

    def __init__(
        self,
        minute_service: PublicQueryPortV1,
        daily_service: PublicQueryPortV1,
        *,
        intraday_service: PublicQueryPortV1 | None = None,
    ) -> None:
        self._minute_service = minute_service
        self._daily_service = daily_service
        self._intraday_service = intraday_service

    def query(self, request: object) -> QueryReportV1:
        return self._query(request, None)

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1:
        return self._query(request, lease)

    def _query(self, request: object, lease: StorageRootLease | None) -> QueryReportV1:
        try:
            typed = _validated_raw_request(request)
        except ValueError:
            return self._call(self._minute_service, request, lease)
        if typed.timeframe == "1d":
            return self._call(self._daily_service, typed, lease)
        if (
            typed.timeframe in {"3m", "5m", "15m", "30m", "1h"}
            and self._intraday_service is not None
        ):
            return self._call(self._intraday_service, typed, lease)
        return self._call(self._minute_service, typed, lease)

    @staticmethod
    def _call(
        service: PublicQueryPortV1,
        request: object,
        lease: StorageRootLease | None,
    ) -> QueryReportV1:
        return (
            service.query(request)
            if lease is None
            else service.query_under_lease(request, lease)
        )


class DailyQueryServiceV1:
    def __init__(
        self,
        policy: EquityAdmissionPolicyV1,
        evaluator: QueryCoveragePortV1,
        *,
        resolver: DailyScheduleResolverPortV1,
        engine: DailyQueryEnginePortV1,
        clock: QueryClockV1,
    ) -> None:
        self._policy = policy
        self._evaluator = evaluator
        self._resolver = resolver
        self._engine = engine
        self._clock = clock

    def query(self, request: object) -> QueryReportV1:
        return self._query(request, None)

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1:
        if type(lease) is not StorageRootLease:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        return self._query(request, lease)

    def _query(self, request: object, lease: StorageRootLease | None) -> QueryReportV1:
        try:
            request = _validated_raw_request(request)
        except ValueError:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        if not self._policy.admits(request.segment, request.symbol):
            return _terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            )
        if request.timeframe != "1d":
            return _terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME,
            )
        try:
            public_request = _public_daily_request(request)
        except QueryResourceLimitV1:
            return _terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED,
            )
        except ValueError:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        try:
            invocation = _validated_invocation(self._clock.now())
            coverage_request = CoverageRequestV1(
                request.segment,
                request.symbol,
                request.from_date,
                request.to_date,
                request.storage_root,
            )
            return self._execute_query(
                request,
                public_request,
                coverage_request,
                invocation,
                lease,
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

    def _execute_query(
        self,
        request: QueryRequestV1,
        public_request: PublicQueryRequestV1,
        coverage_request: CoverageRequestV1,
        invocation: datetime,
        lease: StorageRootLease | None,
    ) -> QueryReportV1:
        if lease is None:
            return self._query_under_admission(
                request, public_request, coverage_request, invocation
            )
        return self._query_with_admission(
            request,
            public_request,
            coverage_request,
            invocation,
            ExistingCoverageAdmissionV1(request.storage_root, lease),
        )

    def _query_under_admission(
        self,
        request: QueryRequestV1,
        public_request: PublicQueryRequestV1,
        coverage_request: CoverageRequestV1,
        invocation: datetime,
    ) -> QueryReportV1:
        with self._evaluator.admit(request.storage_root) as admission:
            return self._query_with_admission(
                request,
                public_request,
                coverage_request,
                invocation,
                cast(ExistingCoverageAdmissionV1, admission),
            )

    def _query_with_admission(
        self,
        request: QueryRequestV1,
        public_request: PublicQueryRequestV1,
        coverage_request: CoverageRequestV1,
        invocation: datetime,
        admission: ExistingCoverageAdmissionV1,
    ) -> QueryReportV1:
        evaluation = (
            self._evaluator.evaluate_under_admission_with_policy(
                coverage_request,
                invocation,
                admission,
                self._policy,
            )
            if isinstance(self._policy, Nifty50AdmissionPolicyV1)
            else self._evaluator.evaluate_under_admission(
                coverage_request,
                invocation,
                admission,
            )
        )
        evaluation = _validated_evaluation(evaluation)
        empty = DailyQueryPayloadV1(
            public_request,
            DAILY_CALCULATION_VERSION_V1,
            "raw",
            0,
            evaluation.months,
            (),
        )
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
        resolution = self._resolver.resolve(
            public_request,
            request.storage_root,
            evaluation,
            invocation,
            admission,
        )
        sessions = _validated_resolution(public_request, evaluation, resolution)
        if len(sessions) > public_request.max_rows:
            raise QueryResourceLimitV1
        rows = (
            self._engine.execute(
                public_request,
                request.storage_root,
                evaluation,
                sessions,
                self._evaluator,
                admission,
            )
            if sessions
            else ()
        )
        rows = _validated_daily_rows(public_request, sessions, rows)
        admission.ensure_live(request.storage_root)
        payload = DailyQueryPayloadV1(
            public_request,
            DAILY_CALCULATION_VERSION_V1,
            "raw",
            len(rows),
            evaluation.months,
            rows,
        )
        return PublicCommandReportV1(
            "v1",
            "query",
            PublicCommandStatusV1.SUCCEEDED,
            None,
            0,
            payload,
        )


class RetainedDailyScheduleResolverV1:
    """Resolve exact retained schedules under the coverage admission."""

    def resolve(
        self,
        request: PublicQueryRequestV1,
        root: Path,
        evaluation: CoverageEvaluationV1,
        invocation: datetime,
        admission: ExistingCoverageAdmissionV1,
    ) -> DailyScheduleResolutionV1:
        if type(admission) is not ExistingCoverageAdmissionV1:
            raise QueryExecutionFailureV1
        admission.ensure_live(root)
        sessions: list[VerifiedSessionV1] = []
        closures: list[VerifiedClosureV1] = []
        try:
            for selection in evaluation.verified_partitions:
                digest = selection.schedule_digest_sha256
                evidence = ScheduleEvidenceStore(root, admission.lease).resolve(digest)
                schedule = _validated_schedule_evidence(evidence, digest, invocation)
                start = max(request.from_date, selection.plan.from_date)
                end = min(request.to_date, selection.plan.to_date)
                if start > end:
                    raise ValueError
                if schedule.covered_from > start or schedule.covered_to < end:
                    raise ValueError
                covered = {
                    item.trade_date
                    for item in (*schedule.sessions, *schedule.closures)
                    if start <= item.trade_date <= end
                }
                if covered != set(_dates(start, end)):
                    raise ValueError
                sessions.extend(
                    VerifiedSessionV1(
                        item.trade_date, item.open_at, item.close_at, digest
                    )
                    for item in schedule.sessions
                    if start <= item.trade_date <= end
                )
                closures.extend(
                    VerifiedClosureV1(item.trade_date, digest)
                    for item in schedule.closures
                    if start <= item.trade_date <= end
                )
                admission.ensure_live(root)
        except Exception:
            raise QueryExecutionFailureV1 from None
        return DailyScheduleResolutionV1(tuple(sessions), tuple(closures))


def _validated_schedule_evidence(
    value: object, digest: str, invocation: datetime
) -> ExpectedSessionSchedule:
    try:
        if type(value) is not ScheduleEvidenceResult:
            raise ValueError
        evidence = replace(value)
        schedule = evidence.schedule
        if (
            evidence != value
            or evidence.outcome is not ScheduleOutcome.RESOLVED
            or schedule is None
            or evidence.digest != digest
            or schedule.as_of > invocation
            or schedule_digest(schedule) != digest
            or canonical_schedule_bytes(schedule) != evidence.canonical_bytes
        ):
            raise ValueError
        return replace(schedule)
    except Exception:
        raise QueryExecutionFailureV1 from None


class DuckDBDailyOHLCVEngineV1:
    """Aggregate authoritative sessions over descriptor-pinned Parquet."""

    def execute(
        self,
        request: PublicQueryRequestV1,
        root: Path,
        evaluation: CoverageEvaluationV1,
        sessions: tuple[VerifiedSessionV1, ...],
        evaluator: QueryCoveragePortV1,
        admission: ExistingCoverageAdmissionV1,
    ) -> tuple[PublicQueryRowV1, ...]:
        try:
            if type(request) is not PublicQueryRequestV1:
                raise ValueError
            request = replace(request)
        except Exception:
            raise QueryExecutionFailureV1 from None
        evaluation = _validated_evaluation(evaluation)
        sessions = _validated_sessions(request, evaluation, sessions)
        if (
            request.timeframe != "1d"
            or len(evaluation.verified_partitions) != len(evaluation.months)
            or not 1
            <= len(evaluation.verified_partitions)
            <= MAX_QUERY_PARQUET_PATHS_V1
            or len(sessions) > MAX_DAILY_QUERY_ROWS_V1
            or sum(_session_minutes(value) for value in sessions)
            > MAX_DAILY_INPUT_ROWS_V1
        ):
            raise QueryExecutionFailureV1
        if not sessions:
            return ()
        admission.ensure_live(root)
        try:
            with ExitStack() as handles:
                untyped_pinned = tuple(
                    handles.enter_context(
                        evaluator.open_verified_partition_under_admission(
                            root,
                            selection,
                            admission,
                        )
                    )
                    for selection in evaluation.verified_partitions
                )
                pinned = _validated_partition_handles(
                    untyped_pinned, evaluation.verified_partitions
                )
                admission.ensure_live(root)
                rows = self._execute(request, sessions, pinned)
                admission.ensure_live(root)
                return rows
        except (QueryResourceLimitV1, QueryTimeoutV1, QueryExecutionFailureV1):
            raise
        except Exception:
            raise QueryExecutionFailureV1 from None

    def _execute(
        self,
        request: PublicQueryRequestV1,
        sessions: tuple[VerifiedSessionV1, ...],
        pinned: tuple[VerifiedPartitionReadHandleV1, ...],
    ) -> tuple[PublicQueryRowV1, ...]:
        connection: Any | None = None
        timer: threading.Timer | None = None
        deadline = threading.Event()
        try:
            active: Any = duckdb.connect(config=_connection_config())
            connection = active
            timer = threading.Timer(
                QUERY_TIMEOUT_SECONDS_V1, _expire_query, (deadline, active)
            )
            timer.daemon = True
            timer.start()
            raw_rows = active.execute(
                _DAILY_SQL,
                [
                    [_epoch_us(value.open_at) for value in sessions],
                    [_epoch_us(value.close_at) for value in sessions],
                    [value.duckdb_path for value in pinned],
                ],
            ).fetchall()
            rows = _daily_rows(request, sessions, raw_rows)
            timer.cancel()
            timer.join(timeout=1.0)
            timer = None
            if deadline.is_set():
                raise QueryTimeoutV1
            return rows
        except duckdb.InterruptException:
            raise QueryTimeoutV1 from None
        except duckdb.OutOfMemoryException:
            raise QueryResourceLimitV1 from None
        except (QueryResourceLimitV1, QueryTimeoutV1, QueryExecutionFailureV1):
            raise
        except Exception:
            raise QueryExecutionFailureV1 from None
        finally:
            if timer is not None:
                timer.cancel()
                timer.join(timeout=1.0)
            if connection is not None:
                connection.close()


_DAILY_SQL = """
WITH sessions AS (
    SELECT unnest(?)::BIGINT AS open_us, unnest(?)::BIGINT AS close_us
)
SELECT
    sessions.open_us,
    sessions.close_us,
    first(candles.open ORDER BY candles.ts),
    max(candles.high),
    min(candles.low),
    first(candles.close ORDER BY candles.ts DESC),
    sum(candles.volume)::HUGEINT,
    count(candles.ts)::BIGINT,
    count(DISTINCT candles.ts)::BIGINT,
    min(epoch_us(candles.ts)),
    max(epoch_us(candles.ts)),
    count(candles.ts) FILTER (
        WHERE (epoch_us(candles.ts) - sessions.open_us) % 60000000 <> 0
    )::BIGINT
FROM sessions
LEFT JOIN read_parquet(?) AS candles
    ON epoch_us(candles.ts) >= sessions.open_us
    AND epoch_us(candles.ts) < sessions.close_us
GROUP BY sessions.open_us, sessions.close_us
ORDER BY sessions.open_us
""".strip()


def _daily_rows(
    request: PublicQueryRequestV1,
    sessions: tuple[VerifiedSessionV1, ...],
    raw_rows: object,
) -> tuple[PublicQueryRowV1, ...]:
    if type(raw_rows) is not list:
        raise QueryExecutionFailureV1
    raw_values = cast(list[object], raw_rows)
    if len(raw_values) != len(sessions):
        raise QueryExecutionFailureV1
    return tuple(
        _daily_row(request.fields, session, raw)
        for session, raw in zip(sessions, raw_values, strict=True)
    )


def _daily_row(
    fields: tuple[CandleFieldV1, ...],
    session: VerifiedSessionV1,
    raw: object,
) -> PublicQueryRowV1:
    if type(raw) is not tuple:
        raise QueryExecutionFailureV1
    values = cast(tuple[object, ...], raw)
    if len(values) != 12:
        raise QueryExecutionFailureV1
    (
        open_us,
        close_us,
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
    expected = _session_minutes(session)
    if (
        type(open_us) is not int
        or type(close_us) is not int
        or open_us != _epoch_us(session.open_at)
        or close_us != _epoch_us(session.close_at)
        or type(row_count) is not int
        or type(distinct_count) is not int
        or row_count != expected
        or distinct_count != expected
        or first_us != open_us
        or last_us != close_us - 60_000_000
        or type(off_grid_count) is not int
        or off_grid_count != 0
        or any(type(value) is not float for value in (open_value, high, low, close))
        or type(volume) is not int
    ):
        raise QueryExecutionFailureV1
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
        session.open_at,
        typed_open if CandleFieldV1.OPEN in selected else None,
        typed_high if CandleFieldV1.HIGH in selected else None,
        typed_low if CandleFieldV1.LOW in selected else None,
        typed_close if CandleFieldV1.CLOSE in selected else None,
        volume if CandleFieldV1.VOLUME in selected else None,
    )


def _validated_raw_request(value: object) -> QueryRequestV1:
    try:
        if type(value) is not QueryRequestV1:
            raise ValueError
        return replace(value)
    except Exception:
        raise ValueError("invalid daily query request") from None


def _public_daily_request(request: QueryRequestV1) -> PublicQueryRequestV1:
    if (
        request.from_date > request.to_date
        or request.from_date < date(2022, 1, 1)
        or not _valid_root_syntax(request.storage_root)
    ):
        raise ValueError("invalid daily query request")
    if (
        _month_count(request.from_date, request.to_date) > 12
        or not 1 <= request.max_rows <= MAX_DAILY_QUERY_ROWS_V1
    ):
        raise QueryResourceLimitV1
    try:
        return PublicQueryRequestV1(
            request.segment,
            request.symbol,
            request.from_date,
            request.to_date,
            "1d",
            tuple(CandleFieldV1(value) for value in request.fields),
            request.max_rows,
        )
    except ValueError:
        raise QueryResourceLimitV1 from None


def _validated_evaluation(value: object) -> CoverageEvaluationV1:
    try:
        if type(value) is not CoverageEvaluationV1:
            raise ValueError
        return CoverageEvaluationV1(
            tuple(replace(month) for month in value.months),
            tuple(replace(selection) for selection in value.verified_partitions),
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
        or len(sessions) > MAX_DAILY_QUERY_ROWS_V1
        or any(
            not request.from_date <= item.trade_date <= request.to_date
            or digests.get((item.trade_date.year, item.trade_date.month))
            != item.schedule_digest_sha256
            for item in sessions
        )
        or any(
            left.open_at >= right.open_at
            or left.trade_date >= right.trade_date
            or left.close_at > right.open_at
            for left, right in zip(sessions, sessions[1:], strict=False)
        )
    ):
        raise QueryExecutionFailureV1
    return sessions


def _validated_daily_rows(
    request: PublicQueryRequestV1,
    sessions: tuple[VerifiedSessionV1, ...],
    value: object,
) -> tuple[PublicQueryRowV1, ...]:
    try:
        if type(value) is not tuple:
            raise ValueError
        untyped = cast(tuple[object, ...], value)
        if any(type(item) is not PublicQueryRowV1 for item in untyped):
            raise ValueError
        typed = cast(tuple[PublicQueryRowV1, ...], untyped)
        rows = tuple(replace(item) for item in typed)
    except Exception:
        raise QueryExecutionFailureV1 from None
    selected = set(request.fields)
    if (
        rows != value
        or len(rows) != len(sessions)
        or tuple(item.ts for item in rows) != tuple(item.open_at for item in sessions)
        or any(
            (item.open is not None) != (CandleFieldV1.OPEN in selected)
            or (item.high is not None) != (CandleFieldV1.HIGH in selected)
            or (item.low is not None) != (CandleFieldV1.LOW in selected)
            or (item.close is not None) != (CandleFieldV1.CLOSE in selected)
            or (item.volume is not None) != (CandleFieldV1.VOLUME in selected)
            for item in rows
        )
    ):
        raise QueryExecutionFailureV1
    return rows


def _validated_partition_handles(
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
        pinned = tuple(replace(item) for item in typed)
    except Exception:
        raise QueryExecutionFailureV1 from None
    if (
        pinned != value
        or len(pinned) != len(selections)
        or tuple(item.selection for item in pinned) != selections
    ):
        raise QueryExecutionFailureV1
    return pinned


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
    observed = tuple(item.trade_date for item in sessions) + tuple(
        item.trade_date for item in resolution.closures
    )
    expected = _dates(request.from_date, request.to_date)
    if len(observed) != len(expected) or set(observed) != set(expected):
        raise QueryExecutionFailureV1
    return sessions


def _validated_invocation(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("invalid daily query invocation")
    return value.astimezone(UTC)


def _terminal(
    status: PublicCommandStatusV1, code: PublicFailureCodeV1
) -> QueryReportV1:
    return PublicCommandReportV1("v1", "query", status, _failure(code, ()), 0, None)


def _failure(code: PublicFailureCodeV1, months: tuple[str, ...]) -> PublicFailureV1:
    return PublicFailureV1(code, None, None, None, None, months)


def _valid_root_syntax(value: object) -> bool:
    return (
        type(value) is type(Path())
        and value.is_absolute()
        and not any(character in part for part in value.parts for character in "~*?[]")
    )


def _month_count(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1


def _dates(start: date, end: date) -> tuple[date, ...]:
    return tuple(
        start + timedelta(days=offset) for offset in range((end - start).days + 1)
    )


def _session_minutes(value: VerifiedSessionV1) -> int:
    delta = value.close_at - value.open_at
    return delta.days * 1_440 + delta.seconds // 60


def _utc_minute(value: object) -> bool:
    return (
        type(value) is datetime
        and value.utcoffset() == timedelta(0)
        and value.second == 0
        and value.microsecond == 0
    )


def _valid_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and not any(character not in "0123456789abcdef" for character in value)
    )


def _epoch_us(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = value - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


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
