"""Bounded zero-provider query over verified one-minute Parquet evidence."""

from __future__ import annotations

import threading
from contextlib import ExitStack, suppress
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, cast

import duckdb as _duckdb

from .preview_admission import PreviewAdmissionPolicyV1
from .public_contract import (
    CandleFieldV1,
    CoverageStateV1,
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

duckdb: Any = cast(Any, _duckdb)

MAX_QUERY_PARQUET_PATHS_V1 = 12
MAX_QUERY_ROWS_V1 = 10_000
QUERY_MEMORY_LIMIT_V1 = "256MB"
QUERY_TIMEOUT_SECONDS_V1 = 5.0
_IST = timezone(timedelta(hours=5, minutes=30))


class QueryTimeoutV1(RuntimeError):
    """The bounded query exceeded its wall-clock deadline."""


class QueryResourceLimitV1(RuntimeError):
    """The bounded query exceeded rows or in-memory DuckDB resources."""


class QueryExecutionFailureV1(RuntimeError):
    """The verified query could not be executed safely."""


@dataclass(frozen=True, slots=True)
class QueryRequestV1:
    segment: str
    symbol: str
    from_date: date
    to_date: date
    timeframe: str
    fields: tuple[str, ...]
    max_rows: int
    storage_root: Path

    def __post_init__(self) -> None:
        if (
            type(self.segment) is not str
            or type(self.symbol) is not str
            or type(self.from_date) is not date
            or type(self.to_date) is not date
            or type(self.timeframe) is not str
            or type(self.fields) is not tuple
            or any(type(value) is not str for value in self.fields)
            or type(self.max_rows) is not int
            or type(self.storage_root) is not type(Path())
        ):
            raise ValueError("invalid query request")


class QueryClockV1(Protocol):
    def now(self) -> datetime: ...


class QueryAdmissionV1(Protocol):
    def __enter__(self) -> QueryAdmissionV1: ...

    def __exit__(self, *_: object) -> None: ...

    def ensure_live(self, root: object) -> None: ...


class QueryCoveragePortV1(Protocol):
    def admit(self, root: object) -> QueryAdmissionV1: ...

    def evaluate_under_admission(
        self,
        request: CoverageRequestV1,
        invocation_time: datetime,
        admission: ExistingCoverageAdmissionV1,
    ) -> CoverageEvaluationV1: ...

    def open_verified_partition_under_admission(
        self,
        root: Path,
        selection: VerifiedPartitionV1,
        admission: ExistingCoverageAdmissionV1,
    ) -> Any: ...


class OneMinuteQueryEnginePortV1(Protocol):
    def execute(
        self,
        request: PublicQueryRequestV1,
        root: Path,
        evaluation: CoverageEvaluationV1,
        evaluator: QueryCoveragePortV1,
        admission: QueryAdmissionV1,
    ) -> tuple[PublicQueryRowV1, ...]: ...


class OneMinuteQueryServiceV1:
    def __init__(
        self,
        policy: PreviewAdmissionPolicyV1,
        evaluator: QueryCoveragePortV1,
        *,
        engine: OneMinuteQueryEnginePortV1,
        clock: QueryClockV1,
    ) -> None:
        self._policy = policy
        self._evaluator = evaluator
        self._engine = engine
        self._clock = clock

    def query(self, request: object) -> QueryReportV1:
        try:
            request = _validated_request(request)
        except ValueError:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        if not self._policy.admits(request.segment, request.symbol):
            return _terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            )
        if request.timeframe != "1m":
            return _terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME,
            )
        try:
            public_request = _public_request(request)
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
            return self._query_under_admission(
                request, public_request, coverage_request, invocation
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

    def _query_under_admission(
        self,
        request: QueryRequestV1,
        public_request: PublicQueryRequestV1,
        coverage_request: CoverageRequestV1,
        invocation: datetime,
    ) -> QueryReportV1:
        with self._evaluator.admit(request.storage_root) as admission:
            evaluation = self._evaluator.evaluate_under_admission(
                coverage_request,
                invocation,
                cast(ExistingCoverageAdmissionV1, admission),
            )
            evaluation = _validated_evaluation(evaluation)
            empty_payload = QueryPayloadV1(public_request, 0, evaluation.months, ())
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
                    empty_payload,
                )
            rows = self._engine.execute(
                public_request,
                request.storage_root,
                evaluation,
                self._evaluator,
                admission,
            )
            admission.ensure_live(request.storage_root)
            payload = QueryPayloadV1(public_request, len(rows), evaluation.months, rows)
            return PublicCommandReportV1(
                "v1",
                "query",
                PublicCommandStatusV1.SUCCEEDED,
                None,
                0,
                payload,
            )


class DuckDBOneMinuteQueryEngineV1:
    """One in-memory, no-spill, descriptor-pinned direct-Parquet query."""

    def execute(
        self,
        request: PublicQueryRequestV1,
        root: Path,
        evaluation: CoverageEvaluationV1,
        evaluator: QueryCoveragePortV1,
        admission: QueryAdmissionV1,
    ) -> tuple[PublicQueryRowV1, ...]:
        try:
            if type(request) is not PublicQueryRequestV1:
                raise ValueError
            request = replace(request)
        except Exception:
            raise QueryExecutionFailureV1 from None
        evaluation = _validated_evaluation(evaluation)
        if (
            len(evaluation.verified_partitions) != len(evaluation.months)
            or not 1
            <= len(evaluation.verified_partitions)
            <= MAX_QUERY_PARQUET_PATHS_V1
        ):
            raise QueryExecutionFailureV1
        admission.ensure_live(root)
        try:
            with ExitStack() as handles:
                pinned = tuple(
                    cast(
                        VerifiedPartitionReadHandleV1,
                        handles.enter_context(
                            evaluator.open_verified_partition_under_admission(
                                root,
                                selection,
                                cast(ExistingCoverageAdmissionV1, admission),
                            )
                        ),
                    )
                    for selection in evaluation.verified_partitions
                )
                admission.ensure_live(root)
                rows = self._execute(request, pinned)
                admission.ensure_live(root)
                return rows
        except (QueryResourceLimitV1, QueryTimeoutV1, QueryExecutionFailureV1):
            raise
        except Exception:
            raise QueryExecutionFailureV1 from None

    def _execute(
        self,
        request: PublicQueryRequestV1,
        pinned: tuple[VerifiedPartitionReadHandleV1, ...],
    ) -> tuple[PublicQueryRowV1, ...]:
        connection: Any | None = None
        timer: threading.Timer | None = None
        deadline = threading.Event()
        try:
            active_connection: Any = duckdb.connect(config=_connection_config())
            connection = active_connection
            timer = threading.Timer(
                QUERY_TIMEOUT_SECONDS_V1,
                _expire_query,
                (deadline, active_connection),
            )
            timer.daemon = True
            timer.start()
            columns = _query_columns(request.fields)
            statement = (
                f"SELECT {', '.join(_select_expression(field) for field in columns)} "  # noqa: S608 -- identifiers come only from CandleFieldV1
                "FROM read_parquet(?) "
                "WHERE epoch_us(ts) >= ? AND epoch_us(ts) < ? "
                "ORDER BY ts ASC LIMIT ?"
            )
            start, end = _utc_epoch_bounds(request.from_date, request.to_date)
            raw_rows = active_connection.execute(
                statement,
                [
                    [handle.duckdb_path for handle in pinned],
                    start,
                    end,
                    request.max_rows + 1,
                ],
            ).fetchall()
            if len(raw_rows) > request.max_rows:
                raise QueryResourceLimitV1
            rows = tuple(_public_row(columns, raw) for raw in raw_rows)
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
        except (QueryResourceLimitV1, QueryTimeoutV1):
            raise
        except Exception:
            raise QueryExecutionFailureV1 from None
        finally:
            if timer is not None:
                timer.cancel()
                timer.join(timeout=1.0)
            if connection is not None:
                connection.close()


def _validated_request(value: object) -> QueryRequestV1:
    try:
        if type(value) is not QueryRequestV1:
            raise ValueError
        return replace(value)
    except Exception:
        raise ValueError("invalid query request") from None


def _public_request(request: QueryRequestV1) -> PublicQueryRequestV1:
    if (
        request.from_date > request.to_date
        or request.from_date < date(2022, 1, 1)
        or not _valid_root_syntax(request.storage_root)
    ):
        raise ValueError("invalid query request")
    if (
        _month_count(request.from_date, request.to_date) > 12
        or not 1 <= request.max_rows <= MAX_QUERY_ROWS_V1
    ):
        raise QueryResourceLimitV1
    try:
        fields = tuple(CandleFieldV1(value) for value in request.fields)
        return PublicQueryRequestV1(
            request.segment,
            request.symbol,
            request.from_date,
            request.to_date,
            "1m",
            fields,
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


def _validated_invocation(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("invalid query invocation")
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


def _utc_epoch_bounds(start: date, end: date) -> tuple[int, int]:
    start_local = datetime(start.year, start.month, start.day, tzinfo=_IST)
    after = end + timedelta(days=1)
    end_local = datetime(after.year, after.month, after.day, tzinfo=_IST)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    start_delta = start_local.astimezone(UTC) - epoch
    end_delta = end_local.astimezone(UTC) - epoch
    return (
        (start_delta.days * 86_400 + start_delta.seconds) * 1_000_000
        + start_delta.microseconds,
        (end_delta.days * 86_400 + end_delta.seconds) * 1_000_000
        + end_delta.microseconds,
    )


def _query_columns(
    selected: tuple[CandleFieldV1, ...],
) -> tuple[CandleFieldV1, ...]:
    return (CandleFieldV1.TS,) + tuple(
        field for field in selected if field is not CandleFieldV1.TS
    )


def _select_expression(field: CandleFieldV1) -> str:
    if field is CandleFieldV1.TS:
        return "epoch_us(ts) AS ts_epoch_us"
    if field in {
        CandleFieldV1.OPEN,
        CandleFieldV1.HIGH,
        CandleFieldV1.LOW,
        CandleFieldV1.CLOSE,
        CandleFieldV1.VOLUME,
    }:
        return field.value
    raise QueryExecutionFailureV1


def _public_row(columns: tuple[CandleFieldV1, ...], raw: object) -> PublicQueryRowV1:
    if type(raw) is not tuple:
        raise QueryExecutionFailureV1
    raw_values = cast(tuple[object, ...], raw)
    if len(raw_values) != len(columns):
        raise QueryExecutionFailureV1
    values: dict[CandleFieldV1, object] = dict(zip(columns, raw_values, strict=True))
    timestamp = values.get(CandleFieldV1.TS)
    if type(timestamp) is not int:
        raise QueryExecutionFailureV1
    return PublicQueryRowV1(
        datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=timestamp),
        _optional_float(values.get(CandleFieldV1.OPEN)),
        _optional_float(values.get(CandleFieldV1.HIGH)),
        _optional_float(values.get(CandleFieldV1.LOW)),
        _optional_float(values.get(CandleFieldV1.CLOSE)),
        _optional_int(values.get(CandleFieldV1.VOLUME)),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if type(value) is not float:
        raise QueryExecutionFailureV1
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise QueryExecutionFailureV1
    return value


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
