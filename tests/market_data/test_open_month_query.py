from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.provisional_store as provisional_store
from swing_trading_ai_assistant.market_data.catalog import (
    CatalogStorageError,
    DuckDBCatalog,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.open_month_query import (
    CurrentAwareQueryServiceV1,
    OpenMonthOneMinuteQueryServiceV1,
    _combine_query_reports,
    _public_row,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    publish_provisional_partition_under_lease,
)
from swing_trading_ai_assistant.market_data.preview_admission import (
    PreviewAdmissionPolicyV1,
)
from swing_trading_ai_assistant.market_data.provisional_metadata import (
    metadata_from_publication,
)
from swing_trading_ai_assistant.market_data.provisional_store import (
    ProvisionalPartitionUnavailableV1,
)
from swing_trading_ai_assistant.market_data.public_contract import (
    CandleFieldV1,
    CoverageStateV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicCoverageMonthV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    PublicQueryRequestV1,
    PublicQueryRowV1,
    QueryPayloadV1,
    QueryReportV1,
)
from swing_trading_ai_assistant.market_data.public_query import (
    QueryRequestV1,
    QueryTimeoutV1,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)
from swing_trading_ai_assistant.market_data.validation import (
    EQUITY_MONTH_VALIDATION_POLICY_V1,
    ValidationReason,
)

IST = timezone(timedelta(hours=5, minutes=30))


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
        8,
        date(2026, 8, 1),
        date(2026, 8, 11),
    )


def _row(minute: int) -> CanonicalCandle:
    return CanonicalCandle(
        provider="upstox",
        instrument_key="NSE_EQ|INE002A01018",
        security_id="INE002A01018",
        symbol="RELIANCE",
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        underlying_id=None,
        expiry=None,
        strike=None,
        option_type=None,
        interval="1m",
        ts=datetime(2026, 8, 11, 3, minute, tzinfo=UTC),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5 + minute / 100,
        volume=1_000 + minute,
        oi=None,
        ingested_at=datetime(2026, 8, 11, 4, 0, tzinfo=UTC),
        source_version="upstox-intraday-v3",
        adjustment_state="raw",
    )


def _seed(root: Path) -> None:
    lease_result = StorageRootLease.try_acquire(root)
    assert lease_result.outcome is LeaseOutcome.ACQUIRED
    assert lease_result.lease is not None
    with lease_result.lease as lease:
        rows = (_row(45), _row(46))
        digest = "a" * 64
        published = publish_provisional_partition_under_lease(
            root, lease, _plan(), rows[-1].ts, digest, rows
        )
        metadata = metadata_from_publication(
            plan=published.plan,
            schedule_digest_sha256=digest,
            cutoff=published.cutoff,
            session_complete=False,
            actual_from_ts=published.actual_from_ts,
            actual_to_ts=published.actual_to_ts,
            row_count=published.row_count,
            checksum_sha256=published.checksum_sha256,
            byte_size=published.byte_size,
            relative_path=published.canonical_path,
            instrument_snapshot_digest_sha256="b" * 64,
            instrument_snapshot_retrieved_at=datetime(2026, 8, 11, 3, 0, tzinfo=UTC),
            published_at=datetime(2026, 8, 11, 4, 0, tzinfo=UTC),
            historical_attempt_count=1,
            intraday_attempt_count=1,
        )
        with DuckDBCatalog(root, lease=lease) as catalog:
            catalog.save_provisional_partition(metadata)


def _seed_previous_month(root: Path) -> None:
    lease_result = StorageRootLease.try_acquire(root)
    assert lease_result.outcome is LeaseOutcome.ACQUIRED
    assert lease_result.lease is not None
    with lease_result.lease as lease:
        plan = replace(
            _plan(),
            year=2026,
            month=7,
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
        )
        rows = (
            replace(
                _row(45),
                ts=datetime(2026, 7, 31, 9, 58, tzinfo=UTC),
                ingested_at=datetime(2026, 7, 31, 11, tzinfo=UTC),
            ),
            replace(
                _row(46),
                ts=datetime(2026, 7, 31, 9, 59, tzinfo=UTC),
                ingested_at=datetime(2026, 7, 31, 11, tzinfo=UTC),
            ),
        )
        digest = "a" * 64
        published = publish_provisional_partition_under_lease(
            root, lease, plan, rows[-1].ts, digest, rows
        )
        metadata = metadata_from_publication(
            plan=published.plan,
            schedule_digest_sha256=digest,
            cutoff=published.cutoff,
            session_complete=True,
            actual_from_ts=published.actual_from_ts,
            actual_to_ts=published.actual_to_ts,
            row_count=published.row_count,
            checksum_sha256=published.checksum_sha256,
            byte_size=published.byte_size,
            relative_path=published.canonical_path,
            instrument_snapshot_digest_sha256="b" * 64,
            instrument_snapshot_retrieved_at=datetime(2026, 7, 31, 11, tzinfo=UTC),
            published_at=datetime(2026, 7, 31, 11, tzinfo=UTC),
            historical_attempt_count=1,
            intraday_attempt_count=0,
        )
        with DuckDBCatalog(root, lease=lease) as catalog:
            catalog.save_provisional_partition(metadata)


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 11, 10, 0, tzinfo=IST)


class _InvalidClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 11, 10, 0)


class _RolloverClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 1, 4, 30, tzinfo=UTC)


class _QueryStub:
    def __init__(self, report: object) -> None:
        self.report = report
        self.requests: list[object] = []

    def query(self, request: object):
        self.requests.append(request)
        return self.report


class _RaisingQueryStub:
    def query(self, request: object):
        raise RuntimeError("dependency failed")


def test_open_month_query_under_caller_lease_and_invalid_lease_are_bounded(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    service = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    )
    request = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 1),
        date(2026, 8, 11),
        "1m",
        ("ts", "close"),
        100,
        tmp_path,
    )
    rejected = service.query_under_lease(request, object())  # type: ignore[arg-type]
    assert rejected.status is PublicCommandStatusV1.REJECTED

    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease:
        report = service.query_under_lease(request, lease)
        assert report.status is PublicCommandStatusV1.SUCCEEDED

    class BrokenService(OpenMonthOneMinuteQueryServiceV1):
        def _query_under_lease(self, *args: object):
            raise ProvisionalPartitionUnavailableV1("corrupt provisional partition")

    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease:
        unavailable = BrokenService(
            PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
        ).query_under_lease(request, lease)
    assert unavailable.status is PublicCommandStatusV1.UNAVAILABLE

    class SymbolOnlyPolicy:
        def admits(self, segment: object, symbol: object) -> bool:
            return segment == "NSE_EQ" and symbol == "RELIANCE"

        def admits_instrument(self, instrument: object) -> bool:
            return False

    mismatch = OpenMonthOneMinuteQueryServiceV1(
        SymbolOnlyPolicy(),
        clock=_Clock(),  # type: ignore[arg-type]
    ).query(request)
    assert mismatch.status is PublicCommandStatusV1.REJECTED


def test_retained_prior_month_query_survives_calendar_rollover(
    tmp_path: Path,
) -> None:
    _seed_previous_month(tmp_path)
    service = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        clock=_RolloverClock(),
        allow_prior_month=True,
    )
    request = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 25),
        date(2026, 7, 31),
        "1m",
        ("ts", "close"),
        100,
        tmp_path,
    )

    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease:
        report = service.query_under_lease(request, lease)

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert type(report.payload) is QueryPayloadV1
    assert report.payload.months[0].month == "2026-07"
    assert report.payload.months[0].session_complete is True
    assert report.payload.rows[-1].ts == datetime(2026, 7, 31, 9, 59, tzinfo=UTC)


def test_production_open_month_query_stops_at_the_shared_deadline_before_catalog(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None

    class Deadline:
        checks = 0

        def ensure_live(self) -> None:
            self.checks += 1
            if self.checks == 2:
                raise QueryTimeoutV1

    request = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 1),
        date(2026, 8, 11),
        "1m",
        ("ts", "close"),
        100,
        tmp_path,
    )
    with acquired.lease as lease, pytest.raises(QueryTimeoutV1):
        OpenMonthOneMinuteQueryServiceV1(
            PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
        ).query_under_lease(request, lease, deadline=Deadline())

    assert not (tmp_path / "catalog.duckdb").exists()


def test_current_aware_query_delegates_under_caller_lease(tmp_path: Path) -> None:
    calls: list[str] = []

    class Port:
        def query(self, request: object):
            raise AssertionError

        def query_under_lease(self, request: object, lease: StorageRootLease):
            calls.append("under-lease")
            return OpenMonthOneMinuteQueryServiceV1(
                PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
            ).query_under_lease(request, lease)

    _seed(tmp_path)
    service = CurrentAwareQueryServiceV1(Port(), Port(), clock=_Clock())
    invalid = service.query_under_lease(object(), object())  # type: ignore[arg-type]
    assert invalid.status is PublicCommandStatusV1.REJECTED
    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease:
        report = service.query_under_lease(
            QueryRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 8, 1),
                date(2026, 8, 11),
                "1m",
                ("ts", "close"),
                100,
                tmp_path,
            ),
            lease,
        )
    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert calls == ["under-lease"]


def test_current_aware_query_routes_only_current_month_one_minute(
    tmp_path: Path,
) -> None:
    open_service = _QueryStub("open")
    closed_service = _QueryStub("closed")
    service = CurrentAwareQueryServiceV1(closed_service, open_service, clock=_Clock())
    current = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 1),
        date(2026, 8, 11),
        "1m",
        ("ts", "close"),
        100,
        tmp_path,
    )
    historical = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 1),
        date(2026, 7, 31),
        "1m",
        ("ts", "close"),
        100,
        tmp_path,
    )

    assert service.query(current) == "open"
    assert service.query(historical) == "closed"
    assert open_service.requests == [current]
    assert closed_service.requests == [historical]


def test_current_aware_query_routes_unknown_request_to_closed_service() -> None:
    closed_service = _QueryStub("closed")
    service = CurrentAwareQueryServiceV1(
        closed_service, _QueryStub("open"), clock=_Clock()
    )

    assert service.query(object()) == "closed"


@pytest.mark.parametrize(
    ("closed_service", "open_service", "query_request"),
    (
        (
            _QueryStub("closed"),
            _RaisingQueryStub(),
            QueryRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 8, 1),
                date(2026, 8, 11),
                "1m",
                ("ts",),
                100,
                Path.cwd(),
            ),
        ),
        (
            _RaisingQueryStub(),
            _QueryStub("open"),
            QueryRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 7, 1),
                date(2026, 7, 31),
                "1m",
                ("ts",),
                100,
                Path.cwd(),
            ),
        ),
        (
            _RaisingQueryStub(),
            _QueryStub("open"),
            QueryRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 7, 1),
                date(2026, 8, 11),
                "1m",
                ("ts",),
                100,
                Path.cwd(),
            ),
        ),
    ),
)
def test_current_aware_query_fails_closed_on_dependency_exception(
    closed_service: _QueryStub | _RaisingQueryStub,
    open_service: _QueryStub | _RaisingQueryStub,
    query_request: QueryRequestV1,
) -> None:
    service = CurrentAwareQueryServiceV1(closed_service, open_service, clock=_Clock())

    report = service.query(query_request)

    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE


def test_current_aware_query_fails_closed_on_invalid_clock(tmp_path: Path) -> None:
    service = CurrentAwareQueryServiceV1(
        _QueryStub("closed"), _QueryStub("open"), clock=_InvalidClock()
    )
    request = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 1),
        date(2026, 8, 11),
        "1m",
        ("ts",),
        100,
        tmp_path,
    )

    report = service.query(request)

    assert report.status is PublicCommandStatusV1.FAILED


def _query_report(month: int, provisional: bool) -> PublicCommandReportV1:
    digest = f"{month:x}" * 64
    ts = datetime(2026, month, 2, 3, 45, tzinfo=UTC)
    request = PublicQueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, month, 1),
        date(2026, month, 31 if month == 7 else 11),
        "1m",
        (CandleFieldV1.TS, CandleFieldV1.CLOSE),
        100,
    )
    coverage = PublicCoverageMonthV1(
        f"2026-{month:02d}",
        CoverageStateV1.PROVISIONAL if provisional else CoverageStateV1.VERIFIED,
        ts,
        ts,
        1,
        "f" * 64,
        1,
        (
            None
            if provisional
            else f"{EQUITY_MONTH_VALIDATION_POLICY_V1}+sessions-sha256:{digest}"
        ),
        digest,
        None,
        None if provisional else ValidationReason.NONE,
        ts if provisional else None,
        False if provisional else None,
    )
    payload = QueryPayloadV1(
        request,
        1,
        (coverage,),
        (PublicQueryRowV1(ts, None, None, None, 100.0 + month, None),),
    )
    return PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )


def test_current_aware_query_combines_closed_and_provisional_rows(
    tmp_path: Path,
) -> None:
    closed_service = _QueryStub(_query_report(7, False))
    open_service = _QueryStub(_query_report(8, True))
    service = CurrentAwareQueryServiceV1(closed_service, open_service, clock=_Clock())
    request = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 1),
        date(2026, 8, 11),
        "1m",
        ("ts", "close"),
        100,
        tmp_path,
    )

    report = service.query(request)

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.payload is not None
    assert report.payload.request.from_date == date(2026, 7, 1)
    assert tuple(value.month for value in report.payload.months) == (
        "2026-07",
        "2026-08",
    )
    assert tuple(value.close for value in report.payload.rows) == (107.0, 108.0)
    assert closed_service.requests[0].to_date == date(2026, 7, 31)
    assert open_service.requests[0].from_date == date(2026, 8, 1)


def test_open_month_query_returns_available_rows_and_provisional_cutoff(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    service = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    )

    report = service.query(
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("ts", "open", "high", "low", "close", "volume"),
            100,
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.failure is None
    assert report.payload is not None
    assert report.payload.row_count == 2
    assert report.payload.months[0].coverage_state.value == "PROVISIONAL"
    assert report.payload.months[0].data_cutoff == datetime(
        2026, 8, 11, 3, 46, tzinfo=UTC
    )
    assert report.payload.months[0].session_complete is False
    assert report.payload.rows[-1].close == 100.96


def test_open_month_query_reads_last_snapshot_during_active_refresh(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    writer = StorageRootLease.try_acquire_existing(tmp_path)
    assert writer.lease is not None
    try:
        report = OpenMonthOneMinuteQueryServiceV1(
            PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
        ).query(
            QueryRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 8, 1),
                date(2026, 8, 11),
                "1m",
                ("ts", "close"),
                100,
                tmp_path,
            )
        )
    finally:
        writer.lease.close()

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.payload is not None
    assert report.payload.row_count == 2


def test_open_month_query_retries_one_atomic_catalog_publication_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)
    calls = 0

    def _catalog(*args: object, **kwargs: object) -> DuckDBCatalog:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise CatalogStorageError("catalog changed during snapshot")
        return DuckDBCatalog(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_data.open_month_query.DuckDBCatalog",
        _catalog,
    )
    report = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).query(
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("ts", "close"),
            100,
            tmp_path,
        )
    )

    assert calls == 2
    assert report.status is PublicCommandStatusV1.SUCCEEDED


@pytest.mark.parametrize(
    "fault_type",
    (AssertionError, KeyError, RuntimeError, Exception),
    ids=("assertion", "key", "runtime", "exception"),
)
def test_current_aware_query_converts_real_partition_reader_fault_once_at_outer_v1_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_type: type[BaseException],
) -> None:
    _seed(tmp_path)
    error = fault_type("partition reader defect")
    reader_calls = 0

    def fail_partition_reader(
        root: object, lease: object, relative_path: object
    ) -> object:
        nonlocal reader_calls
        del root, lease, relative_path
        reader_calls += 1
        raise error

    class ClosedPort:
        def query(self, request: object) -> QueryReportV1:
            del request
            raise AssertionError("current-month query must not read closed evidence")

    monkeypatch.setattr(
        provisional_store, "read_partition_under_lease", fail_partition_reader
    )
    report = CurrentAwareQueryServiceV1(
        ClosedPort(),
        OpenMonthOneMinuteQueryServiceV1(
            PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
        ),
        clock=_Clock(),
    ).query(
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("ts", "close"),
            100,
            tmp_path,
        )
    )

    assert reader_calls == 1
    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
    assert report.payload is None


def test_open_month_query_without_persisted_snapshot_is_insufficient(
    tmp_path: Path,
) -> None:
    lease = StorageRootLease.try_acquire(tmp_path)
    assert lease.lease is not None
    lease.lease.close()
    with DuckDBCatalog(tmp_path):
        pass
    service = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    )

    report = service.query(
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("ts", "close"),
            100,
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.COVERAGE_INSUFFICIENT
    assert report.payload is not None and report.payload.rows == ()


@pytest.mark.parametrize(
    "request_value",
    (
        object(),
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            "1m",
            ("ts",),
            100,
            Path.cwd(),
        ),
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 12),
            "1m",
            ("ts",),
            100,
            Path.cwd(),
        ),
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("unknown",),
            100,
            Path.cwd(),
        ),
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("ts",),
            10_001,
            Path.cwd(),
        ),
    ),
)
def test_open_month_query_rejects_invalid_requests(request_value: object) -> None:
    report = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).query(request_value)

    assert report.status is PublicCommandStatusV1.REJECTED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.INVALID_INPUT


def test_open_month_query_rejects_unsupported_symbol(tmp_path: Path) -> None:
    report = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).query(
        QueryRequestV1(
            "NSE_EQ",
            "TCS",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("ts",),
            100,
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.REJECTED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT


def test_open_month_query_rejects_unsupported_timeframe(tmp_path: Path) -> None:
    report = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).query(
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1d",
            ("ts",),
            100,
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.REJECTED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME


def test_open_month_query_reports_unavailable_storage(tmp_path: Path) -> None:
    report = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).query(
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("ts",),
            100,
            tmp_path / "missing",
        )
    )

    assert report.status is PublicCommandStatusV1.UNAVAILABLE


def test_open_month_query_enforces_row_limit(tmp_path: Path) -> None:
    _seed(tmp_path)
    report = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).query(
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("ts",),
            1,
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED


def test_open_month_query_fails_closed_on_invalid_clock(tmp_path: Path) -> None:
    report = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_InvalidClock()
    ).query(
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("ts",),
            100,
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.REJECTED


def test_open_month_query_fails_closed_on_corrupt_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)

    def _corrupt(*_args: object) -> object:
        raise ProvisionalPartitionUnavailableV1("corrupt provisional partition")

    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_data.open_month_query.load_provisional_partition",
        _corrupt,
    )
    report = OpenMonthOneMinuteQueryServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).query(
        QueryRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("ts",),
            100,
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.UNAVAILABLE


def test_combine_query_propagates_typed_failure(tmp_path: Path) -> None:
    request = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 1),
        date(2026, 8, 11),
        "1m",
        ("ts",),
        100,
        tmp_path,
    )
    failed = PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.UNAVAILABLE,
        PublicFailureV1(
            PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            None,
            None,
            None,
            None,
            (),
        ),
        0,
        None,
    )

    report = _combine_query_reports(request, failed, object())

    assert report.status is PublicCommandStatusV1.UNAVAILABLE
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE


def test_combine_query_rejects_duplicate_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 1),
        date(2026, 8, 11),
        "1m",
        ("ts", "close"),
        100,
        tmp_path,
    )
    july = _query_report(7, False)
    august = _query_report(8, True)
    assert july.payload is not None and august.payload is not None
    object.__setattr__(august.payload.rows[0], "ts", july.payload.rows[0].ts)
    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_data.open_month_query._successful_query_payload",
        lambda source: july.payload if source is july else august.payload,
    )

    report = _combine_query_reports(request, july, august)

    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED


def test_combine_query_fails_closed_on_malformed_sources(tmp_path: Path) -> None:
    request = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 1),
        date(2026, 8, 11),
        "1m",
        ("ts",),
        100,
        tmp_path,
    )

    report = _combine_query_reports(request, object(), object())

    assert report.status is PublicCommandStatusV1.FAILED


def test_public_row_rejects_noncanonical_value() -> None:
    with pytest.raises(ValueError, match="invalid provisional row"):
        _public_row(object(), (CandleFieldV1.TS,))
