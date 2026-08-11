from __future__ import annotations

import gzip
import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import swing_trading_ai_assistant.market_data.daily_ohlcv as daily_module
import swing_trading_ai_assistant.market_data.public_contract as contract_module
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.daily_ohlcv import (
    DAILY_CALCULATION_VERSION_V1,
    MAX_DAILY_QUERY_ROWS_V1,
    DailyQueryServiceV1,
    DailyScheduleResolutionV1,
    DuckDBDailyOHLCVEngineV1,
    TimeframeQueryServiceV1,
    VerifiedClosureV1,
    VerifiedSessionV1,
)
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
    DailyQueryPayloadV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicCoverageMonthV1,
    PublicFailureCodeV1,
    PublicQueryRequestV1,
    QueryReportV1,
    render_query_report_json,
)
from swing_trading_ai_assistant.market_data.public_coverage import (
    CoverageEvaluationV1,
    ExistingCoverageAdmissionV1,
    VerifiedPartitionReadHandleV1,
    VerifiedPartitionV1,
)
from swing_trading_ai_assistant.market_data.public_query import (
    QueryExecutionFailureV1,
    QueryRequestV1,
    QueryResourceLimitV1,
    QueryTimeoutV1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    ScheduleSession,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_data.validation import ValidationReason

NOW = datetime(2026, 8, 10, 4, 0, tzinfo=UTC)
DIGEST = "a" * 64


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


def _month(state: CoverageStateV1 = CoverageStateV1.VERIFIED) -> PublicCoverageMonthV1:
    verified = state is CoverageStateV1.VERIFIED
    return PublicCoverageMonthV1(
        "2026-07",
        state,
        datetime(2026, 7, 3, 3, 45, tzinfo=UTC) if verified else None,
        datetime(2026, 7, 3, 3, 47, tzinfo=UTC) if verified else None,
        3 if verified else None,
        "b" * 64 if verified else None,
        1 if verified else None,
        f"nse-equity-month@v1+sessions-sha256:{DIGEST}" if verified else None,
        DIGEST if verified else None,
        None,
        ValidationReason.NONE if verified else None,
    )


def _selection() -> VerifiedPartitionV1:
    return VerifiedPartitionV1(
        _plan(),
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
        "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
        "year=2026/month=07/bars.parquet",
        "b" * 64,
        3,
        datetime(2026, 7, 3, 3, 45, tzinfo=UTC),
        datetime(2026, 7, 3, 3, 47, tzinfo=UTC),
        DIGEST,
    )


def _evaluation(
    state: CoverageStateV1 = CoverageStateV1.VERIFIED,
) -> CoverageEvaluationV1:
    return CoverageEvaluationV1(
        (_month(state),),
        (_selection(),) if state is CoverageStateV1.VERIFIED else (),
    )


def _raw_request(
    root: Path,
    *,
    timeframe: str = "1d",
    fields: tuple[str, ...] = ("ts", "open", "high", "low", "close", "volume"),
    max_rows: int = 31,
    to_date: date = date(2026, 7, 3),
) -> QueryRequestV1:
    return QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 3),
        to_date,
        timeframe,
        fields,
        max_rows,
        root,
    )


def _public_request(
    *,
    fields: tuple[CandleFieldV1, ...] = tuple(CandleFieldV1),
    max_rows: int = 31,
) -> PublicQueryRequestV1:
    return PublicQueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 3),
        date(2026, 7, 3),
        "1d",
        fields,
        max_rows,
    )


def _session() -> VerifiedSessionV1:
    return VerifiedSessionV1(
        date(2026, 7, 3),
        datetime(2026, 7, 3, 3, 45, tzinfo=UTC),
        datetime(2026, 7, 3, 3, 48, tzinfo=UTC),
        DIGEST,
    )


class _Clock:
    def now(self) -> datetime:
        return NOW


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
    def __init__(self, evaluation: CoverageEvaluationV1 | None = None) -> None:
        self.evaluation = evaluation or _evaluation()
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
        return self.evaluation


class _Resolver:
    def __init__(
        self,
        sessions: tuple[VerifiedSessionV1, ...] = (_session(),),
        *,
        complete: bool = True,
    ) -> None:
        self.sessions = sessions
        self.complete = complete
        self.calls = 0

    def resolve(
        self,
        _request: object,
        _root: Path,
        _evaluation: CoverageEvaluationV1,
        _invocation: datetime,
        admission: _Admission,
    ) -> DailyScheduleResolutionV1:
        assert admission.live
        self.calls += 1
        assert type(_request) is PublicQueryRequestV1
        session_dates = {value.trade_date for value in self.sessions}
        closures = (
            tuple(
                VerifiedClosureV1(current, DIGEST)
                for offset in range((_request.to_date - _request.from_date).days + 1)
                if (current := _request.from_date + timedelta(days=offset))
                not in session_dates
            )
            if self.complete
            else ()
        )
        return DailyScheduleResolutionV1(self.sessions, closures)


class _Engine:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def execute(
        self,
        request: PublicQueryRequestV1,
        _root: Path,
        _evaluation: CoverageEvaluationV1,
        sessions: tuple[VerifiedSessionV1, ...],
        _evaluator: object,
        admission: _Admission,
    ):
        assert admission.live
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert sessions == (_session(),)
        return (
            daily_module.PublicQueryRowV1(
                sessions[0].open_at,
                100.0 if CandleFieldV1.OPEN in request.fields else None,
                103.0 if CandleFieldV1.HIGH in request.fields else None,
                98.0 if CandleFieldV1.LOW in request.fields else None,
                102.5 if CandleFieldV1.CLOSE in request.fields else None,
                3_003 if CandleFieldV1.VOLUME in request.fields else None,
            ),
        )


def _service(
    evaluator: _Evaluator, resolver: _Resolver, engine: _Engine
) -> DailyQueryServiceV1:
    return DailyQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        evaluator,  # type: ignore[arg-type]
        resolver=resolver,  # type: ignore[arg-type]
        engine=engine,  # type: ignore[arg-type]
        clock=_Clock(),
    )


@pytest.mark.parametrize(
    "overrides",
    (
        {"trade_date": datetime(2026, 7, 3, tzinfo=UTC)},
        {"open_at": datetime(2026, 7, 3, 3, 45)},
        {"close_at": datetime(2026, 7, 3, 3, 45, tzinfo=UTC)},
        {"trade_date": date(2026, 7, 4)},
        {"close_at": datetime(2026, 7, 3, 19, 0, tzinfo=UTC)},
        {"schedule_digest_sha256": "A" * 64},
        {"schedule_digest_sha256": "a" * 63},
        {"close_at": datetime(2026, 7, 3, 13, 46, tzinfo=UTC)},
    ),
)
def test_verified_session_rejects_invalid_identity_time_and_bounds(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        replace(_session(), **overrides)


def test_daily_schedule_resolution_rejects_invalid_closures_shapes_and_overlap() -> (
    None
):
    with pytest.raises(ValueError):
        VerifiedClosureV1(datetime(2026, 7, 3, tzinfo=UTC), DIGEST)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        DailyScheduleResolutionV1((object(),), ())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        DailyScheduleResolutionV1(
            (_session(),), (VerifiedClosureV1(date(2026, 7, 3), DIGEST),)
        )


def test_daily_resolution_validation_rejects_wrong_type_and_unbound_closure() -> None:
    with pytest.raises(QueryExecutionFailureV1):
        daily_module._validated_resolution(_public_request(), _evaluation(), object())
    unbound = DailyScheduleResolutionV1(
        (), (VerifiedClosureV1(date(2026, 7, 3), "b" * 64),)
    )
    with pytest.raises(QueryExecutionFailureV1):
        daily_module._validated_resolution(_public_request(), _evaluation(), unbound)


def test_daily_service_uses_one_live_admission_and_zero_provider_attempts(
    tmp_path: Path,
) -> None:
    evaluator = _Evaluator()
    resolver = _Resolver()
    engine = _Engine()

    report = _service(evaluator, resolver, engine).query(_raw_request(tmp_path))

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.provider_attempt_count == 0
    assert type(report.payload) is DailyQueryPayloadV1
    assert report.payload.calculation_version == DAILY_CALCULATION_VERSION_V1
    assert report.payload.adjustment_state == "raw"
    assert report.payload.row_count == 1
    assert evaluator.calls == ["admit", "coverage"]
    assert resolver.calls == 1
    assert engine.calls == 1
    assert not evaluator.admission.live


def test_daily_service_preserves_incomplete_coverage_without_derivation(
    tmp_path: Path,
) -> None:
    evaluator = _Evaluator(_evaluation(CoverageStateV1.MISSING))
    resolver = _Resolver()
    engine = _Engine()

    report = _service(evaluator, resolver, engine).query(_raw_request(tmp_path))

    assert report.status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.COVERAGE_INSUFFICIENT
    assert type(report.payload) is DailyQueryPayloadV1
    assert report.payload.rows == ()
    assert resolver.calls == 0
    assert engine.calls == 0


def test_daily_service_rejects_invalid_input_product_root_and_fields_before_admission(
    tmp_path: Path,
) -> None:
    evaluator = _Evaluator()
    service = _service(evaluator, _Resolver(), _Engine())
    cases = (
        (object(), PublicFailureCodeV1.INVALID_INPUT),
        (
            replace(_raw_request(tmp_path), symbol="TCS"),
            PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
        ),
        (
            replace(_raw_request(tmp_path), storage_root=Path("relative")),
            PublicFailureCodeV1.INVALID_INPUT,
        ),
        (
            replace(_raw_request(tmp_path), fields=("close", "ts")),
            PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED,
        ),
    )

    for request, code in cases:
        report = service.query(request)
        assert report.status is PublicCommandStatusV1.REJECTED
        assert report.failure is not None
        assert report.failure.code is code

    assert evaluator.calls == []


def test_daily_service_fails_closed_on_invalid_clock(tmp_path: Path) -> None:
    class InvalidClock:
        def now(self) -> object:
            return object()

    evaluator = _Evaluator()
    service = DailyQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        evaluator,  # type: ignore[arg-type]
        resolver=_Resolver(),  # type: ignore[arg-type]
        engine=_Engine(),  # type: ignore[arg-type]
        clock=InvalidClock(),  # type: ignore[arg-type]
    )

    report = service.query(_raw_request(tmp_path))

    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
    assert evaluator.calls == []


@pytest.mark.parametrize(
    ("timeframe", "max_rows", "code"),
    (
        ("1m", 31, PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME),
        ("1d", 0, PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED),
        ("1d", MAX_DAILY_QUERY_ROWS_V1 + 1, PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED),
    ),
)
def test_daily_service_rejects_wrong_timeframe_and_bounds_before_root(
    tmp_path: Path,
    timeframe: str,
    max_rows: int,
    code: PublicFailureCodeV1,
) -> None:
    evaluator = _Evaluator()
    resolver = _Resolver()
    engine = _Engine()

    report = _service(evaluator, resolver, engine).query(
        _raw_request(tmp_path, timeframe=timeframe, max_rows=max_rows)
    )

    assert report.status is PublicCommandStatusV1.REJECTED
    assert report.failure is not None
    assert report.failure.code is code
    assert evaluator.calls == []
    assert resolver.calls == 0
    assert engine.calls == 0


def test_daily_service_rejects_output_session_count_without_truncation(
    tmp_path: Path,
) -> None:
    sessions = (
        _session(),
        VerifiedSessionV1(
            date(2026, 7, 4),
            datetime(2026, 7, 4, 3, 45, tzinfo=UTC),
            datetime(2026, 7, 4, 3, 48, tzinfo=UTC),
            DIGEST,
        ),
    )
    report = _service(_Evaluator(), _Resolver(sessions), _Engine()).query(
        _raw_request(tmp_path, max_rows=1, to_date=date(2026, 7, 4))
    )

    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED
    assert report.payload is None


def test_daily_service_fails_closed_when_resolver_omits_requested_trade_date(
    tmp_path: Path,
) -> None:
    report = _service(
        _Evaluator(), _Resolver((_session(),), complete=False), _Engine()
    ).query(_raw_request(tmp_path, max_rows=2, to_date=date(2026, 7, 4)))

    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
    assert report.payload is None


def test_daily_service_returns_zero_rows_for_authoritative_closure_only_range(
    tmp_path: Path,
) -> None:
    engine = _Engine()

    report = _service(_Evaluator(), _Resolver(()), engine).query(_raw_request(tmp_path))

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.failure is None
    assert type(report.payload) is DailyQueryPayloadV1
    assert report.payload.rows == ()
    assert engine.calls == 0


@pytest.mark.parametrize("case", ("zero", "extra", "shifted", "reordered"))
def test_daily_service_rejects_rows_not_exactly_bound_to_authoritative_sessions(
    tmp_path: Path, case: str
) -> None:
    second = VerifiedSessionV1(
        date(2026, 7, 4),
        datetime(2026, 7, 4, 3, 45, tzinfo=UTC),
        datetime(2026, 7, 4, 3, 48, tzinfo=UTC),
        DIGEST,
    )
    sessions = (_session(), second) if case == "reordered" else (_session(),)

    def row(
        value: VerifiedSessionV1, *, shift: int = 0
    ) -> daily_module.PublicQueryRowV1:
        return daily_module.PublicQueryRowV1(
            value.open_at + timedelta(minutes=shift),
            100.0,
            103.0,
            98.0,
            102.5,
            3_003,
        )

    rows = {
        "zero": (),
        "extra": (row(_session()), row(_session(), shift=1)),
        "shifted": (row(_session(), shift=1),),
        "reordered": (row(second), row(_session())),
    }[case]

    class StaticEngine:
        def execute(self, *_args: object) -> tuple[daily_module.PublicQueryRowV1, ...]:
            return rows

    report = DailyQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        _Evaluator(),  # type: ignore[arg-type]
        resolver=_Resolver(sessions),  # type: ignore[arg-type]
        engine=StaticEngine(),  # type: ignore[arg-type]
        clock=_Clock(),
    ).query(
        _raw_request(
            tmp_path,
            max_rows=2,
            to_date=date(2026, 7, 4) if case == "reordered" else date(2026, 7, 3),
        )
    )

    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
    assert report.payload is None


@pytest.mark.parametrize(
    ("error", "code"),
    (
        (
            QueryResourceLimitV1(),
            PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED,
        ),
        (QueryTimeoutV1(), PublicFailureCodeV1.QUERY_TIMEOUT),
        (QueryExecutionFailureV1(), PublicFailureCodeV1.UNCLASSIFIED_FAILURE),
    ),
)
def test_daily_service_maps_bounded_engine_failures_and_releases_admission(
    tmp_path: Path, error: Exception, code: PublicFailureCodeV1
) -> None:
    evaluator = _Evaluator()

    report = _service(evaluator, _Resolver(), _Engine(error)).query(
        _raw_request(tmp_path)
    )

    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is code
    assert report.payload is None
    assert not evaluator.admission.live


def test_timeframe_router_invokes_exactly_one_service(tmp_path: Path) -> None:
    class Port:
        def __init__(self, label: str) -> None:
            self.label = label
            self.calls = 0

        def query(self, request: object) -> str:
            self.calls += 1
            return self.label

    minute = Port("minute")
    daily = Port("daily")
    router = TimeframeQueryServiceV1(minute, daily)  # type: ignore[arg-type]

    assert router.query(_raw_request(tmp_path, timeframe="1m")) == "minute"
    assert router.query(_raw_request(tmp_path, timeframe="1d")) == "daily"
    assert minute.calls == 1
    assert daily.calls == 1

    assert router.query(object()) == "minute"
    assert minute.calls == 2
    assert daily.calls == 1


def _candles() -> tuple[CanonicalCandle, ...]:
    values = (
        (100.0, 101.0, 99.0, 100.5, 1_000),
        (100.5, 103.0, 98.0, 101.5, 1_001),
        (101.5, 103.0, 100.0, 102.5, 1_002),
    )
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
            open_value,
            high,
            low,
            close,
            volume,
            None,
            datetime(2026, 8, 1, tzinfo=UTC),
            "upstox-historical-v3",
            "raw",
        )
        for index, (open_value, high, low, close, volume) in enumerate(values)
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


def test_daily_duckdb_engine_aggregates_authoritative_session_ohlcv(
    tmp_path: Path,
) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()

    with admission:
        rows = DuckDBDailyOHLCVEngineV1().execute(
            _public_request(),
            tmp_path,
            _evaluation(),
            (_session(),),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )

    assert len(rows) == 1
    assert rows[0].ts == _session().open_at
    assert (rows[0].open, rows[0].high, rows[0].low, rows[0].close) == (
        100.0,
        103.0,
        98.0,
        102.5,
    )
    assert rows[0].volume == 3_003


def test_daily_duckdb_engine_uses_special_session_utc_bounds_and_ist_trade_date(
    tmp_path: Path,
) -> None:
    special = VerifiedSessionV1(
        date(2026, 7, 3),
        datetime(2026, 7, 3, 7, 0, tzinfo=UTC),
        datetime(2026, 7, 3, 7, 2, tzinfo=UTC),
        DIGEST,
    )
    candles = tuple(
        replace(candle, ts=special.open_at + timedelta(minutes=index))
        for index, candle in enumerate(_candles()[:2])
    )
    parquet_path = tmp_path / "special-bars.parquet"
    write_candles_parquet(parquet_path, candles)
    admission = _Admission()

    with admission:
        rows = DuckDBDailyOHLCVEngineV1().execute(
            _public_request(),
            tmp_path,
            _evaluation(),
            (special,),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )

    assert len(rows) == 1
    assert rows[0].ts == datetime(2026, 7, 3, 7, 0, tzinfo=UTC)
    assert rows[0].ts.astimezone(
        timezone(timedelta(hours=5, minutes=30))
    ).date() == date(2026, 7, 3)
    assert (rows[0].open, rows[0].high, rows[0].low, rows[0].close) == (
        100.0,
        103.0,
        98.0,
        101.5,
    )
    assert rows[0].volume == 2_001


def test_daily_duckdb_engine_rejects_off_grid_replacement_minute(
    tmp_path: Path,
) -> None:
    parquet_path = tmp_path / "off-grid.parquet"
    write_candles_parquet(parquet_path, _candles())
    table = pq.read_table(parquet_path)
    timestamps = table.column("ts").to_pylist()
    timestamps[1] += timedelta(seconds=30)
    table = table.set_column(
        table.schema.get_field_index("ts"),
        "ts",
        pa.array(timestamps, type=table.schema.field("ts").type),
    )
    pq.write_table(table, parquet_path)
    admission = _Admission()

    with admission, pytest.raises(QueryExecutionFailureV1):
        DuckDBDailyOHLCVEngineV1().execute(
            _public_request(),
            tmp_path,
            _evaluation(),
            (_session(),),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )


def test_daily_engine_rejects_untyped_arbitrary_partition_handle(
    tmp_path: Path,
) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()

    class ArbitraryEvaluator:
        @contextmanager
        def open_verified_partition_under_admission(self, *_args: object):
            yield SimpleNamespace(duckdb_path=str(parquet_path), selection=object())

    with admission, pytest.raises(QueryExecutionFailureV1):
        DuckDBDailyOHLCVEngineV1().execute(
            _public_request(),
            tmp_path,
            _evaluation(),
            (_session(),),
            ArbitraryEvaluator(),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )


def test_daily_partition_handle_validation_rejects_path_identity_and_order_mutation(
    tmp_path: Path,
) -> None:
    first = _selection()
    august_plan = replace(
        _plan(),
        year=2026,
        month=8,
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31),
    )
    second = replace(
        first,
        plan=august_plan,
        canonical_path=first.canonical_path.replace(
            "year=2026/month=07", "year=2026/month=08"
        ),
        actual_from_ts=datetime(2026, 8, 3, 3, 45, tzinfo=UTC),
        actual_to_ts=datetime(2026, 8, 3, 3, 47, tzinfo=UTC),
    )
    first_handle = VerifiedPartitionReadHandleV1("/dev/fd/10", first)
    second_handle = VerifiedPartitionReadHandleV1("/dev/fd/11", second)

    with pytest.raises(QueryExecutionFailureV1):
        daily_module._validated_partition_handles(object(), (first,))
    with pytest.raises(QueryExecutionFailureV1):
        daily_module._validated_partition_handles((object(),), (first,))
    with pytest.raises(QueryExecutionFailureV1):
        daily_module._validated_partition_handles((second_handle,), (first,))
    with pytest.raises(QueryExecutionFailureV1):
        daily_module._validated_partition_handles(
            (second_handle, first_handle), (first, second)
        )

    object.__setattr__(first_handle, "duckdb_path", str(tmp_path / "arbitrary.parquet"))
    with pytest.raises(QueryExecutionFailureV1):
        daily_module._validated_partition_handles((first_handle,), (first,))


@pytest.mark.parametrize("value", ([], (object(),)))
def test_daily_output_row_validation_rejects_wrong_container_and_row_type(
    value: object,
) -> None:
    with pytest.raises(QueryExecutionFailureV1):
        daily_module._validated_daily_rows(_public_request(), (_session(),), value)


def test_retained_daily_schedule_resolver_rejects_unbound_dependency_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule = ExpectedSessionSchedule(
        2,
        "nse-authoritative-test",
        "release-2026-08-01",
        datetime(2026, 8, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 7, 3),
        date(2026, 7, 3),
        (
            ScheduleSession(
                date(2026, 7, 3),
                _session().open_at,
                _session().close_at,
                "special-test",
            ),
        ),
        (),
    )

    class FakeStore:
        def __init__(self, _root: Path, _lease: object) -> None:
            return None

        def resolve(self, _digest: str) -> object:
            return SimpleNamespace(
                outcome=ScheduleOutcome.RESOLVED,
                schedule=schedule,
                digest=DIGEST,
                canonical_bytes=b"not-bound-to-digest",
            )

    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    acquired.lease.close()
    monkeypatch.setattr(daily_module, "ScheduleEvidenceStore", FakeStore)

    with (
        ExistingCoverageAdmissionV1.acquire(tmp_path) as admission,
        pytest.raises(QueryExecutionFailureV1),
    ):
        daily_module.RetainedDailyScheduleResolverV1().resolve(
            _public_request(), tmp_path, _evaluation(), NOW, admission
        )


def test_retained_daily_schedule_resolver_rejects_wrong_admission_and_missing_object(
    tmp_path: Path,
) -> None:
    resolver = daily_module.RetainedDailyScheduleResolverV1()

    with pytest.raises(QueryExecutionFailureV1):
        resolver.resolve(  # type: ignore[arg-type]
            _public_request(), tmp_path, _evaluation(), NOW, object()
        )

    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    acquired.lease.close()
    with (
        ExistingCoverageAdmissionV1.acquire(tmp_path) as admission,
        pytest.raises(QueryExecutionFailureV1),
    ):
        resolver.resolve(_public_request(), tmp_path, _evaluation(), NOW, admission)


def test_daily_duckdb_engine_rejects_incomplete_duplicate_and_volume_overflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()
    engine = DuckDBDailyOHLCVEngineV1()

    class ResultConnection:
        def __init__(self, row: tuple[object, ...]) -> None:
            self.row = row

        def execute(self, _statement: str, _parameters: object) -> ResultConnection:
            return self

        def fetchall(self) -> list[tuple[object, ...]]:
            return [self.row]

        def interrupt(self) -> None:
            return None

        def close(self) -> None:
            return None

    valid_prefix = (
        1_783_050_300_000_000,
        1_783_050_480_000_000,
        100.0,
        103.0,
        98.0,
        102.5,
    )
    invalid_rows = (
        valid_prefix + (3_003, 2, 2, 1_783_050_300_000_000, 1_783_050_420_000_000, 0),
        valid_prefix + (3_003, 4, 3, 1_783_050_300_000_000, 1_783_050_420_000_000, 0),
        valid_prefix + (2**63, 3, 3, 1_783_050_300_000_000, 1_783_050_420_000_000, 0),
    )

    for raw in invalid_rows:
        monkeypatch.setattr(
            daily_module.duckdb,
            "connect",
            lambda raw=raw, **_kwargs: ResultConnection(raw),
        )
        expected = QueryResourceLimitV1 if raw[6] == 2**63 else QueryExecutionFailureV1
        with admission, pytest.raises(expected):
            engine.execute(
                _public_request(),
                tmp_path,
                _evaluation(),
                (_session(),),
                _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )


def test_daily_engine_fails_closed_on_invalid_boundaries_and_open_failure(
    tmp_path: Path,
) -> None:
    engine = DuckDBDailyOHLCVEngineV1()
    admission = _Admission()

    class FailingEvaluator:
        @contextmanager
        def open_verified_partition_under_admission(self, *_args: object):
            raise RuntimeError("sanitized test failure")
            yield

    with admission:
        with pytest.raises(QueryExecutionFailureV1):
            engine.execute(  # type: ignore[arg-type]
                object(),
                tmp_path,
                _evaluation(),
                (_session(),),
                _DescriptorEvaluator(tmp_path),  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )
        with pytest.raises(QueryExecutionFailureV1):
            engine.execute(
                replace(_public_request(), timeframe="1m"),
                tmp_path,
                _evaluation(),
                (_session(),),
                _DescriptorEvaluator(tmp_path),  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )
        assert (
            engine.execute(
                _public_request(),
                tmp_path,
                _evaluation(),
                (),
                _DescriptorEvaluator(tmp_path),  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )
            == ()
        )
        with pytest.raises(QueryExecutionFailureV1):
            engine.execute(
                _public_request(),
                tmp_path,
                _evaluation(),
                (_session(),),
                FailingEvaluator(),  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ((), QueryExecutionFailureV1),
        ([], QueryExecutionFailureV1),
        ([[]], QueryExecutionFailureV1),
        ([()], QueryExecutionFailureV1),
        ([(1,)], QueryExecutionFailureV1),
        (
            [
                (
                    1_783_050_300_000_000,
                    1_783_050_480_000_000,
                    100.0,
                    103.0,
                    101.0,
                    99.0,
                    3_003,
                    3,
                    3,
                    1_783_050_300_000_000,
                    1_783_050_420_000_000,
                    0,
                )
            ],
            QueryExecutionFailureV1,
        ),
        (
            [
                (
                    1_783_050_300_000_000,
                    1_783_050_480_000_000,
                    100.0,
                    103.0,
                    98.0,
                    102.5,
                    -1,
                    3,
                    3,
                    1_783_050_300_000_000,
                    1_783_050_420_000_000,
                    0,
                )
            ],
            QueryResourceLimitV1,
        ),
    ),
)
def test_daily_row_materialization_fails_closed_on_malformed_shapes_and_values(
    raw: object, expected: type[Exception]
) -> None:
    with pytest.raises(expected):
        daily_module._daily_rows(_public_request(), (_session(),), raw)


@pytest.mark.parametrize(
    "value",
    (
        object(),
        (object(),),
        (
            VerifiedSessionV1(
                date(2026, 7, 3),
                datetime(2026, 7, 3, 3, 45, tzinfo=UTC),
                datetime(2026, 7, 3, 3, 48, tzinfo=UTC),
                "b" * 64,
            ),
        ),
        (
            VerifiedSessionV1(
                date(2026, 7, 4),
                datetime(2026, 7, 4, 3, 45, tzinfo=UTC),
                datetime(2026, 7, 4, 3, 48, tzinfo=UTC),
                DIGEST,
            ),
            _session(),
        ),
    ),
)
def test_daily_session_validation_rejects_malformed_unbound_and_unordered_values(
    value: object,
) -> None:
    with pytest.raises(QueryExecutionFailureV1):
        daily_module._validated_sessions(_public_request(), _evaluation(), value)


def test_daily_evaluation_validation_rejects_wrong_and_mutated_values() -> None:
    with pytest.raises(QueryExecutionFailureV1):
        daily_module._validated_evaluation(object())

    evaluation = _evaluation()
    object.__setattr__(evaluation, "verified_partitions", ())
    with pytest.raises(QueryExecutionFailureV1):
        daily_module._validated_evaluation(evaluation)


def test_daily_duckdb_engine_interrupts_at_deadline_and_closes_connection(
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

        def fetchall(self) -> list[tuple[object, ...]]:
            return [
                (
                    1_783_050_300_000_000,
                    1_783_050_480_000_000,
                    100.0,
                    103.0,
                    98.0,
                    102.5,
                    3_003,
                    3,
                    3,
                    1_783_050_300_000_000,
                    1_783_050_420_000_000,
                    0,
                )
            ]

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
    monkeypatch.setattr(daily_module.duckdb, "connect", lambda **_kwargs: connection)
    monkeypatch.setattr(daily_module.threading, "Timer", ImmediateTimer)

    with admission, pytest.raises(QueryTimeoutV1):
        DuckDBDailyOHLCVEngineV1().execute(
            _public_request(),
            tmp_path,
            _evaluation(),
            (_session(),),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )

    assert connection.closed


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        (daily_module.duckdb.InterruptException("interrupted"), QueryTimeoutV1),
        (
            daily_module.duckdb.OutOfMemoryException("bounded memory"),
            QueryResourceLimitV1,
        ),
        (RuntimeError("sanitized test failure"), QueryExecutionFailureV1),
    ),
)
def test_daily_duckdb_engine_maps_database_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected: type[Exception],
) -> None:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, _candles())
    admission = _Admission()

    def fail_connect(**_kwargs: object) -> object:
        raise error

    monkeypatch.setattr(daily_module.duckdb, "connect", fail_connect)

    with admission, pytest.raises(expected):
        DuckDBDailyOHLCVEngineV1().execute(
            _public_request(),
            tmp_path,
            _evaluation(),
            (_session(),),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )


def test_daily_payload_and_json_freeze_provenance_and_requested_fields() -> None:
    request = _public_request(
        fields=(CandleFieldV1.TS, CandleFieldV1.CLOSE, CandleFieldV1.VOLUME)
    )
    row = daily_module.PublicQueryRowV1(
        _session().open_at, None, None, None, 102.5, 3_003
    )
    payload = DailyQueryPayloadV1(
        request,
        DAILY_CALCULATION_VERSION_V1,
        "raw",
        1,
        (_month(),),
        (row,),
    )
    report: QueryReportV1 = PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )

    decoded = json.loads(render_query_report_json(report))

    assert list(decoded["payload"]) == [
        "request",
        "calculation_version",
        "adjustment_state",
        "row_count",
        "months",
        "rows",
    ]
    assert decoded["payload"]["calculation_version"] == DAILY_CALCULATION_VERSION_V1
    assert decoded["payload"]["adjustment_state"] == "raw"
    assert decoded["payload"]["rows"] == [
        {
            "ts": "2026-07-03T03:45:00.000000Z",
            "close": 102.5,
            "volume": 3_003,
        }
    ]


def test_daily_payload_rejects_wrong_timeframe_duplicate_date_and_provenance() -> None:
    request = _public_request(fields=(CandleFieldV1.TS, CandleFieldV1.CLOSE))
    row = daily_module.PublicQueryRowV1(
        _session().open_at, None, None, None, 102.5, None
    )
    payload = DailyQueryPayloadV1(
        request,
        DAILY_CALCULATION_VERSION_V1,
        "raw",
        1,
        (_month(),),
        (row,),
    )

    with pytest.raises(ValueError):
        replace(payload, calculation_version="future")
    with pytest.raises(ValueError):
        replace(payload, adjustment_state="adjusted")
    with pytest.raises(ValueError):
        replace(payload, rows=(row, row), row_count=2)
    with pytest.raises(ValueError):
        replace(payload, request=replace(request, timeframe="1m"))

    object.__setattr__(payload, "request", object())
    with pytest.raises(ValueError):
        replace(payload)


def test_query_contract_helpers_fail_closed_on_unknown_payload_type() -> None:
    assert not contract_module._valid_query_report(
        PublicCommandStatusV1.SUCCEEDED, None, object()
    )
    unknown = SimpleNamespace(
        request=_public_request(), row_count=0, months=(_month(),), rows=()
    )
    with pytest.raises(ValueError):
        contract_module._query_payload_value(unknown)  # type: ignore[arg-type]


def test_daily_renderer_recursively_rejects_mutated_request_without_leakage() -> None:
    request = _public_request(fields=(CandleFieldV1.TS, CandleFieldV1.CLOSE))
    row = daily_module.PublicQueryRowV1(
        _session().open_at, None, None, None, 102.5, None
    )
    payload = DailyQueryPayloadV1(
        request,
        DAILY_CALCULATION_VERSION_V1,
        "raw",
        1,
        (_month(),),
        (row,),
    )
    report: QueryReportV1 = PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )
    object.__setattr__(request, "segment", {"credential": "secret-token"})

    encoded = render_query_report_json(report)
    decoded = json.loads(encoded)

    assert decoded["status"] == "FAILED"
    assert decoded["failure"]["code"] == "UNCLASSIFIED_FAILURE"
    assert b"secret-token" not in encoded


def _seed_disposable_daily_root(root: Path) -> None:
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
                date(2026, 7, 3),
                _session().open_at,
                _session().close_at,
                "special-test",
            ),
        ),
        tuple(
            ScheduleClosure(current, "closed")
            for offset in range(31)
            if (current := date(2026, 7, 1) + timedelta(days=offset))
            != date(2026, 7, 3)
        ),
    )
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(root) as catalog:
        InstrumentSnapshotStoreV1(root, acquired.lease, catalog).retain(snapshot)
        retained = ScheduleEvidenceStore(root, acquired.lease).retain(schedule)
        assert retained.digest is not None
        published = publish_partition(root, _plan(), _candles())
        started = datetime(2026, 8, 2, tzinfo=UTC)
        active = PartitionManifest(
            1,
            _plan(),
            "daily-query-smoke",
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


def test_disposable_root_daily_cli_is_provider_free_read_only_and_provenanced(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_disposable_daily_root(tmp_path)
    before = _root_bytes(tmp_path)

    exit_code = main(
        [
            "query",
            "--segment",
            "NSE_EQ",
            "--symbol",
            "RELIANCE",
            "--from",
            "2026-07-03",
            "--to",
            "2026-07-03",
            "--timeframe",
            "1d",
            "--fields",
            "ts,open,high,low,close,volume",
            "--max-rows",
            "31",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )

    decoded = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert decoded["provider_attempt_count"] == 0
    assert decoded["payload"]["calculation_version"] == DAILY_CALCULATION_VERSION_V1
    assert decoded["payload"]["adjustment_state"] == "raw"
    assert decoded["payload"]["row_count"] == 1
    assert decoded["payload"]["rows"] == [
        {
            "ts": "2026-07-03T03:45:00.000000Z",
            "open": 100.0,
            "high": 103.0,
            "low": 98.0,
            "close": 102.5,
            "volume": 3_003,
        }
    ]
    assert _root_bytes(tmp_path) == before
