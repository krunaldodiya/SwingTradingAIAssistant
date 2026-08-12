from __future__ import annotations

import gzip
import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

import swing_trading_ai_assistant.market_data.public_query as query_module
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    FetchedInstrumentSnapshotV1,
    InstrumentSnapshotStoreV1,
)
from swing_trading_ai_assistant.market_data.instruments import InstrumentCatalog
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.parquet import write_candles_parquet
from swing_trading_ai_assistant.market_data.partition_publication import (
    publish_partition,
)
from swing_trading_ai_assistant.market_data.preview_admission import (
    PreviewAdmissionPolicyV1,
)
from swing_trading_ai_assistant.market_data.public_contract import (
    CandleFieldV1,
    CoverageStateV1,
    PublicCommandStatusV1,
    PublicCoverageMonthV1,
    PublicFailureCodeV1,
    PublicQueryRequestV1,
)
from swing_trading_ai_assistant.market_data.public_coverage import (
    CoverageEvaluationFailureV1,
    CoverageEvaluationV1,
    VerifiedPartitionReadHandleV1,
    VerifiedPartitionV1,
)
from swing_trading_ai_assistant.market_data.public_query import (
    DuckDBOneMinuteQueryEngineV1,
    OneMinuteQueryServiceV1,
    QueryExecutionFailureV1,
    QueryRequestV1,
    QueryResourceLimitV1,
    QueryTimeoutV1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceStore,
    ScheduleSession,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50ConstituentV1,
    Nifty50UniverseSnapshotV1,
    Nifty50UniverseStoreV1,
)
from swing_trading_ai_assistant.market_data.validation import ValidationReason

NOW = datetime(2026, 8, 10, 4, 0, tzinfo=UTC)
DIGEST = "a" * 64


def _test_isin(index: int) -> str:
    prefix = f"INE{index:06d}A0"
    for digit in "0123456789":
        candidate = prefix + digit
        expanded = "".join(
            str(ord(value) - 55) if value.isalpha() else value for value in candidate
        )
        total = sum(
            (int(value) * 2 // 10 + int(value) * 2 % 10) if position % 2 else int(value)
            for position, value in enumerate(reversed(expanded))
        )
        if total % 10 == 0:
            return candidate
    raise AssertionError


def _retain_reliance_universe(
    root: Path, lease: StorageRootLease, catalog: DuckDBCatalog
) -> None:
    observed = datetime(2026, 6, 30, tzinfo=UTC)
    members = [Nifty50ConstituentV1("INE002A01018", "RELIANCE", "ENERGY")] + [
        Nifty50ConstituentV1(_test_isin(index), f"SYM{index:02d}", "FINANCIALS")
        for index in range(49)
    ]
    members.sort(key=lambda member: member.isin)
    Nifty50UniverseStoreV1(root, lease, catalog).retain(
        Nifty50UniverseSnapshotV1(
            1,
            "nifty-50",
            date(2026, 7, 1),
            date(2026, 9, 30),
            "nse-archive",
            "2026-q3",
            observed,
            observed,
            "nse-archive",
            "2026-q3",
            observed,
            observed,
            tuple(members),
        )
    )


def _request(
    root: Path,
    *,
    segment: str = "NSE_EQ",
    symbol: str = "RELIANCE",
    timeframe: str = "1m",
    fields: tuple[str, ...] = ("ts", "open", "close", "volume"),
    max_rows: int = 1_000,
) -> QueryRequestV1:
    return QueryRequestV1(
        segment,
        symbol,
        date(2026, 7, 3),
        date(2026, 7, 3),
        timeframe,
        fields,
        max_rows,
        root,
    )


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
        7,
        date(2026, 7, 1),
        date(2026, 7, 31),
    )


def _selection(row_count: int = 3) -> VerifiedPartitionV1:
    return VerifiedPartitionV1(
        _plan(),
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
        "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
        "year=2026/month=07/bars.parquet",
        "b" * 64,
        row_count,
        datetime(2026, 7, 3, 3, 45, tzinfo=UTC),
        datetime(2026, 7, 3, 3, 45 + row_count - 1, tzinfo=UTC),
        DIGEST,
    )


def _month(
    state: CoverageStateV1 = CoverageStateV1.VERIFIED,
    row_count: int = 3,
) -> PublicCoverageMonthV1:
    verified = state is CoverageStateV1.VERIFIED
    return PublicCoverageMonthV1(
        "2026-07",
        state,
        datetime(2026, 7, 3, 3, 45, tzinfo=UTC) if verified else None,
        datetime(2026, 7, 3, 3, 45 + row_count - 1, tzinfo=UTC) if verified else None,
        row_count if verified else None,
        "b" * 64 if verified else None,
        1 if verified else None,
        f"nse-equity-month@v1+sessions-sha256:{DIGEST}" if verified else None,
        DIGEST if verified else None,
        None,
        ValidationReason.NONE if verified else None,
    )


def _evaluation(
    state: CoverageStateV1 = CoverageStateV1.VERIFIED,
    row_count: int = 3,
) -> CoverageEvaluationV1:
    selections = (_selection(row_count),) if state is CoverageStateV1.VERIFIED else ()
    return CoverageEvaluationV1((_month(state, row_count),), selections)


class _Clock:
    def now(self) -> datetime:
        return NOW


class _NaiveClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 10, 4, 0)


class _Admission:
    def __init__(self) -> None:
        self.live = False

    def __enter__(self) -> _Admission:
        self.live = True
        return self

    def __exit__(self, *_: object) -> None:
        self.live = False

    def ensure_live(self, _root: object) -> None:
        if not self.live:
            raise RuntimeError("not live")


class _Evaluator:
    def __init__(
        self,
        evaluation: CoverageEvaluationV1 | Exception | None = None,
    ) -> None:
        self.evaluation = _evaluation() if evaluation is None else evaluation
        self.admission = _Admission()
        self.calls: list[str] = []

    def admit(self, _root: object) -> _Admission:
        self.calls.append("admit")
        return self.admission

    def evaluate_under_admission(
        self, _request: object, _invocation: object, admission: _Admission
    ) -> CoverageEvaluationV1:
        assert admission.live
        self.calls.append("coverage")
        if isinstance(self.evaluation, Exception):
            raise self.evaluation
        return self.evaluation


class _Engine:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls = 0

    def execute(
        self,
        request: PublicQueryRequestV1,
        root: Path,
        evaluation: CoverageEvaluationV1,
        evaluator: object,
        admission: _Admission,
    ):
        del root, evaluation, evaluator
        assert admission.live
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return (
            query_module.PublicQueryRowV1(
                datetime(2026, 7, 3, 3, 45, tzinfo=UTC),
                100.0 if CandleFieldV1.OPEN in request.fields else None,
                None,
                None,
                100.5 if CandleFieldV1.CLOSE in request.fields else None,
                1_000 if CandleFieldV1.VOLUME in request.fields else None,
            ),
        )


def _service(evaluator: _Evaluator, engine: _Engine) -> OneMinuteQueryServiceV1:
    return OneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        evaluator,  # type: ignore[arg-type]
        engine=engine,  # type: ignore[arg-type]
        clock=_Clock(),
    )


def test_one_minute_query_rejects_invalid_parent_lease() -> None:
    report = _service(_Evaluator(), _Engine()).query_under_lease(
        object(),
        object(),  # type: ignore[arg-type]
    )
    assert report.status is PublicCommandStatusV1.REJECTED


def test_query_service_holds_one_admission_through_materialization(
    tmp_path: Path,
) -> None:
    evaluator = _Evaluator()
    engine = _Engine()

    report = _service(evaluator, engine).query(_request(tmp_path))

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.provider_attempt_count == 0
    assert report.payload is not None
    assert report.payload.row_count == 1
    assert evaluator.calls == ["admit", "coverage"]
    assert engine.calls == 1
    assert not evaluator.admission.live


def test_query_service_admits_product_before_root_or_query_validation(
    tmp_path: Path,
) -> None:
    evaluator = _Evaluator()
    engine = _Engine()
    service = _service(evaluator, engine)

    malformed = service.query(object())
    unsupported = service.query(
        _request(Path("relative"), symbol="TCS", fields=("not-a-field",))
    )
    bad_timeframe = service.query(_request(tmp_path, timeframe="1d"))
    bad_fields = service.query(_request(tmp_path, fields=("open", "ts")))
    bad_rows = service.query(_request(tmp_path, max_rows=10_001))
    unsafe_root = service.query(_request(tmp_path.parent / "~unsafe"))
    too_many_months = service.query(
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2025, 7, 1),
            date(2026, 7, 1),
            "1m",
            ("ts",),
            1,
            tmp_path,
        )
    )

    assert malformed.status is PublicCommandStatusV1.REJECTED
    assert malformed.failure is not None
    assert malformed.failure.code is PublicFailureCodeV1.INVALID_INPUT
    assert unsupported.status is PublicCommandStatusV1.REJECTED
    assert unsupported.failure is not None
    assert (
        unsupported.failure.code is PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT
    )
    assert bad_timeframe.failure is not None
    assert bad_timeframe.failure.code is PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME
    assert bad_fields.failure is not None
    assert bad_fields.failure.code is PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED
    assert bad_rows.failure is not None
    assert bad_rows.failure.code is PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED
    assert unsafe_root.failure is not None
    assert unsafe_root.failure.code is PublicFailureCodeV1.INVALID_INPUT
    assert too_many_months.failure is not None
    assert too_many_months.failure.code is PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED
    assert evaluator.calls == []
    assert engine.calls == 0


def test_query_service_retains_insufficient_evidence_without_opening_rows(
    tmp_path: Path,
) -> None:
    evaluator = _Evaluator(_evaluation(CoverageStateV1.MISSING))
    engine = _Engine()

    report = _service(evaluator, engine).query(_request(tmp_path))

    assert report.status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.COVERAGE_INSUFFICIENT
    assert report.failure.months == ("2026-07",)
    assert report.payload is not None
    assert report.payload.rows == ()
    assert engine.calls == 0


def test_query_service_fails_closed_on_mutated_coverage_evidence(
    tmp_path: Path,
) -> None:
    evaluation = _evaluation()
    object.__setattr__(evaluation, "months", {"credential": "secret-token"})
    evaluator = _Evaluator(evaluation)
    engine = _Engine()

    report = _service(evaluator, engine).query(_request(tmp_path))

    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
    assert report.payload is None
    assert engine.calls == 0


def test_query_service_fails_before_admission_on_invalid_invocation(
    tmp_path: Path,
) -> None:
    evaluator = _Evaluator()
    engine = _Engine()
    service = OneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        evaluator,  # type: ignore[arg-type]
        engine=engine,  # type: ignore[arg-type]
        clock=_NaiveClock(),
    )

    report = service.query(_request(tmp_path))

    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
    assert evaluator.calls == []
    assert engine.calls == 0


def test_query_request_boundary_rejects_non_string_field(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 3),
            date(2026, 7, 3),
            "1m",
            ("ts", object()),  # type: ignore[arg-type]
            1,
            tmp_path,
        )


@pytest.mark.parametrize(
    ("error", "status", "code"),
    (
        (
            CoverageEvaluationFailureV1(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            ),
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
        ),
        (
            QueryResourceLimitV1(),
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED,
        ),
        (
            QueryTimeoutV1(),
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.QUERY_TIMEOUT,
        ),
        (
            QueryExecutionFailureV1(),
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        ),
    ),
)
def test_query_service_maps_sanitized_dependency_failures(
    tmp_path: Path,
    error: Exception,
    status: PublicCommandStatusV1,
    code: PublicFailureCodeV1,
) -> None:
    evaluator = (
        _Evaluator(error)
        if isinstance(error, CoverageEvaluationFailureV1)
        else _Evaluator()
    )
    engine = _Engine(None if isinstance(error, CoverageEvaluationFailureV1) else error)

    report = _service(evaluator, engine).query(_request(tmp_path))

    assert report.status is status
    assert report.failure is not None
    assert report.failure.code is code
    assert report.payload is None


def _candles() -> tuple[CanonicalCandle, ...]:
    return tuple(
        CanonicalCandle(
            "upstox",
            "NSE_EQ|INE002A01018",
            "INE002A01018",
            "RELIANCE",
            "NSE",
            "NSE_EQ",
            "EQ",
            None,
            None,
            None,
            None,
            "1m",
            datetime(2026, 7, 3, 3, 45 + index, tzinfo=UTC),
            100.0 + index,
            101.0 + index,
            99.0 + index,
            100.5 + index,
            1_000 + index,
            None,
            datetime(2026, 8, 1, tzinfo=UTC),
            "upstox-historical-v3",
            "raw",
        )
        for index in range(3)
    )


class _DescriptorEvaluator:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def open_verified_partition_under_admission(
        self,
        _root: Path,
        selection: VerifiedPartitionV1,
        admission: _Admission,
    ):
        assert admission.live
        descriptor = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC)
        try:
            yield VerifiedPartitionReadHandleV1(f"/dev/fd/{descriptor}", selection)
            assert admission.live
        finally:
            os.close(descriptor)


def _public_request(
    max_rows: int = 1_000,
    fields: tuple[CandleFieldV1, ...] = (CandleFieldV1.TS, CandleFieldV1.CLOSE),
) -> PublicQueryRequestV1:
    return PublicQueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 3),
        date(2026, 7, 3),
        "1m",
        fields,
        max_rows,
    )


def test_duckdb_engine_uses_pinned_paths_bounded_config_and_parameters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    evaluator = _DescriptorEvaluator(parquet_path)
    admission = _Admission()
    real_connect = duckdb.connect
    configs: list[dict[str, object]] = []
    statements: list[tuple[str, object]] = []

    class RecordingConnection:
        def __init__(self, config: dict[str, object]) -> None:
            self.connection = real_connect(config=config)

        def execute(self, statement: str, parameters: object):
            statements.append((statement, parameters))
            self.connection.execute(statement, parameters)
            return self

        def fetchall(self):
            return self.connection.fetchall()

        def interrupt(self) -> None:
            self.connection.interrupt()

        def close(self) -> None:
            self.connection.close()

    def connect(*, config: dict[str, object]):
        configs.append(config)
        return RecordingConnection(config)

    monkeypatch.setattr(query_module.duckdb, "connect", connect)
    with admission:
        rows = DuckDBOneMinuteQueryEngineV1().execute(
            _public_request(),
            tmp_path,
            _evaluation(),
            evaluator,  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )

    assert tuple(row.close for row in rows) == (100.5, 101.5, 102.5)
    assert all(row.open is None for row in rows)
    assert configs == [
        {
            "threads": 1,
            "memory_limit": "256MB",
            "max_temp_directory_size": "0B",
            "preserve_insertion_order": False,
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
        }
    ]
    statement, parameters = statements[0]
    assert "read_parquet(?)" in statement
    assert "WHERE epoch_us(ts) >= ? AND epoch_us(ts) < ?" in statement
    assert "ORDER BY ts ASC LIMIT ?" in statement
    assert "RELIANCE" not in statement
    assert type(parameters) is list
    assert parameters[-1] == 1_001


def test_duckdb_engine_rejects_row_overflow_without_truncation(tmp_path: Path) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()

    with admission, pytest.raises(QueryResourceLimitV1):
        DuckDBOneMinuteQueryEngineV1().execute(
            _public_request(max_rows=2),
            tmp_path,
            _evaluation(),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )


def test_duckdb_engine_fails_closed_on_mutated_public_request(tmp_path: Path) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()
    request = _public_request()
    object.__setattr__(request, "fields", ({"credential": "secret-token"},))

    with admission, pytest.raises(QueryExecutionFailureV1):
        DuckDBOneMinuteQueryEngineV1().execute(
            request,
            tmp_path,
            _evaluation(),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )


def test_duckdb_engine_rejects_wrong_request_evaluation_and_empty_selection(
    tmp_path: Path,
) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()
    engine = DuckDBOneMinuteQueryEngineV1()
    evaluator = _DescriptorEvaluator(parquet_path)

    with admission:
        with pytest.raises(QueryExecutionFailureV1):
            engine.execute(
                object(),  # type: ignore[arg-type]
                tmp_path,
                _evaluation(),
                evaluator,  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )
        with pytest.raises(QueryExecutionFailureV1):
            engine.execute(
                _public_request(),
                tmp_path,
                object(),  # type: ignore[arg-type]
                evaluator,  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )
        with pytest.raises(QueryExecutionFailureV1):
            engine.execute(
                _public_request(),
                tmp_path,
                CoverageEvaluationV1((), ()),
                evaluator,  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )


def test_duckdb_engine_returns_empty_success_for_verified_dates_without_bars(
    tmp_path: Path,
) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()
    request = replace(
        _public_request(),
        from_date=date(2026, 7, 4),
        to_date=date(2026, 7, 4),
    )

    with admission:
        rows = DuckDBOneMinuteQueryEngineV1().execute(
            request,
            tmp_path,
            _evaluation(),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )

    assert rows == ()


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        (duckdb.InterruptException("deadline"), QueryTimeoutV1),
        (duckdb.OutOfMemoryException("memory"), QueryResourceLimitV1),
        (duckdb.IOException("read"), QueryExecutionFailureV1),
    ),
)
def test_duckdb_engine_maps_execution_errors_and_closes_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected: type[Exception],
) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()

    class FailingConnection:
        def __init__(self) -> None:
            self.closed = False

        def execute(self, _statement: str, _parameters: object) -> object:
            raise error

        def interrupt(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    connection = FailingConnection()
    monkeypatch.setattr(query_module.duckdb, "connect", lambda **_kwargs: connection)

    with admission, pytest.raises(expected):
        DuckDBOneMinuteQueryEngineV1().execute(
            _public_request(),
            tmp_path,
            _evaluation(),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )

    assert connection.closed


def test_duckdb_engine_maps_connection_open_failure_without_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()

    def fail_connect(**_kwargs: object) -> object:
        raise duckdb.IOException("open")

    monkeypatch.setattr(query_module.duckdb, "connect", fail_connect)

    with admission, pytest.raises(QueryExecutionFailureV1):
        DuckDBOneMinuteQueryEngineV1().execute(
            _public_request(),
            tmp_path,
            _evaluation(),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )


def test_duckdb_engine_fails_when_deadline_fires_even_if_interrupt_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()

    class ReturningConnection:
        def __init__(self) -> None:
            self.closed = False

        def execute(self, _statement: str, _parameters: object) -> ReturningConnection:
            return self

        def fetchall(self) -> list[tuple[int, float]]:
            return [(1_783_050_300_000_000, 100.5)]

        def interrupt(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    class ImmediateTimer:
        def __init__(
            self, _seconds: float, target: object, args: tuple[object, ...]
        ) -> None:
            self.daemon = False
            self._target = target
            self._args = args

        def start(self) -> None:
            assert callable(self._target)
            self._target(*self._args)

        def cancel(self) -> None:
            return None

        def join(self, timeout: float) -> None:
            assert timeout == 1.0

    connection = ReturningConnection()
    monkeypatch.setattr(query_module.duckdb, "connect", lambda **_kwargs: connection)
    monkeypatch.setattr(query_module.threading, "Timer", ImmediateTimer)

    with admission, pytest.raises(QueryTimeoutV1):
        DuckDBOneMinuteQueryEngineV1().execute(
            _public_request(),
            tmp_path,
            _evaluation(),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )

    assert connection.closed


@pytest.mark.parametrize(
    ("raw", "fields"),
    (
        ([1], (CandleFieldV1.TS, CandleFieldV1.CLOSE)),
        ((1,), (CandleFieldV1.TS, CandleFieldV1.CLOSE)),
        (("bad", 100.0), (CandleFieldV1.TS, CandleFieldV1.CLOSE)),
        ((1, 100), (CandleFieldV1.TS, CandleFieldV1.CLOSE)),
        ((1, 1.5), (CandleFieldV1.TS, CandleFieldV1.VOLUME)),
    ),
)
def test_duckdb_engine_fails_closed_on_malformed_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw: object,
    fields: tuple[CandleFieldV1, ...],
) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()

    class MalformedConnection:
        def execute(self, _statement: str, _parameters: object) -> MalformedConnection:
            return self

        def fetchall(self) -> list[object]:
            return [raw]

        def interrupt(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        query_module.duckdb, "connect", lambda **_kwargs: MalformedConnection()
    )

    with admission, pytest.raises(QueryExecutionFailureV1):
        DuckDBOneMinuteQueryEngineV1().execute(
            _public_request(fields=fields),
            tmp_path,
            _evaluation(),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )


def _seed_disposable_query_root(root: Path) -> None:
    instrument = {
        "segment": "NSE_EQ",
        "name": "RELIANCE INDUSTRIES LIMITED",
        "exchange": "NSE",
        "isin": "INE002A01018",
        "instrument_type": "EQ",
        "instrument_key": "NSE_EQ|INE002A01018",
        "trading_symbol": "RELIANCE",
    }
    decompressed = json.dumps([instrument], separators=(",", ":")).encode()
    compressed = gzip.compress(decompressed, mtime=0)
    snapshot = FetchedInstrumentSnapshotV1(
        datetime(2026, 8, 1, 3, 0, tzinfo=UTC),
        date(2026, 8, 1),
        compressed,
        decompressed,
        hashlib.sha256(compressed).hexdigest(),
        hashlib.sha256(decompressed).hexdigest(),
        InstrumentCatalog.from_json_bytes(decompressed),
        None,
        None,
    )
    schedule = ExpectedSessionSchedule(
        2,
        "nse-authoritative-test",
        "release-2026-08-01",
        datetime(2026, 8, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 7, 1),
        date(2026, 7, 31),
        (
            ScheduleSession(
                date(2026, 7, 1),
                datetime(2026, 7, 1, 3, 45, tzinfo=UTC),
                datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
                "regular",
            ),
        ),
        tuple(
            ScheduleClosure(date(2026, 7, 1) + timedelta(days=offset), "closed")
            for offset in range(1, 31)
        ),
    )
    plan = _plan()
    candles = tuple(
        CanonicalCandle(
            candle.provider,
            candle.instrument_key,
            candle.security_id,
            candle.symbol,
            candle.exchange,
            candle.segment,
            candle.instrument_type,
            candle.underlying_id,
            candle.expiry,
            candle.strike,
            candle.option_type,
            candle.interval,
            datetime(2026, 7, 1, 3, 45, tzinfo=UTC) + timedelta(minutes=index),
            100.0,
            101.0,
            99.0,
            100.5,
            1_000 + index,
            candle.oi,
            candle.ingested_at,
            candle.source_version,
            candle.adjustment_state,
        )
        for index, candle in enumerate((_candles()[0],) * 375)
    )
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(root) as catalog:
        _retain_reliance_universe(root, acquired.lease, catalog)
        InstrumentSnapshotStoreV1(root, acquired.lease, catalog).retain(snapshot)
        retained = ScheduleEvidenceStore(root, acquired.lease).retain(schedule)
        assert retained.digest is not None
        published = publish_partition(root, plan, candles)
        started = datetime(2026, 8, 2, tzinfo=UTC)
        active = PartitionManifest(
            1,
            plan,
            "query-smoke",
            None,
            ManifestState.IN_PROGRESS,
            ValidationOutcome.NOT_RUN,
            "nse-equity-month@v1+sessions-sha256:" + retained.digest,
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
        catalog.create_manifest(active)
        catalog.transition_manifest(
            active,
            verify_manifest(
                active,
                started,
                published.actual_from_ts,
                published.actual_to_ts,
                published.row_count,
                published.checksum_sha256,
                published.canonical_path,
            ),
        )


def _root_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def test_disposable_root_query_cli_is_provider_free_and_read_only(
    tmp_path: Path, capsys
) -> None:
    _seed_disposable_query_root(tmp_path)
    before = _root_bytes(tmp_path)

    exit_code = main(
        [
            "query",
            "--segment",
            "NSE_EQ",
            "--symbol",
            "RELIANCE",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-01",
            "--timeframe",
            "1m",
            "--fields",
            "ts,close,volume",
            "--max-rows",
            "1000",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )

    decoded = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert decoded["provider_attempt_count"] == 0
    assert decoded["payload"]["row_count"] == 375
    assert decoded["payload"]["rows"][0] == {
        "ts": "2026-07-01T03:45:00.000000Z",
        "close": 100.5,
        "volume": 1_000,
    }
    assert decoded["payload"]["rows"][-1]["ts"] == ("2026-07-01T09:59:00.000000Z")
    assert _root_bytes(tmp_path) == before
