from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import swing_trading_ai_assistant.market_data.intraday_views as intraday_module
import swing_trading_ai_assistant.market_data.open_month_query as open_query_module
from swing_trading_ai_assistant.market_data.daily_ohlcv import (
    DailyScheduleResolutionV1,
    TimeframeQueryServiceV1,
    VerifiedClosureV1,
    VerifiedSessionV1,
)
from swing_trading_ai_assistant.market_data.intraday_views import (
    DERIVED_INTRADAY_CALCULATION_VERSION_V1,
    DerivedEvidenceIncompleteV1,
    DerivedIntradayQueryServiceV1,
    DuckDBIntradayViewEngineV1,
    OpenMonthDerivedIntradayQueryServiceV1,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.open_month_query import (
    CurrentAwareQueryServiceV1,
)
from swing_trading_ai_assistant.market_data.parquet import write_candles_parquet
from swing_trading_ai_assistant.market_data.preview_admission import (
    PreviewAdmissionPolicyV1,
)
from swing_trading_ai_assistant.market_data.public_contract import (
    CandleFieldV1,
    CoverageStateV1,
    DerivedIntradayQueryPayloadV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicCoverageMonthV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    PublicQueryRequestV1,
    PublicQueryRowV1,
    QueryPayloadV1,
    render_query_report_json,
)
from swing_trading_ai_assistant.market_data.public_coverage import (
    CoverageEvaluationFailureV1,
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
    ScheduleEvidenceResult,
    ScheduleFailureCode,
    ScheduleOutcome,
    ScheduleSession,
    canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_data.validation import ValidationReason

DIGEST = "a" * 64
START = datetime(2026, 7, 3, 3, 45, tzinfo=UTC)


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
            raise RuntimeError


class _DescriptorEvaluator:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def open_verified_partition_under_admission(
        self, _root: Path, selection: VerifiedPartitionV1, admission: _Admission
    ):
        assert admission.live
        descriptor = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC)
        try:
            yield VerifiedPartitionReadHandleV1(f"/dev/fd/{descriptor}", selection)
        finally:
            os.close(descriptor)


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


def _evaluation(count: int) -> CoverageEvaluationV1:
    last = START + timedelta(minutes=count - 1)
    month = PublicCoverageMonthV1(
        "2026-07",
        CoverageStateV1.VERIFIED,
        START,
        last,
        count,
        "b" * 64,
        1,
        f"nse-equity-month@v1+sessions-sha256:{DIGEST}",
        DIGEST,
        None,
        ValidationReason.NONE,
    )
    selection = VerifiedPartitionV1(
        _plan(),
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
        "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
        "year=2026/month=07/bars.parquet",
        "b" * 64,
        count,
        START,
        last,
        DIGEST,
    )
    return CoverageEvaluationV1((month,), (selection,))


def _request(timeframe: str = "5m", max_rows: int = 100) -> PublicQueryRequestV1:
    return PublicQueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 3),
        date(2026, 7, 3),
        timeframe,
        tuple(CandleFieldV1),
        max_rows,
    )


def _raw_request(
    root: Path,
    timeframe: str = "5m",
    *,
    from_date: date = date(2026, 7, 3),
    to_date: date = date(2026, 7, 3),
    fields: tuple[str, ...] = tuple(value.value for value in CandleFieldV1),
    max_rows: int = 100,
) -> QueryRequestV1:
    return QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        from_date,
        to_date,
        timeframe,
        fields,
        max_rows,
        root,
    )


def _session(count: int, start: datetime = START) -> VerifiedSessionV1:
    return VerifiedSessionV1(
        date(2026, 7, 3),
        start,
        start + timedelta(minutes=count),
        DIGEST,
    )


def _candles(count: int, start: datetime = START) -> tuple[CanonicalCandle, ...]:
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
            start + timedelta(minutes=index),
            100.0 + index,
            101.0 + index,
            99.0 + index,
            100.5 + index,
            index + 1,
            None,
            datetime(2026, 8, 1, tzinfo=UTC),
            "upstox-historical-v3",
            "raw",
        )
        for index in range(count)
    )


def _execute(
    tmp_path: Path,
    candles: tuple[CanonicalCandle, ...],
    session: VerifiedSessionV1,
    timeframe: str = "5m",
    max_rows: int = 100,
) -> tuple[PublicQueryRowV1, ...]:
    parquet_path = tmp_path / "bars.parquet"
    write_candles_parquet(parquet_path, candles)
    admission = _Admission()
    with admission:
        return DuckDBIntradayViewEngineV1().execute(
            _request(timeframe, max_rows),
            tmp_path,
            _evaluation(len(candles)),
            (session,),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )


def test_five_minute_buckets_are_session_anchored_and_keep_complete_tail(
    tmp_path: Path,
) -> None:
    rows = _execute(tmp_path, _candles(7), _session(7))

    assert tuple(row.ts for row in rows) == (START, START + timedelta(minutes=5))
    assert (rows[0].open, rows[0].high, rows[0].low, rows[0].close, rows[0].volume) == (
        100.0,
        105.0,
        99.0,
        104.5,
        15,
    )
    assert (rows[1].open, rows[1].high, rows[1].low, rows[1].close, rows[1].volume) == (
        105.0,
        107.0,
        104.0,
        106.5,
        13,
    )


@pytest.mark.parametrize(
    "timeframe,minutes", [("3m", 3), ("15m", 15), ("30m", 30), ("1h", 60)]
)
def test_every_supported_interval_uses_exact_session_buckets(
    tmp_path: Path, timeframe: str, minutes: int
) -> None:
    rows = _execute(tmp_path, _candles(minutes + 1), _session(minutes + 1), timeframe)
    assert tuple(row.ts for row in rows) == (START, START + timedelta(minutes=minutes))


def test_special_session_is_anchored_to_authoritative_open(tmp_path: Path) -> None:
    start = datetime(2026, 7, 3, 7, 2, tzinfo=UTC)
    rows = _execute(tmp_path, _candles(6, start), _session(6, start))
    assert tuple(row.ts for row in rows) == (start, start + timedelta(minutes=5))


def test_missing_duplicate_and_off_grid_minutes_fail_as_insufficient_evidence(
    tmp_path: Path,
) -> None:
    base = _candles(7)
    cases = [base[:3] + base[4:], base[:3] + (base[2],) + base[3:]]
    for index, candles in enumerate(cases):
        root = tmp_path / str(index)
        root.mkdir()
        with pytest.raises(DerivedEvidenceIncompleteV1):
            _execute(root, candles, _session(7))

    path = tmp_path / "off-grid"
    path.mkdir()
    parquet_path = path / "bars.parquet"
    write_candles_parquet(parquet_path, base)
    table = pq.read_table(parquet_path)
    timestamps = table.column("ts").to_pylist()
    timestamps[2] += timedelta(seconds=30)
    table = table.set_column(
        table.schema.get_field_index("ts"),
        "ts",
        pa.array(timestamps, type=table.schema.field("ts").type),
    )
    pq.write_table(table, parquet_path)
    admission = _Admission()
    with admission, pytest.raises(DerivedEvidenceIncompleteV1):
        DuckDBIntradayViewEngineV1().execute(
            _request(),
            path,
            _evaluation(7),
            (_session(7),),
            _DescriptorEvaluator(parquet_path),  # type: ignore[arg-type]
            admission,  # type: ignore[arg-type]
        )


def test_volume_overflow_and_output_bound_are_typed(tmp_path: Path) -> None:
    candles = list(_candles(5))
    candles[0] = replace(candles[0], volume=2**63 - 1)
    with pytest.raises(QueryResourceLimitV1):
        _execute(tmp_path, tuple(candles), _session(5))

    with pytest.raises(QueryResourceLimitV1):
        _execute(tmp_path, _candles(7), _session(7), max_rows=1)


def test_public_payload_freezes_raw_calculation_provenance() -> None:
    request = _request()
    row = PublicQueryRowV1(START, 100.0, 101.0, 99.0, 100.5, 1)
    payload = DerivedIntradayQueryPayloadV1(
        request,
        DERIVED_INTRADAY_CALCULATION_VERSION_V1,
        "raw",
        5,
        1,
        _evaluation(1).months,
        (row,),
    )
    assert payload.calculation_version == "nse-session-intraday-ohlcv@v1"
    assert payload.adjustment_state == "raw"

    with pytest.raises(ValueError):
        replace(payload, bucket_minutes=3)


def test_router_sends_only_approved_intraday_views_to_derived_service(
    tmp_path: Path,
) -> None:
    class Port:
        def __init__(self, value: str) -> None:
            self.value = value

        def query(self, _request: object) -> str:
            return self.value

        def query_under_lease(self, _request: object, _lease: object) -> str:
            return self.value

    router = TimeframeQueryServiceV1(
        Port("minute"), Port("daily"), intraday_service=Port("derived")
    )
    for timeframe in ("3m", "5m", "15m", "30m", "1h"):
        raw = QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 3),
            date(2026, 7, 3),
            timeframe,
            ("ts", "close"),
            10,
            tmp_path,
        )
        assert router.query(raw) == "derived"


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 7, 3, 8, tzinfo=UTC)


class _CoverageEvaluator:
    def __init__(self, evaluation: CoverageEvaluationV1) -> None:
        self.evaluation = evaluation
        self.admission = _Admission()

    def admit(self, _root: object) -> _Admission:
        return self.admission

    def evaluate_under_admission(
        self, _request: object, _invocation: object, admission: _Admission
    ) -> CoverageEvaluationV1:
        assert admission.live
        return self.evaluation


class _ScheduleResolver:
    def __init__(self, session: VerifiedSessionV1) -> None:
        self.session = session

    def resolve(self, *_: object) -> DailyScheduleResolutionV1:
        return DailyScheduleResolutionV1((self.session,), ())


class _DerivedEngine:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def execute(self, request: PublicQueryRequestV1, *_: object):
        if self.error is not None:
            raise self.error
        return (PublicQueryRowV1(START, 100.0, 101.0, 99.0, 100.5, 1),)


def test_closed_service_maps_complete_and_incomplete_evidence_without_provider_calls(
    tmp_path: Path,
) -> None:
    evaluation = _evaluation(5)
    raw = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 3),
        date(2026, 7, 3),
        "5m",
        tuple(value.value for value in CandleFieldV1),
        10,
        tmp_path.resolve(),
    )
    success = DerivedIntradayQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        _CoverageEvaluator(evaluation),  # type: ignore[arg-type]
        resolver=_ScheduleResolver(_session(5)),  # type: ignore[arg-type]
        engine=_DerivedEngine(),  # type: ignore[arg-type]
        clock=_Clock(),
    ).query(raw)
    assert success.status is PublicCommandStatusV1.SUCCEEDED
    assert success.provider_attempt_count == 0
    assert isinstance(success.payload, DerivedIntradayQueryPayloadV1)

    incomplete = DerivedIntradayQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        _CoverageEvaluator(evaluation),  # type: ignore[arg-type]
        resolver=_ScheduleResolver(_session(5)),  # type: ignore[arg-type]
        engine=_DerivedEngine(DerivedEvidenceIncompleteV1()),  # type: ignore[arg-type]
        clock=_Clock(),
    ).query(raw)
    assert incomplete.status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
    assert incomplete.failure is not None
    assert incomplete.failure.months == ("2026-07",)
    assert incomplete.provider_attempt_count == 0


def _provisional_month(
    count: int, *, session_complete: bool = False
) -> PublicCoverageMonthV1:
    last = START + timedelta(minutes=count - 1)
    return PublicCoverageMonthV1(
        "2026-07",
        CoverageStateV1.PROVISIONAL,
        START,
        last,
        count,
        "c" * 64,
        1,
        None,
        DIGEST,
        None,
        None,
        last,
        session_complete,
    )


class _MinutePort:
    def __init__(
        self, rows: tuple[PublicQueryRowV1, ...], month: PublicCoverageMonthV1
    ) -> None:
        self.rows = rows
        self.month = month
        self.calls = 0

    def query_under_lease(
        self, request: QueryRequestV1, _lease: StorageRootLease
    ) -> PublicCommandReportV1[QueryPayloadV1]:
        self.calls += 1
        public = PublicQueryRequestV1(
            request.segment,
            request.symbol,
            request.from_date,
            request.to_date,
            "1m",
            tuple(CandleFieldV1),
            10_000,
        )
        return PublicCommandReportV1(
            "v1",
            "query",
            PublicCommandStatusV1.SUCCEEDED,
            None,
            0,
            QueryPayloadV1(public, len(self.rows), (self.month,), self.rows),
        )


class _OpenScheduleResolver:
    def resolve(
        self, _root: Path, _digest: str, _invocation: datetime, _lease: StorageRootLease
    ) -> DailyScheduleResolutionV1:
        return DailyScheduleResolutionV1((_session(10),), ())


def _minute_rows(count: int) -> tuple[PublicQueryRowV1, ...]:
    return tuple(
        PublicQueryRowV1(
            START + timedelta(minutes=index),
            100.0 + index,
            101.0 + index,
            99.0 + index,
            100.5 + index,
            index + 1,
        )
        for index in range(count)
    )


def test_open_month_service_omits_only_the_advancing_bucket(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    minute = _MinutePort(_minute_rows(7), _provisional_month(7))
    request = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 3),
        date(2026, 7, 3),
        "5m",
        tuple(value.value for value in CandleFieldV1),
        10,
        tmp_path,
    )
    with acquired.lease as lease:
        report = OpenMonthDerivedIntradayQueryServiceV1(
            minute,  # type: ignore[arg-type]
            _OpenScheduleResolver(),  # type: ignore[arg-type]
            clock=_Clock(),
        ).query_under_lease(request, lease)

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.provider_attempt_count == 0
    assert isinstance(report.payload, DerivedIntradayQueryPayloadV1)
    assert tuple(row.ts for row in report.payload.rows) == (START,)
    assert report.payload.months[0].session_complete is False
    assert minute.calls == 1


def _derived_report(
    request: QueryRequestV1, month: PublicCoverageMonthV1, ts: datetime
):
    public = PublicQueryRequestV1(
        request.segment,
        request.symbol,
        request.from_date,
        request.to_date,
        "5m",
        tuple(CandleFieldV1),
        request.max_rows,
    )
    payload = DerivedIntradayQueryPayloadV1(
        public,
        DERIVED_INTRADAY_CALCULATION_VERSION_V1,
        "raw",
        5,
        1,
        (month,),
        (PublicQueryRowV1(ts, 100.0, 101.0, 99.0, 100.5, 1),),
    )
    return PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )


def test_current_aware_service_combines_closed_and_provisional_derived_views(
    tmp_path: Path,
) -> None:
    class AugustClock:
        def now(self) -> datetime:
            return datetime(2026, 8, 12, 8, tzinfo=UTC)

    class DerivedPort:
        def __init__(self, open_month: bool) -> None:
            self.open_month = open_month
            self.calls = 0

        def query(self, request: QueryRequestV1):
            self.calls += 1
            if self.open_month:
                month = replace(_provisional_month(1), month="2026-08")
                return _derived_report(
                    request, month, datetime(2026, 8, 3, 3, 45, tzinfo=UTC)
                )
            month = replace(
                _evaluation(1).months[0],
                actual_from_ts=datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
                actual_to_ts=datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
            )
            return _derived_report(
                request, month, datetime(2026, 7, 31, 3, 45, tzinfo=UTC)
            )

        def query_under_lease(self, request: QueryRequestV1, _lease: StorageRootLease):
            return self.query(request)

    closed = DerivedPort(False)
    opened = DerivedPort(True)
    request = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 31),
        date(2026, 8, 12),
        "5m",
        tuple(value.value for value in CandleFieldV1),
        10,
        tmp_path,
    )
    report = CurrentAwareQueryServiceV1(
        closed,  # type: ignore[arg-type]
        closed,  # unused for a derived request
        open_intraday_service=opened,  # type: ignore[arg-type]
        clock=AugustClock(),
    ).query(request)

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert isinstance(report.payload, DerivedIntradayQueryPayloadV1)
    assert tuple(month.month for month in report.payload.months) == (
        "2026-07",
        "2026-08",
    )
    assert tuple(row.ts for row in report.payload.rows) == (
        datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
        datetime(2026, 8, 3, 3, 45, tzinfo=UTC),
    )
    assert closed.calls == opened.calls == 1


def _retained_schedule() -> ExpectedSessionSchedule:
    return ExpectedSessionSchedule(
        2,
        "authoritative-calendar-test",
        "release-2026-07-03",
        datetime(2026, 7, 3, 4, 0, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 7, 3),
        date(2026, 7, 3),
        (
            ScheduleSession(
                date(2026, 7, 3),
                START,
                START + timedelta(minutes=10),
                "special-test",
            ),
        ),
        (),
    )


def test_retained_open_schedule_is_digest_bound_and_point_in_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule = _retained_schedule()
    digest = schedule_digest(schedule)
    result = ScheduleEvidenceResult(
        ScheduleOutcome.RESOLVED,
        ScheduleFailureCode.NONE,
        schedule,
        canonical_schedule_bytes(schedule),
        digest,
        f"calendar-schedules/sha256/{digest}.json",
    )

    class FakeStore:
        def __init__(self, _root: Path, _lease: object) -> None:
            return None

        def resolve(self, _digest: str) -> ScheduleEvidenceResult:
            return result

    monkeypatch.setattr(intraday_module, "ScheduleEvidenceStore", FakeStore)
    resolution = intraday_module.RetainedOpenMonthScheduleResolverV1().resolve(
        tmp_path,
        digest,
        datetime(2026, 7, 3, 8, tzinfo=UTC),
        object(),  # type: ignore[arg-type]
    )
    assert resolution.sessions == (
        VerifiedSessionV1(
            date(2026, 7, 3), START, START + timedelta(minutes=10), digest
        ),
    )
    assert resolution.closures == ()

    for invalid in (
        object(),
        replace(result, digest="b" * 64),
        replace(
            result,
            schedule=replace(schedule, as_of=datetime(2026, 7, 4, tzinfo=UTC)),
            canonical_bytes=canonical_schedule_bytes(
                replace(schedule, as_of=datetime(2026, 7, 4, tzinfo=UTC))
            ),
        ),
    ):

        class InvalidStore:
            def __init__(self, _root: Path, _lease: object) -> None:
                return None

            def resolve(self, _digest: str, value: object = invalid) -> object:
                return value

        monkeypatch.setattr(intraday_module, "ScheduleEvidenceStore", InvalidStore)
        with pytest.raises(QueryExecutionFailureV1):
            intraday_module.RetainedOpenMonthScheduleResolverV1().resolve(
                tmp_path,
                digest,
                datetime(2026, 7, 3, 8, tzinfo=UTC),
                object(),  # type: ignore[arg-type]
            )


def test_open_service_public_entry_is_existing_only_and_validates_lease(
    tmp_path: Path,
) -> None:
    service = OpenMonthDerivedIntradayQueryServiceV1(
        _MinutePort(_minute_rows(7), _provisional_month(7)),  # type: ignore[arg-type]
        _OpenScheduleResolver(),  # type: ignore[arg-type]
        clock=_Clock(),
    )
    invalid = service.query(object())
    assert invalid.status is PublicCommandStatusV1.REJECTED
    assert invalid.failure is not None
    assert invalid.failure.code is PublicFailureCodeV1.INVALID_INPUT

    missing = service.query(_raw_request((tmp_path / "missing").resolve()))
    assert missing.status is PublicCommandStatusV1.UNAVAILABLE
    assert missing.failure is not None
    assert missing.failure.code is PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE

    wrong_lease = service.query_under_lease(
        _raw_request(tmp_path.resolve()),
        object(),  # type: ignore[arg-type]
    )
    assert wrong_lease.status is PublicCommandStatusV1.REJECTED

    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease:
        prepared_failure = service.query_under_lease(object(), lease)
        assert prepared_failure.status is PublicCommandStatusV1.REJECTED
    success = service.query(_raw_request(tmp_path.resolve()))
    assert success.status is PublicCommandStatusV1.SUCCEEDED
    assert success.provider_attempt_count == 0


@pytest.mark.parametrize(
    ("request_case", "clock", "code"),
    (
        (object(), _Clock(), PublicFailureCodeV1.INVALID_INPUT),
        ("unsupported", _Clock(), PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME),
        ("bounded", _Clock(), PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED),
        ("future", _Clock(), PublicFailureCodeV1.INVALID_INPUT),
        (
            "valid",
            SimpleNamespace(now=lambda: datetime(2026, 7, 3)),
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        ),
    ),
)
def test_open_service_request_failures_are_stable(
    tmp_path: Path, request_case: object, clock: object, code: PublicFailureCodeV1
) -> None:
    actual = request_case
    if request_case == "unsupported":
        actual = _raw_request(tmp_path.resolve(), "1m")
    elif request_case == "bounded":
        actual = _raw_request(tmp_path.resolve(), max_rows=10_001)
    elif request_case == "future":
        actual = _raw_request(
            tmp_path.resolve(),
            from_date=date(2026, 7, 3),
            to_date=date(2026, 7, 4),
        )
    elif request_case == "valid":
        actual = _raw_request(tmp_path.resolve())
    result = OpenMonthDerivedIntradayQueryServiceV1(
        _MinutePort((), _provisional_month(1)),  # type: ignore[arg-type]
        _OpenScheduleResolver(),  # type: ignore[arg-type]
        clock=clock,  # type: ignore[arg-type]
    ).query_under_lease(actual, object())  # type: ignore[arg-type]
    assert result.failure is not None
    assert result.failure.code is PublicFailureCodeV1.INVALID_INPUT
    if type(actual) is QueryRequestV1:
        prepared = intraday_module._prepare_open_request(actual, clock)  # type: ignore[arg-type]
        assert isinstance(prepared, PublicCommandReportV1)
        assert prepared.failure is not None
        assert prepared.failure.code is code


def test_open_service_maps_minute_and_aggregation_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    request = _raw_request(tmp_path.resolve())
    minute = _MinutePort(_minute_rows(7), _provisional_month(7))
    service = OpenMonthDerivedIntradayQueryServiceV1(
        minute,  # type: ignore[arg-type]
        _OpenScheduleResolver(),  # type: ignore[arg-type]
        clock=_Clock(),
    )
    with acquired.lease as lease:
        original = intraday_module._aggregate_available_rows
        for error, code in (
            (QueryResourceLimitV1(), PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED),
            (QueryTimeoutV1(), PublicFailureCodeV1.QUERY_TIMEOUT),
            (RuntimeError("sanitized"), PublicFailureCodeV1.UNCLASSIFIED_FAILURE),
        ):
            monkeypatch.setattr(
                intraday_module,
                "_aggregate_available_rows",
                lambda *_args, error=error: (_ for _ in ()).throw(error),
            )
            report = service.query_under_lease(request, lease)
            assert report.failure is not None
            assert report.failure.code is code
        monkeypatch.setattr(intraday_module, "_aggregate_available_rows", original)

        source_rows = _minute_rows(6)
        incomplete = OpenMonthDerivedIntradayQueryServiceV1(
            _MinutePort(source_rows[:2] + source_rows[3:], _provisional_month(6)),  # type: ignore[arg-type]
            _OpenScheduleResolver(),  # type: ignore[arg-type]
            clock=_Clock(),
        ).query_under_lease(request, lease)
        assert incomplete.status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
        assert incomplete.failure is not None
        assert incomplete.failure.months == ("2026-07",)


def test_open_service_rejects_malformed_minute_reports(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    request = _raw_request(tmp_path.resolve())

    class Port:
        def __init__(self, value: object) -> None:
            self.value = value

        def query_under_lease(self, _request: object, _lease: object) -> object:
            return self.value

    failure = PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.FAILED,
        PublicFailureV1(PublicFailureCodeV1.QUERY_TIMEOUT, None, None, None, None, ()),
        0,
        None,
    )
    cases = (object(), failure)
    with acquired.lease as lease:
        for value in cases:
            report = OpenMonthDerivedIntradayQueryServiceV1(
                Port(value),  # type: ignore[arg-type]
                _OpenScheduleResolver(),  # type: ignore[arg-type]
                clock=_Clock(),
            ).query_under_lease(request, lease)
            expected = (
                PublicFailureCodeV1.QUERY_TIMEOUT
                if value is failure
                else PublicFailureCodeV1.UNCLASSIFIED_FAILURE
            )
            assert report.failure is not None
            assert report.failure.code is expected


def test_open_service_forwards_minute_evidence_and_rejects_missing_cutoff(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    request = _raw_request(tmp_path.resolve())
    minute_request = replace(
        request,
        timeframe="1m",
        fields=tuple(value.value for value in CandleFieldV1),
        max_rows=10_000,
    )
    public_minute = PublicQueryRequestV1(
        minute_request.segment,
        minute_request.symbol,
        minute_request.from_date,
        minute_request.to_date,
        "1m",
        tuple(CandleFieldV1),
        10_000,
    )
    missing_payload = QueryPayloadV1(public_minute, 0, _missing_evaluation().months, ())
    insufficient = PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
        PublicFailureV1(
            PublicFailureCodeV1.COVERAGE_INSUFFICIENT,
            None,
            None,
            None,
            None,
            ("2026-07",),
        ),
        0,
        missing_payload,
    )

    class Port:
        def __init__(self, value: object) -> None:
            self.value = value

        def query_under_lease(self, _request: object, _lease: object) -> object:
            return self.value

    with acquired.lease as lease:
        forwarded = OpenMonthDerivedIntradayQueryServiceV1(
            Port(insufficient),  # type: ignore[arg-type]
            _OpenScheduleResolver(),  # type: ignore[arg-type]
            clock=_Clock(),
        ).query_under_lease(request, lease)
        assert forwarded.status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
        assert isinstance(forwarded.payload, DerivedIntradayQueryPayloadV1)

        verified_without_cutoff = _MinutePort(_minute_rows(5), _evaluation(5).months[0])
        rejected = OpenMonthDerivedIntradayQueryServiceV1(
            verified_without_cutoff,  # type: ignore[arg-type]
            _OpenScheduleResolver(),  # type: ignore[arg-type]
            clock=_Clock(),
        ).query_under_lease(request, lease)
        assert rejected.status is PublicCommandStatusV1.FAILED
        assert rejected.failure is not None
        assert rejected.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE

        mismatched = QueryPayloadV1(
            replace(public_minute, symbol="TCS"), 0, _missing_evaluation().months, ()
        )
        malformed = PublicCommandReportV1(
            "v1",
            "query",
            PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
            PublicFailureV1(
                PublicFailureCodeV1.COVERAGE_INSUFFICIENT,
                None,
                None,
                None,
                None,
                ("2026-07",),
            ),
            0,
            mismatched,
        )
        invalid = OpenMonthDerivedIntradayQueryServiceV1(
            Port(malformed),  # type: ignore[arg-type]
            _OpenScheduleResolver(),  # type: ignore[arg-type]
            clock=_Clock(),
        ).query_under_lease(request, lease)
        assert invalid.status is PublicCommandStatusV1.FAILED


def _missing_evaluation() -> CoverageEvaluationV1:
    return CoverageEvaluationV1(
        (
            PublicCoverageMonthV1(
                "2026-07",
                CoverageStateV1.MISSING,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        ),
        (),
    )


def _closed_service(
    root: Path,
    *,
    evaluator: object | None = None,
    engine: object | None = None,
    clock: object | None = None,
) -> DerivedIntradayQueryServiceV1:
    return DerivedIntradayQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        evaluator or _CoverageEvaluator(_evaluation(5)),  # type: ignore[arg-type]
        resolver=_ScheduleResolver(_session(5)),  # type: ignore[arg-type]
        engine=engine or _DerivedEngine(),  # type: ignore[arg-type]
        clock=clock or _Clock(),  # type: ignore[arg-type]
    )


def test_closed_service_rejects_invalid_unsupported_and_bounded_requests(
    tmp_path: Path,
) -> None:
    service = _closed_service(tmp_path)
    cases = (
        (object(), PublicFailureCodeV1.INVALID_INPUT),
        (
            replace(_raw_request(tmp_path.resolve()), symbol="TCS"),
            PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
        ),
        (
            _raw_request(tmp_path.resolve(), "1d"),
            PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME,
        ),
        (
            _raw_request(tmp_path.resolve(), max_rows=10_001),
            PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED,
        ),
        (
            _raw_request(Path("relative")),
            PublicFailureCodeV1.INVALID_INPUT,
        ),
    )
    for request, code in cases:
        report = service.query(request)
        assert report.status is PublicCommandStatusV1.REJECTED
        assert report.failure is not None
        assert report.failure.code is code

    invalid_lease = service.query_under_lease(
        _raw_request(tmp_path.resolve()),
        object(),  # type: ignore[arg-type]
    )
    assert invalid_lease.status is PublicCommandStatusV1.REJECTED


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
            RuntimeError("sanitized"),
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        ),
    ),
)
def test_closed_service_maps_dependency_failures(
    tmp_path: Path,
    error: Exception,
    status: PublicCommandStatusV1,
    code: PublicFailureCodeV1,
) -> None:
    class Evaluator:
        def admit(self, _root: object) -> _Admission:
            return _Admission()

        def evaluate_under_admission(self, *_args: object) -> object:
            raise error

    report = _closed_service(tmp_path, evaluator=Evaluator()).query(
        _raw_request(tmp_path.resolve())
    )
    assert report.status is status
    assert report.failure is not None
    assert report.failure.code is code


def test_closed_service_preserves_missing_coverage_and_live_lease(
    tmp_path: Path,
) -> None:
    missing = _closed_service(
        tmp_path, evaluator=_CoverageEvaluator(_missing_evaluation())
    ).query(_raw_request(tmp_path.resolve()))
    assert missing.status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
    assert missing.failure is not None
    assert missing.failure.months == ("2026-07",)
    assert isinstance(missing.payload, DerivedIntradayQueryPayloadV1)
    assert missing.payload.rows == ()

    class LeaseEvaluator:
        def evaluate_under_admission(
            self, _request: object, _invocation: object, admission: object
        ) -> CoverageEvaluationV1:
            assert isinstance(admission, ExistingCoverageAdmissionV1)
            return _evaluation(5)

    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease:
        result = _closed_service(
            tmp_path, evaluator=LeaseEvaluator()
        ).query_under_lease(_raw_request(tmp_path.resolve()), lease)
    assert result.status is PublicCommandStatusV1.SUCCEEDED


def test_closed_service_invalid_rows_become_insufficient_and_invalid_clock_fails(
    tmp_path: Path,
) -> None:
    invalid_rows = _closed_service(
        tmp_path,
        engine=_DerivedEngine(),
    )
    invalid_rows._engine = SimpleNamespace(  # type: ignore[attr-defined]
        execute=lambda *_args: (
            PublicQueryRowV1(
                START + timedelta(minutes=1), 100.0, 101.0, 99.0, 100.5, 1
            ),
        )
    )
    report = invalid_rows.query(_raw_request(tmp_path.resolve()))
    assert report.status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE

    failed = _closed_service(
        tmp_path, clock=SimpleNamespace(now=lambda: datetime(2026, 7, 3))
    ).query(_raw_request(tmp_path.resolve()))
    assert failed.status is PublicCommandStatusV1.FAILED
    assert failed.failure is not None
    assert failed.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE


def test_engine_rejects_invalid_boundaries_empty_sessions_and_open_failure(
    tmp_path: Path,
) -> None:
    engine = DuckDBIntradayViewEngineV1()
    admission = _Admission()

    class FailingEvaluator:
        @contextmanager
        def open_verified_partition_under_admission(self, *_args: object):
            raise RuntimeError("sanitized")
            yield

    with admission:
        with pytest.raises(QueryExecutionFailureV1):
            engine.execute(  # type: ignore[arg-type]
                object(),
                tmp_path,
                _evaluation(5),
                (_session(5),),
                _DescriptorEvaluator(tmp_path),  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )
        with pytest.raises(QueryResourceLimitV1):
            engine.execute(
                replace(_request(), timeframe="1m"),
                tmp_path,
                _evaluation(5),
                (_session(5),),
                _DescriptorEvaluator(tmp_path),  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )
        assert (
            engine.execute(
                _request(),
                tmp_path,
                _evaluation(5),
                (),
                _DescriptorEvaluator(tmp_path),  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )
            == ()
        )
        with pytest.raises(QueryExecutionFailureV1):
            engine.execute(
                _request(),
                tmp_path,
                _evaluation(5),
                (_session(5),),
                FailingEvaluator(),  # type: ignore[arg-type]
                admission,  # type: ignore[arg-type]
            )


def _valid_raw_bucket() -> tuple[object, ...]:
    open_us = intraday_module._epoch_us(START)
    close_us = intraday_module._epoch_us(START + timedelta(minutes=5))
    bucket_us = 5 * 60_000_000
    return (
        open_us,
        close_us,
        bucket_us,
        0,
        open_us,
        close_us,
        100.0,
        105.0,
        99.0,
        104.5,
        15,
        5,
        5,
        open_us,
        close_us - 60_000_000,
        0,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ((), QueryExecutionFailureV1),
        ([()], QueryExecutionFailureV1),
        ([], DerivedEvidenceIncompleteV1),
        ([_valid_raw_bucket(), _valid_raw_bucket()], DerivedEvidenceIncompleteV1),
        ([SimpleNamespace()], QueryExecutionFailureV1),
    ),
)
def test_intraday_materialization_rejects_wrong_shapes_and_counts(
    raw: object, expected: type[Exception]
) -> None:
    with pytest.raises(expected):
        intraday_module._intraday_rows(_request(), (_session(5),), 5, raw)


@pytest.mark.parametrize(
    ("index", "value", "expected"),
    (
        (0, "bad", QueryExecutionFailureV1),
        (2, 1, QueryExecutionFailureV1),
        (3, -1, DerivedEvidenceIncompleteV1),
        (5, 1, DerivedEvidenceIncompleteV1),
        (6, 106.0, QueryExecutionFailureV1),
        (10, -1, QueryResourceLimitV1),
        (11, 4, DerivedEvidenceIncompleteV1),
        (12, 4, DerivedEvidenceIncompleteV1),
        (15, 1, DerivedEvidenceIncompleteV1),
    ),
)
def test_intraday_row_rejects_inconsistent_values(
    index: int, value: object, expected: type[Exception]
) -> None:
    raw = list(_valid_raw_bucket())
    raw[index] = value
    with pytest.raises(expected):
        intraday_module._intraday_row(
            tuple(CandleFieldV1), (_session(5),), 5, tuple(raw)
        )


def test_intraday_row_honours_selected_fields() -> None:
    row = intraday_module._intraday_row(
        (CandleFieldV1.TS, CandleFieldV1.CLOSE),
        (_session(5),),
        5,
        _valid_raw_bucket(),
    )
    assert (row.open, row.high, row.low, row.close, row.volume) == (
        None,
        None,
        None,
        104.5,
        None,
    )


def test_materialization_rejects_non_monotonic_bucket_output() -> None:
    with pytest.raises(QueryExecutionFailureV1):
        intraday_module._intraday_rows(
            _request(), (_session(5), _session(5)), 5, [_valid_raw_bucket()] * 2
        )


def _handle() -> VerifiedPartitionReadHandleV1:
    return VerifiedPartitionReadHandleV1(
        "/dev/fd/9", _evaluation(5).verified_partitions[0]
    )


def test_intraday_engine_deadline_interrupts_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReturningConnection:
        def __init__(self) -> None:
            self.closed = False

        def execute(self, _statement: str, _parameters: object) -> ReturningConnection:
            return self

        def fetchall(self) -> list[tuple[object, ...]]:
            return [_valid_raw_bucket()]

        def interrupt(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    class ImmediateTimer:
        def __init__(
            self, _seconds: float, target: object, args: tuple[object, ...]
        ) -> None:
            self.daemon = False
            self.target = target
            self.args = args

        def start(self) -> None:
            assert callable(self.target)
            self.target(*self.args)

        def cancel(self) -> None:
            return None

        def join(self, timeout: float) -> None:
            assert timeout == 1.0

    connection = ReturningConnection()
    monkeypatch.setattr(intraday_module.duckdb, "connect", lambda **_kwargs: connection)
    monkeypatch.setattr(intraday_module.threading, "Timer", ImmediateTimer)
    with pytest.raises(QueryTimeoutV1):
        DuckDBIntradayViewEngineV1()._execute(
            _request(), (_session(5),), (_handle(),), 5
        )
    assert connection.closed


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        (intraday_module.duckdb.InterruptException("interrupted"), QueryTimeoutV1),
        (
            intraday_module.duckdb.OutOfMemoryException("bounded memory"),
            QueryResourceLimitV1,
        ),
        (RuntimeError("sanitized"), QueryExecutionFailureV1),
    ),
)
def test_intraday_engine_maps_database_failures(
    monkeypatch: pytest.MonkeyPatch, error: Exception, expected: type[Exception]
) -> None:
    def fail_connect(**_kwargs: object) -> object:
        raise error

    monkeypatch.setattr(intraday_module.duckdb, "connect", fail_connect)
    with pytest.raises(expected):
        DuckDBIntradayViewEngineV1()._execute(
            _request(), (_session(5),), (_handle(),), 5
        )


@pytest.mark.parametrize(
    "value",
    (
        object(),
        [],
        (object(),),
        (
            VerifiedSessionV1(
                date(2026, 7, 3),
                START,
                START + timedelta(minutes=5),
                "b" * 64,
            ),
        ),
    ),
)
def test_session_validation_rejects_malformed_and_unbound_values(value: object) -> None:
    with pytest.raises(QueryExecutionFailureV1):
        intraday_module._validated_sessions(_request(), _evaluation(5), value)


def test_evaluation_and_handle_validation_fail_closed() -> None:
    with pytest.raises(QueryExecutionFailureV1):
        intraday_module._validated_evaluation(object())
    mutated = _evaluation(5)
    object.__setattr__(mutated, "verified_partitions", ())
    with pytest.raises(QueryExecutionFailureV1):
        intraday_module._validated_evaluation(mutated)

    selection = _evaluation(5).verified_partitions
    for handles in (object(), [], (object(),), (_handle(), _handle())):
        with pytest.raises(QueryExecutionFailureV1):
            intraday_module._validated_handles(handles, selection)


@pytest.mark.parametrize(
    ("query_request", "expected"),
    (
        (
            _raw_request(Path("relative")),
            ValueError,
        ),
        (
            _raw_request(
                Path("/var/empty/ark142"),
                from_date=date(2026, 7, 4),
                to_date=date(2026, 7, 3),
            ),
            ValueError,
        ),
        (
            _raw_request(
                Path("/var/empty/ark142"),
                from_date=date(2021, 12, 31),
                to_date=date(2021, 12, 31),
            ),
            ValueError,
        ),
        (
            _raw_request(
                Path("/var/empty/ark142"),
                from_date=date(2025, 1, 1),
                to_date=date(2026, 1, 1),
            ),
            QueryResourceLimitV1,
        ),
        (
            _raw_request(Path("/var/empty/ark142"), fields=("bad",)),
            QueryResourceLimitV1,
        ),
    ),
)
def test_public_request_boundary_rejects_invalid_shapes(
    query_request: QueryRequestV1, expected: type[Exception]
) -> None:
    with pytest.raises(expected):
        intraday_module._public_request(query_request)


def test_open_resolution_and_derived_rows_are_exact() -> None:
    request = _request()
    for value in (
        object(),
        DailyScheduleResolutionV1((), ()),
        DailyScheduleResolutionV1((), (VerifiedClosureV1(date(2026, 7, 3), "b" * 64),)),
    ):
        with pytest.raises(QueryExecutionFailureV1):
            intraday_module._validated_open_resolution(request, DIGEST, value)

    for value in (
        object(),
        (object(),),
        (PublicQueryRowV1(START + timedelta(minutes=1), 1.0, 1.0, 1.0, 1.0, 1),),
    ):
        expected = (
            DerivedEvidenceIncompleteV1
            if isinstance(value, tuple)
            and value
            and isinstance(value[0], PublicQueryRowV1)
            else QueryExecutionFailureV1
        )
        with pytest.raises(expected):
            intraday_module._validated_derived_rows(request, (_session(5),), value)

    with pytest.raises(QueryExecutionFailureV1):
        intraday_module._validated_derived_rows(
            replace(request, timeframe="1m"), (_session(5),), ()
        )


def test_available_row_validation_rejects_partial_or_contradictory_evidence() -> None:
    request = _request()
    rows = _minute_rows(5)
    cases = (
        (replace(request, timeframe="1m"), (_session(5),), rows, rows[-1].ts),
        (request, (_session(5),), rows, datetime(2026, 7, 3)),
        (request, (object(),), rows, rows[-1].ts),
        (request, (_session(5),), rows + (rows[0],), rows[-1].ts),
        (
            request,
            (_session(5),),
            (replace(rows[0], close=None),) + rows[1:],
            rows[-1].ts,
        ),
        (
            request,
            (_session(5),),
            (replace(rows[0], ts=START - timedelta(minutes=1)),) + rows[1:],
            rows[-1].ts,
        ),
    )
    for current_request, sessions, current_rows, cutoff in cases:
        with pytest.raises((QueryExecutionFailureV1, DerivedEvidenceIncompleteV1)):
            intraday_module._validated_available_inputs(
                current_request,
                sessions,  # type: ignore[arg-type]
                current_rows,
                cutoff,
            )

    with pytest.raises(DerivedEvidenceIncompleteV1):
        intraday_module._complete_bucket(
            {row.ts: row for row in rows[:-1]}, START, START + timedelta(minutes=5)
        )

    overflow = tuple(replace(row, volume=2**63 - 1) for row in rows)
    with pytest.raises(QueryResourceLimitV1):
        intraday_module._aggregate_bucket(set(CandleFieldV1), START, overflow)

    with pytest.raises(QueryResourceLimitV1):
        intraday_module._aggregate_available_rows(
            _request(max_rows=1),
            (_session(10),),
            _minute_rows(10),
            START + timedelta(minutes=9),
        )


def test_closed_resolution_requires_one_authoritative_fact_per_date() -> None:
    request = _request()
    evaluation = _evaluation(5)
    for value in (
        object(),
        DailyScheduleResolutionV1((), ()),
        DailyScheduleResolutionV1((), (VerifiedClosureV1(date(2026, 7, 3), "b" * 64),)),
    ):
        with pytest.raises(QueryExecutionFailureV1):
            intraday_module._validated_resolution(request, evaluation, value)

    with pytest.raises(QueryExecutionFailureV1):
        intraday_module._payload(replace(request, timeframe="1m"), evaluation, ())
    with pytest.raises(ValueError):
        intraday_module._validated_invocation(datetime(2026, 7, 3))


def test_expire_query_suppresses_provider_specific_interrupt_failure() -> None:
    class Connection:
        def interrupt(self) -> None:
            raise RuntimeError("sanitized")

    deadline = threading.Event()
    intraday_module._expire_query(deadline, Connection())
    assert deadline.is_set()


def test_derived_json_and_split_insufficient_result_preserve_public_contract(
    tmp_path: Path,
) -> None:
    request = _raw_request(
        tmp_path,
        from_date=date(2026, 7, 31),
        to_date=date(2026, 8, 12),
    )
    closed_request = replace(request, to_date=date(2026, 7, 31))
    closed = _derived_report(
        closed_request,
        replace(
            _evaluation(1).months[0],
            actual_from_ts=datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
            actual_to_ts=datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
        ),
        datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
    )
    open_month = replace(_provisional_month(1), month="2026-08")
    open_payload = DerivedIntradayQueryPayloadV1(
        PublicQueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 12),
            "5m",
            tuple(CandleFieldV1),
            100,
        ),
        DERIVED_INTRADAY_CALCULATION_VERSION_V1,
        "raw",
        5,
        0,
        (open_month,),
        (),
    )
    opened = PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
        PublicFailureV1(
            PublicFailureCodeV1.COVERAGE_INSUFFICIENT,
            None,
            None,
            None,
            None,
            ("2026-08",),
        ),
        0,
        open_payload,
    )
    report = open_query_module._combine_query_reports(request, closed, opened)
    assert isinstance(report, PublicCommandReportV1)
    assert report.status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
    assert report.failure is not None
    assert report.failure.months == ("2026-08",)
    assert isinstance(report.payload, DerivedIntradayQueryPayloadV1)
    assert report.payload.rows == ()
    rendered = render_query_report_json(report)
    assert b'"calculation_version":"nse-session-intraday-ohlcv@v1"' in rendered
    assert b'"bucket_minutes":5' in rendered


def test_split_derived_combiner_fails_closed_on_malformed_and_terminal_fragments(
    tmp_path: Path,
) -> None:
    request = _raw_request(
        tmp_path,
        from_date=date(2026, 7, 31),
        to_date=date(2026, 8, 12),
    )
    failure = PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.FAILED,
        PublicFailureV1(PublicFailureCodeV1.QUERY_TIMEOUT, None, None, None, None, ()),
        0,
        None,
    )
    propagated = open_query_module._combine_query_reports(request, failure, object())
    assert propagated.failure is not None
    assert propagated.failure.code is PublicFailureCodeV1.QUERY_TIMEOUT

    unclassified = open_query_module._combine_query_reports(request, object(), object())
    assert unclassified.failure is not None
    assert unclassified.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE

    closed_request = replace(request, to_date=date(2026, 7, 31))
    closed = _derived_report(
        closed_request,
        replace(
            _evaluation(1).months[0],
            actual_from_ts=datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
            actual_to_ts=datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
        ),
        datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
    )
    opened = _derived_report(
        replace(request, from_date=date(2026, 8, 2)),
        replace(_provisional_month(1), month="2026-08"),
        datetime(2026, 8, 3, 3, 45, tzinfo=UTC),
    )
    inconsistent = open_query_module._combine_query_reports(request, closed, opened)
    assert inconsistent.failure is not None
    assert (
        inconsistent.failure.code is PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED
    )

    assert open_query_module._derived_fragment(object()) is None
    mutated = _derived_report(
        closed_request,
        replace(
            _evaluation(1).months[0],
            actual_from_ts=datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
            actual_to_ts=datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
        ),
        datetime(2026, 7, 31, 3, 45, tzinfo=UTC),
    )
    object.__setattr__(mutated.payload, "bucket_minutes", 3)
    assert open_query_module._derived_fragment(mutated) is None
